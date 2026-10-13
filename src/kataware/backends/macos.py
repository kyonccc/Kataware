"""macOS backend using CoreBluetooth (via PyObjC).

Keyboards that are already connected to macOS do not advertise, so a normal
scan never finds them. ``retrieveConnectedPeripheralsWithServices:`` returns
peripherals the system is already connected to, and connecting to them from
our app only adds a reference to the existing link (no re-pairing). After
reading we cancel our reference; the system keeps the keyboard connected.

CoreBluetooth delivers callbacks on a private dispatch queue; the monitor
thread waits for them with timeouts, so the UI never blocks.
"""

from __future__ import annotations

import logging
import queue
import time

import objc
from CoreBluetooth import (
    CBCentralManager,
    CBUUID,
)
from Foundation import NSObject

try:
    from CoreBluetooth import CBCentralManagerOptionShowPowerAlertKey
except ImportError:  # pragma: no cover
    CBCentralManagerOptionShowPowerAlertKey = "kCBInitOptionShowPowerAlert"

from libdispatch import DISPATCH_QUEUE_SERIAL, dispatch_queue_create

from ..models import BatteryCell, DeviceBattery
from . import Backend, BackendUnavailable

log = logging.getLogger(__name__)

OP_TIMEOUT = 10.0

# CBManagerState values
STATE_UNKNOWN, STATE_RESETTING, STATE_UNSUPPORTED, STATE_UNAUTHORIZED, STATE_POWERED_OFF, STATE_POWERED_ON = range(6)

STATE_MESSAGES = {
    STATE_UNSUPPORTED: "この Mac は Bluetooth LE に対応していません",
    STATE_UNAUTHORIZED: "Bluetooth へのアクセスが許可されていません。"
                        "システム設定 > プライバシーとセキュリティ > Bluetooth で Kataware を許可してください",
    STATE_POWERED_OFF: "Bluetooth がオフになっています",
    STATE_RESETTING: "Bluetooth がリセット中です",
    STATE_UNKNOWN: "Bluetooth の状態を取得できません",
}


class _Delegate(NSObject):
    """Forwards every CoreBluetooth callback into a thread-safe queue."""

    def initWithQueue_(self, q):
        self = objc.super(_Delegate, self).init()
        if self is None:
            return None
        self.q = q
        return self

    # CBCentralManagerDelegate
    def centralManagerDidUpdateState_(self, central):
        self.q.put(("state", None, int(central.state()), None))

    def centralManager_didConnectPeripheral_(self, central, peripheral):
        self.q.put(("connect", _pid(peripheral), None, None))

    def centralManager_didFailToConnectPeripheral_error_(self, central, peripheral, error):
        self.q.put(("connect", _pid(peripheral), None, error or "failed"))

    def centralManager_didDisconnectPeripheral_error_(self, central, peripheral, error):
        self.q.put(("disconnect", _pid(peripheral), None, error))

    # CBPeripheralDelegate
    def peripheral_didDiscoverServices_(self, peripheral, error):
        self.q.put(("services", _pid(peripheral), None, error))

    def peripheral_didDiscoverCharacteristicsForService_error_(self, peripheral, service, error):
        self.q.put(("chars", _pid(peripheral), service, error))

    def peripheral_didUpdateValueForCharacteristic_error_(self, peripheral, characteristic, error):
        self.q.put(("value", _pid(peripheral), characteristic, error))

    def peripheral_didDiscoverDescriptorsForCharacteristic_error_(self, peripheral, characteristic, error):
        self.q.put(("descs", _pid(peripheral), characteristic, error))

    def peripheral_didUpdateValueForDescriptor_error_(self, peripheral, descriptor, error):
        self.q.put(("dvalue", _pid(peripheral), descriptor, error))


def _pid(peripheral) -> str:
    try:
        return str(peripheral.identifier().UUIDString())
    except Exception:
        return ""


def _uuid_eq(cb_uuid, short: str) -> bool:
    try:
        return str(cb_uuid.UUIDString()).upper() in (short.upper(), f"0000{short}-0000-1000-8000-00805F9B34FB".upper())
    except Exception:
        return False


class MacBackend(Backend):
    name = "macos"

    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.delegate = _Delegate.alloc().initWithQueue_(self.q)
        self.dq = dispatch_queue_create(b"kataware.corebluetooth", DISPATCH_QUEUE_SERIAL)
        self.manager = CBCentralManager.alloc().initWithDelegate_queue_options_(
            self.delegate, self.dq, {CBCentralManagerOptionShowPowerAlertKey: False})
        self.state = STATE_UNKNOWN
        try:
            self._wait("state", None, 5.0)
        except TimeoutError:
            pass
        self.state = int(self.manager.state())
        self.bas = CBUUID.UUIDWithString_("180F")
        self.level = CBUUID.UUIDWithString_("2A19")
        self.cud = CBUUID.UUIDWithString_("2901")

    def _wait(self, kind: str, pid: str | None, timeout: float = OP_TIMEOUT, match=None):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(kind)
            try:
                ev = self.q.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(kind) from None
            ev_kind, ev_pid, obj, err = ev
            if ev_kind == "state":
                self.state = obj
                if kind == "state":
                    return obj
                continue
            if ev_kind == "disconnect" and ev_pid == pid and kind != "disconnect":
                raise ConnectionError("切断されました")
            if ev_kind != kind or (pid is not None and ev_pid != pid):
                continue  # stale event from an earlier timed-out operation
            if match is not None and obj is not None and not match(obj):
                continue
            if err is not None:
                raise ConnectionError(str(err))
            return obj

    def read_all(self) -> list[DeviceBattery]:
        # Drain events that arrived between polls (state changes etc.)
        while True:
            try:
                ev = self.q.get_nowait()
                if ev[0] == "state":
                    self.state = ev[2]
            except queue.Empty:
                break
        self.state = int(self.manager.state())
        if self.state != STATE_POWERED_ON:
            raise BackendUnavailable(STATE_MESSAGES.get(self.state, f"Bluetooth 状態 {self.state}"))

        peripherals = self.manager.retrieveConnectedPeripheralsWithServices_([self.bas]) or []
        results = []
        for p in peripherals:
            pid = _pid(p)
            name = str(p.name() or "不明なデバイス")
            try:
                results.append(self._read_peripheral(p, pid, name))
            except Exception as e:
                log.warning("%s の読み取りに失敗: %r", name, e)
                results.append(DeviceBattery(device_id=pid, name=name, error=_short_error(e)))
            finally:
                try:
                    self.manager.cancelPeripheralConnection_(p)
                except Exception:
                    pass
        return results

    def _read_peripheral(self, p, pid: str, name: str) -> DeviceBattery:
        p.setDelegate_(self.delegate)
        if int(p.state()) != 2:  # CBPeripheralStateConnected (for this app)
            self.manager.connectPeripheral_options_(p, None)
            self._wait("connect", pid)
        p.discoverServices_([self.bas])
        self._wait("services", pid)
        cells: list[BatteryCell] = []
        for svc in p.services() or []:
            if not _uuid_eq(svc.UUID(), "180F"):
                continue
            p.discoverCharacteristics_forService_([self.level], svc)
            self._wait("chars", pid, match=lambda s, svc=svc: s.isEqual_(svc))
            for index, ch in enumerate(svc.characteristics() or []):
                if not _uuid_eq(ch.UUID(), "2A19"):
                    continue
                level = None
                try:
                    p.readValueForCharacteristic_(ch)
                    self._wait("value", pid, match=lambda c, ch=ch: c.isEqual_(ch))
                    data = ch.value()
                    if data is not None and data.length() > 0:
                        level = max(0, min(100, bytes(data)[0]))
                except Exception as e:
                    log.info("%s: Battery Level 読み取り失敗: %r", name, e)
                cells.append(BatteryCell(level, self._description(p, pid, ch), index))
        if not cells:
            return DeviceBattery(device_id=pid, name=name, error="バッテリー値を読み取れません")
        return DeviceBattery(device_id=pid, name=name, cells=cells)

    def _description(self, p, pid: str, ch) -> str:
        try:
            p.discoverDescriptorsForCharacteristic_(ch)
            self._wait("descs", pid, 5.0, match=lambda c: c.isEqual_(ch))
            for d in ch.descriptors() or []:
                if not _uuid_eq(d.UUID(), "2901"):
                    continue
                p.readValueForDescriptor_(d)
                self._wait("dvalue", pid, 5.0, match=lambda x, d=d: x.isEqual_(d))
                v = d.value()
                if v is None:
                    return ""
                if isinstance(v, str):
                    return v
                try:
                    return bytes(v).decode("utf-8", "replace").strip("\x00 ")
                except Exception:
                    return str(v)
        except Exception as e:
            log.debug("User Description 取得失敗: %r", e)
        return ""

    def probe(self) -> dict:
        from CoreBluetooth import CBPeripheral

        required = {
            CBCentralManager: ["retrieveConnectedPeripheralsWithServices:", "connectPeripheral:options:",
                               "cancelPeripheralConnection:", "state"],
            CBPeripheral: ["discoverServices:", "discoverCharacteristics:forService:",
                           "readValueForCharacteristic:", "discoverDescriptorsForCharacteristic:",
                           "readValueForDescriptor:", "setDelegate:", "identifier", "name", "services", "state"],
        }
        missing = [f"{cls.__name__}.{sel}" for cls, sels in required.items()
                   for sel in sels if not cls.instancesRespondToSelector_(sel.encode())]
        if missing:
            raise AttributeError(f"CoreBluetooth API が見つかりません: {missing}")
        return {"state": int(self.manager.state())}

    def close(self) -> None:
        try:
            self.manager.setDelegate_(None)
        except Exception:
            pass


def _short_error(e: BaseException) -> str:
    if isinstance(e, TimeoutError):
        return "応答がありません (タイムアウト)"
    msg = str(e) or e.__class__.__name__
    return msg.splitlines()[0][:120]
