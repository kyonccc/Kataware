"""Background polling and the state shown in the UI (UI-toolkit independent)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .backends import Backend, BackendUnavailable, create_backend
from .config import SettingsStore
from .models import DeviceBattery, LabeledLevel, SIDE_LEFT, label_cells

log = logging.getLogger(__name__)

NOTIFY_HYSTERESIS = 5


@dataclass
class LowBatteryAlert:
    device_name: str
    label: str
    level: int


class MonitorState:
    """Merges successive backend readings and decides on notifications."""

    def __init__(self, store: SettingsStore):
        self.store = store
        self.devices: dict[str, DeviceBattery] = {}
        self.status: str = "起動中…"
        self.last_poll: float | None = None
        self._alerted: set[tuple[str, str]] = set()
        self.lock = threading.RLock()

    def central_side(self, device_id: str) -> str:
        return self.store.settings.central_side.get(device_id, SIDE_LEFT)

    def labeled(self, dev: DeviceBattery) -> list[LabeledLevel]:
        return label_cells(dev, self.central_side(dev.device_id))

    def apply(self, readings: list[DeviceBattery]) -> list[LowBatteryAlert]:
        with self.lock:
            seen = set()
            for r in readings:
                seen.add(r.device_id)
                prev = self.devices.get(r.device_id)
                if r.error and prev is not None and prev.cells:
                    # keep the last good values, just show the error
                    prev.error = r.error
                    prev.connected = True
                    continue
                self.devices[r.device_id] = r
            for dev_id, dev in self.devices.items():
                if dev_id not in seen:
                    dev.connected = False
                    dev.error = ""
            self.last_poll = time.time()
            self.status = "" if readings else "バッテリー情報を持つ Bluetooth 機器が接続されていません"
            return self._alerts()

    def set_unavailable(self, message: str) -> None:
        with self.lock:
            self.status = message
            for dev in self.devices.values():
                dev.connected = False

    def _alerts(self) -> list[LowBatteryAlert]:
        threshold = self.store.settings.low_threshold
        alerts = []
        for dev in self.devices.values():
            if not dev.connected or dev.error:
                continue
            for lv in self.labeled(dev):
                if lv.level is None:
                    continue
                key = (dev.device_id, lv.label)
                if threshold and lv.level <= threshold:
                    if key not in self._alerted:
                        self._alerted.add(key)
                        alerts.append(LowBatteryAlert(dev.name, lv.label, lv.level))
                elif lv.level > threshold + NOTIFY_HYSTERESIS:
                    self._alerted.discard(key)
        return alerts

    def sorted_devices(self) -> list[DeviceBattery]:
        with self.lock:
            return sorted(self.devices.values(), key=lambda d: (not d.connected, not d.is_split, d.name.lower()))

    def icon_device(self) -> DeviceBattery | None:
        with self.lock:
            chosen = self.store.settings.icon_device
            if chosen and chosen in self.devices:
                return self.devices[chosen]
            devs = self.sorted_devices()
            return devs[0] if devs else None


class Monitor(threading.Thread):
    """Polls the backend on its own thread; the UI is notified via callback."""

    def __init__(self, state: MonitorState, on_update: Callable[[list[LowBatteryAlert]], None],
                 demo: bool = False, backend_factory: Callable[[], Backend] | None = None):
        super().__init__(name="monitor", daemon=True)
        self.state = state
        self.on_update = on_update
        self.factory = backend_factory or (lambda: create_backend(demo))
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self.backend: Backend | None = None
        self.polls = 0
        self.ok = False

    def refresh(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()

    def poll_once(self) -> list[LowBatteryAlert]:
        alerts: list[LowBatteryAlert] = []
        try:
            if self.backend is None:
                self.backend = self.factory()
                log.info("Bluetooth バックエンド: %s", self.backend.name)
            readings = self.backend.read_all()
            log.info("読み取り結果: %s", [(d.name, [c.level for c in d.cells], d.error) for d in readings])
            alerts = self.state.apply(readings)
            self.ok = True
        except BackendUnavailable as e:
            log.warning("Bluetooth 利用不可: %s", e)
            self.state.set_unavailable(str(e))
        except Exception as e:
            log.exception("読み取り中に予期しないエラー")
            self.state.set_unavailable(f"読み取りエラー: {e}")
            # rebuild the backend next time in case it is in a bad state
            if self.backend is not None:
                try:
                    self.backend.close()
                except Exception:
                    pass
                self.backend = None
        else:
            return self._done(alerts)
        self.ok = False
        return self._done(alerts)

    def _done(self, alerts):
        self.polls += 1
        return alerts

    def run(self) -> None:
        while not self._stopping.is_set():
            alerts = self.poll_once()
            try:
                self.on_update(alerts)
            except Exception:
                log.exception("UI 更新に失敗")
            # Bluetooth unavailable -> retry sooner so we recover quickly.
            minutes = self.state.store.settings.poll_minutes
            wait = minutes * 60 if self.ok else 30
            self._wake.wait(wait)
            self._wake.clear()
        if self.backend is not None:
            self.backend.close()
