"""Windows backend using the WinRT Bluetooth LE APIs (via pywinrt).

Design notes (what made the old tray app unstable and how this avoids it):
* Every WinRT object (BluetoothLEDevice, GattDeviceService) is closed after
  each poll, so no stale GATT sessions pile up across sleep/resume or
  reconnects.
* We never subscribe to notifications or open the service exclusively; we
  only do short read requests, which coexist with Windows' own HID driver.
* Only devices that Windows reports as *connected* are queried, so a
  keyboard that is switched off never triggers long connection attempts.
* Every await has a timeout and every device is isolated in try/except.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid

from ..models import BatteryCell, DeviceBattery
from . import BAS_SERVICE, BATTERY_LEVEL, USER_DESCRIPTION, Backend, BackendUnavailable

log = logging.getLogger(__name__)

OP_TIMEOUT = 10.0

# DEVPKEY_Bluetooth_Battery: the battery level Windows itself shows in
# Settings > Bluetooth & devices. Windows fills it for Classic devices
# (e.g. hands-free profile) and for LE keyboards / mice it talks to directly.
WIN_BATTERY_PROP = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2"
_ADDR_RE = re.compile(r"DEV_([0-9A-F]{12})|&([0-9A-F]{12})_C0", re.IGNORECASE)


def parse_bt_address(instance_id: str) -> int | None:
    """Bluetooth address from a PnP instance id such as BTHENUM\\DEV_A1B2C3D4E5F6\\..."""
    m = _ADDR_RE.search(instance_id or "")
    if not m:
        return None
    return int(m.group(1) or m.group(2), 16)


class WindowsBackend(Backend):
    name = "windows"

    def __init__(self):
        try:
            from winrt import runtime

            try:
                runtime.init_apartment(runtime.MTA)
            except Exception:  # already initialised for this thread
                pass
            from winrt.windows.devices import bluetooth as bt
            from winrt.windows.devices.bluetooth import genericattributeprofile as gatt
            from winrt.windows.devices import enumeration as enum
        except Exception as e:  # pragma: no cover - only on broken installs
            raise BackendUnavailable(f"WinRT Bluetooth API を読み込めません: {e}") from e
        self.bt = bt
        self.gatt = gatt
        self.enum = enum
        self.loop = asyncio.new_event_loop()
        self._skipped: dict[str, str] = {}
        self._watchers: list = []

    def start_watching(self, on_change) -> None:
        """Watch paired Bluetooth (LE and Classic) devices for connect /
        disconnect so a sleeping mouse that wakes up shows up immediately."""
        bt, enum = self.bt, self.enum
        connected_key = "System.Devices.Aep.IsConnected"
        for selector_cls in (bt.BluetoothLEDevice, bt.BluetoothDevice):
            try:
                watcher = enum.DeviceInformation.create_watcher_with_kind_aqs_filter_and_additional_properties(
                    selector_cls.get_device_selector_from_pairing_state(True), [connected_key],
                    enum.DeviceInformationKind.ASSOCIATION_ENDPOINT)
                ready = {"done": False}

                def on_completed(_sender, _args, ready=ready):
                    ready["done"] = True

                def on_updated(_sender, update, ready=ready):
                    try:
                        if ready["done"] and update is not None and connected_key in update.properties:
                            on_change()
                    except Exception:
                        log.debug("接続変化の処理に失敗", exc_info=True)

                watcher.add_enumeration_completed(on_completed)
                watcher.add_updated(on_updated)
                watcher.add_added(lambda _s, _i, ready=ready: ready["done"] and on_change())
                watcher.start()
                self._watchers.append(watcher)
            except Exception as e:
                log.warning("接続状態の監視を開始できません: %r", e)
        if self._watchers:
            log.info("Bluetooth 機器の接続・切断を監視しています")

    def close(self) -> None:
        for w in self._watchers:
            try:
                w.stop()
            except Exception:
                pass
        self._watchers.clear()
        try:
            self.loop.close()
        except Exception:
            pass

    def read_all(self) -> list[DeviceBattery]:
        return self.loop.run_until_complete(self._read_all())

    def probe(self) -> dict:
        bt, gatt, enum = self.bt, self.gatt, self.enum
        required = {
            bt.BluetoothAdapter: ["get_default_async"],
            bt.BluetoothLEDevice: ["get_device_selector_from_pairing_state", "from_id_async",
                                   "from_bluetooth_address_async", "bluetooth_address",
                                   "get_gatt_services_for_uuid_with_cache_mode_async", "close",
                                   "connection_status", "name"],
            gatt.GattDeviceService: ["get_characteristics_for_uuid_with_cache_mode_async", "close"],
            gatt.GattCharacteristic: ["read_value_with_cache_mode_async", "user_description",
                                      "attribute_handle", "get_descriptors_for_uuid_with_cache_mode_async"],
            gatt.GattDescriptor: ["read_value_with_cache_mode_async"],
            enum.DeviceWatcher: ["start", "stop", "add_updated", "add_added", "add_enumeration_completed"],
            enum.DeviceInformationUpdate: ["properties", "id"],
            enum.DeviceInformation: ["find_all_async_aqs_filter",
                                     "create_watcher_with_kind_aqs_filter_and_additional_properties",
                                     "find_all_async_with_kind_aqs_filter_and_additional_properties",
                                     "properties", "id", "name"],
            bt.BluetoothDevice: ["from_bluetooth_address_async", "connection_status", "name", "close"],
        }
        missing = [f"{cls.__name__}.{name}" for cls, names in required.items()
                   for name in names if not hasattr(cls, name)]
        if missing:
            raise AttributeError(f"WinRT API が見つかりません: {missing}")
        _ = (enum.DeviceInformationKind.DEVICE, enum.DeviceInformationKind.ASSOCIATION_ENDPOINT, bt.BluetoothCacheMode.CACHED, bt.BluetoothCacheMode.UNCACHED,
             bt.BluetoothConnectionStatus.CONNECTED, gatt.GattCommunicationStatus.SUCCESS)

        async def enumerate_paired():
            selector = bt.BluetoothLEDevice.get_device_selector_from_pairing_state(True)
            infos = await self._await(enum.DeviceInformation.find_all_async_aqs_filter(selector))
            return [i.name for i in infos]

        async def windows_battery():
            return [d.name for d in await self._read_windows_battery(set(), {})]

        self.start_watching(lambda: None)
        watching = len(self._watchers)
        return {"watchers": watching,
                "paired_le_devices": self.loop.run_until_complete(enumerate_paired()),
                "windows_battery_devices": self.loop.run_until_complete(windows_battery()),
                "windows_battery_query": getattr(self, "query_mode", "")}

    async def _await(self, op, timeout: float = OP_TIMEOUT):
        return await asyncio.wait_for(op, timeout)

    async def _read_all(self) -> list[DeviceBattery]:
        bt, enum = self.bt, self.enum
        await self._check_adapter()
        selector = bt.BluetoothLEDevice.get_device_selector_from_pairing_state(True)
        infos = await self._await(enum.DeviceInformation.find_all_async_aqs_filter(selector))
        results: list[DeviceBattery] = []
        skipped: dict[str, str] = {}
        gatt_addresses: set[int] = set()
        for info in infos:
            name = info.name or info.id
            try:
                dev, reason, address = await self._read_device(info.id, info.name)
                if address is not None and dev is not None:
                    gatt_addresses.add(address)
                if dev is not None:
                    results.append(dev)
                else:
                    skipped[name] = reason
            except Exception as e:
                log.warning("%s の読み取りに失敗: %r", info.name, e)
                results.append(DeviceBattery(device_id=info.id, name=info.name or "不明なデバイス",
                                             error=_short_error(e)))
        try:
            for dev in await self._read_windows_battery(gatt_addresses, skipped):
                results.append(dev)
                skipped.pop(dev.name, None)
        except Exception as e:
            log.warning("Windows のバッテリー情報を取得できません: %r", e)
        if skipped != self._skipped:
            for name, reason in sorted(skipped.items()):
                log.info("表示しない機器: %s (%s)", name, reason)
            self._skipped = skipped
        return results

    async def _read_windows_battery(self, gatt_addresses: set[int], skipped: dict[str, str]) -> list[DeviceBattery]:
        """Fallback for devices whose battery we cannot read over GATT (Classic
        Bluetooth, or LE devices that hide the Battery Service): use the value
        Windows shows in Settings."""
        bt, enum = self.bt, self.enum
        kind = enum.DeviceInformationKind.DEVICE
        find = enum.DeviceInformation.find_all_async_with_kind_aqs_filter_and_additional_properties
        try:
            infos = await self._await(find(f"{WIN_BATTERY_PROP}:<>[]", [WIN_BATTERY_PROP], kind))
            self.query_mode = "aqs"
        except Exception as e:  # AQS not accepted: scan every device node instead
            log.debug("AQS フィルターが使えません (%r)。全デバイスを確認します", e)
            infos = await self._await(find("", [WIN_BATTERY_PROP], kind), 30)
            self.query_mode = "scan"

        found: dict[int, DeviceBattery] = {}
        for info in infos:
            props = info.properties
            level = _unbox_level(props[WIN_BATTERY_PROP] if props is not None and WIN_BATTERY_PROP in props else None)
            address = parse_bt_address(info.id)
            if level is None or address is None or address in gatt_addresses or address in found:
                continue
            name, connected = await self._classic_or_le_status(address)
            name = name or info.name or "不明なデバイス"
            if not connected:
                skipped[name] = "未接続 (Windows の値)"
                continue
            found[address] = DeviceBattery(device_id=f"win:{address:012X}", name=name,
                                           cells=[BatteryCell(level, "", 0)])
        return list(found.values())

    async def _classic_or_le_status(self, address: int) -> tuple[str, bool]:
        bt = self.bt
        for cls in (bt.BluetoothDevice, bt.BluetoothLEDevice):
            dev = None
            try:
                dev = await self._await(cls.from_bluetooth_address_async(address), 5)
                if dev is not None:
                    return dev.name, dev.connection_status == bt.BluetoothConnectionStatus.CONNECTED
            except Exception as e:
                log.debug("%012X の接続状態を取得できません: %r", address, e)
            finally:
                if dev is not None:
                    _safe_close(dev)
        return "", False

    async def _check_adapter(self) -> None:
        bt = self.bt
        try:
            adapter = await self._await(bt.BluetoothAdapter.get_default_async())
        except Exception as e:
            raise BackendUnavailable(f"Bluetooth アダプターを取得できません: {_short_error(e)}") from e
        if adapter is None:
            raise BackendUnavailable("Bluetooth アダプターが見つかりません")
        if not adapter.is_low_energy_supported:
            raise BackendUnavailable("この PC の Bluetooth は LE に対応していません")

    async def _read_device(self, device_id: str, fallback_name: str
                           ) -> tuple[DeviceBattery | None, str, int | None]:
        """Returns (battery or None, reason it was skipped, Bluetooth address)."""
        bt, gatt = self.bt, self.gatt
        device = await self._await(bt.BluetoothLEDevice.from_id_async(device_id))
        if device is None:
            return None, "デバイスを開けません", None
        services = []
        try:
            address = int(device.bluetooth_address)
            if device.connection_status != bt.BluetoothConnectionStatus.CONNECTED:
                return None, "未接続", address
            name = device.name or fallback_name or "不明なデバイス"
            res = await self._await(device.get_gatt_services_for_uuid_with_cache_mode_async(
                uuid.UUID(BAS_SERVICE), bt.BluetoothCacheMode.CACHED))
            if res.status != gatt.GattCommunicationStatus.SUCCESS:
                # Try once more against the device itself (cache can be empty
                # right after pairing).
                res = await self._await(device.get_gatt_services_for_uuid_with_cache_mode_async(
                    uuid.UUID(BAS_SERVICE), bt.BluetoothCacheMode.UNCACHED))
            if res.status != gatt.GattCommunicationStatus.SUCCESS:
                return None, f"バッテリーサービスにアクセスできません (status={res.status})", address
            services = list(res.services)
            if not services:
                return None, "バッテリーサービスがありません", address
            cells: list[BatteryCell] = []
            for svc in services:
                cells.extend(await self._read_service(svc))
            if not cells:
                return (DeviceBattery(device_id=device_id, name=name, error="バッテリー値を読み取れません"),
                        "", address)
            return DeviceBattery(device_id=device_id, name=name, cells=cells), "", address
        finally:
            for svc in services:
                _safe_close(svc)
            _safe_close(device)

    async def _read_service(self, svc) -> list[BatteryCell]:
        bt, gatt = self.bt, self.gatt
        res = await self._await(svc.get_characteristics_for_uuid_with_cache_mode_async(
            uuid.UUID(BATTERY_LEVEL), bt.BluetoothCacheMode.CACHED))
        if res.status != gatt.GattCommunicationStatus.SUCCESS:
            res = await self._await(svc.get_characteristics_for_uuid_with_cache_mode_async(
                uuid.UUID(BATTERY_LEVEL), bt.BluetoothCacheMode.UNCACHED))
        if res.status != gatt.GattCommunicationStatus.SUCCESS:
            return []
        cells = []
        for ch in res.characteristics:
            level = None
            try:
                r = await self._await(ch.read_value_with_cache_mode_async(bt.BluetoothCacheMode.UNCACHED))
                if r.status == gatt.GattCommunicationStatus.SUCCESS and r.value is not None:
                    data = bytes(r.value)
                    if data:
                        level = max(0, min(100, data[0]))
                else:
                    log.info("Battery Level 読み取り失敗 handle=%s status=%s", ch.attribute_handle, r.status)
            except Exception as e:
                log.info("Battery Level 読み取り例外 handle=%s: %r", ch.attribute_handle, e)
            cells.append(BatteryCell(level, await self._description(ch), int(ch.attribute_handle)))
        return cells

    async def _description(self, ch) -> str:
        try:
            desc = ch.user_description
            if desc:
                return desc
        except Exception:
            pass
        bt, gatt = self.bt, self.gatt
        try:
            res = await self._await(ch.get_descriptors_for_uuid_with_cache_mode_async(
                uuid.UUID(USER_DESCRIPTION), bt.BluetoothCacheMode.CACHED), 5)
            if res.status != gatt.GattCommunicationStatus.SUCCESS:
                return ""
            for d in res.descriptors:
                r = await self._await(d.read_value_with_cache_mode_async(bt.BluetoothCacheMode.CACHED), 5)
                if r.status == gatt.GattCommunicationStatus.SUCCESS and r.value is not None:
                    return bytes(r.value).decode("utf-8", "replace").strip("\x00 ")
        except Exception as e:
            log.debug("User Description 取得失敗: %r", e)
        return ""


def _unbox_level(value) -> int | None:
    """WinRT property values arrive boxed; the battery property is a byte."""
    if value is None:
        return None
    if isinstance(value, int):
        level = value
    else:
        from winrt import system

        level = None
        for unbox in ("unbox_uint8", "unbox_int32", "unbox_uint32", "unbox_int16", "unbox_uint16"):
            try:
                level = int(getattr(system, unbox)(value))
                break
            except Exception:
                continue
        if level is None:
            return None
    return level if 0 <= level <= 100 else None


def _safe_close(obj) -> None:
    try:
        obj.close()
    except Exception:
        pass


def _short_error(e: BaseException) -> str:
    if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
        return "応答がありません (タイムアウト)"
    msg = str(e) or e.__class__.__name__
    return msg.splitlines()[0][:120]
