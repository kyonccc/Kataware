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
import uuid

from ..models import BatteryCell, DeviceBattery
from . import BAS_SERVICE, BATTERY_LEVEL, USER_DESCRIPTION, Backend, BackendUnavailable

log = logging.getLogger(__name__)

OP_TIMEOUT = 10.0


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

    def close(self) -> None:
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
                                   "get_gatt_services_for_uuid_with_cache_mode_async", "close",
                                   "connection_status", "name"],
            gatt.GattDeviceService: ["get_characteristics_for_uuid_with_cache_mode_async", "close"],
            gatt.GattCharacteristic: ["read_value_with_cache_mode_async", "user_description",
                                      "attribute_handle", "get_descriptors_for_uuid_with_cache_mode_async"],
            gatt.GattDescriptor: ["read_value_with_cache_mode_async"],
            enum.DeviceInformation: ["find_all_async_aqs_filter"],
        }
        missing = [f"{cls.__name__}.{name}" for cls, names in required.items()
                   for name in names if not hasattr(cls, name)]
        if missing:
            raise AttributeError(f"WinRT API が見つかりません: {missing}")
        _ = (bt.BluetoothCacheMode.CACHED, bt.BluetoothCacheMode.UNCACHED,
             bt.BluetoothConnectionStatus.CONNECTED, gatt.GattCommunicationStatus.SUCCESS)

        async def enumerate_paired():
            selector = bt.BluetoothLEDevice.get_device_selector_from_pairing_state(True)
            infos = await self._await(enum.DeviceInformation.find_all_async_aqs_filter(selector))
            return [i.name for i in infos]

        return {"paired_le_devices": self.loop.run_until_complete(enumerate_paired())}

    async def _await(self, op, timeout: float = OP_TIMEOUT):
        return await asyncio.wait_for(op, timeout)

    async def _read_all(self) -> list[DeviceBattery]:
        bt, enum = self.bt, self.enum
        await self._check_adapter()
        selector = bt.BluetoothLEDevice.get_device_selector_from_pairing_state(True)
        infos = await self._await(enum.DeviceInformation.find_all_async_aqs_filter(selector))
        results: list[DeviceBattery] = []
        for info in infos:
            try:
                dev = await self._read_device(info.id, info.name)
                if dev is not None:
                    results.append(dev)
            except Exception as e:
                log.warning("%s の読み取りに失敗: %r", info.name, e)
                results.append(DeviceBattery(device_id=info.id, name=info.name or "不明なデバイス",
                                             error=_short_error(e)))
        return results

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

    async def _read_device(self, device_id: str, fallback_name: str) -> DeviceBattery | None:
        bt, gatt = self.bt, self.gatt
        device = await self._await(bt.BluetoothLEDevice.from_id_async(device_id))
        if device is None:
            return None
        services = []
        try:
            if device.connection_status != bt.BluetoothConnectionStatus.CONNECTED:
                return None
            name = device.name or fallback_name or "不明なデバイス"
            res = await self._await(device.get_gatt_services_for_uuid_with_cache_mode_async(
                uuid.UUID(BAS_SERVICE), bt.BluetoothCacheMode.CACHED))
            if res.status != gatt.GattCommunicationStatus.SUCCESS:
                # Try once more against the device itself (cache can be empty
                # right after pairing).
                res = await self._await(device.get_gatt_services_for_uuid_with_cache_mode_async(
                    uuid.UUID(BAS_SERVICE), bt.BluetoothCacheMode.UNCACHED))
            if res.status != gatt.GattCommunicationStatus.SUCCESS:
                log.info("%s: バッテリーサービスを取得できません (status=%s)", name, res.status)
                return None
            services = list(res.services)
            if not services:
                return None  # device has no battery service
            cells: list[BatteryCell] = []
            for svc in services:
                cells.extend(await self._read_service(svc))
            if not cells:
                return DeviceBattery(device_id=device_id, name=name, error="バッテリー値を読み取れません")
            return DeviceBattery(device_id=device_id, name=name, cells=cells)
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
