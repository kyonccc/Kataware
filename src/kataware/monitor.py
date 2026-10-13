"""Background polling and the state shown in the UI (UI-toolkit independent)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable

from .backends import Backend, BackendUnavailable, create_backend
from .config import SettingsStore
from .models import BatteryCell, DeviceBattery, LabeledLevel, SIDE_LEFT, label_cells

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
        # Last known values survive restarts so a sleeping mouse or a keyboard
        # that is switched off still shows where its battery was.
        self.cache_path = store.path.with_name("devices.json")
        self._load_cache()

    def _load_cache(self) -> None:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            for d in data:
                cells = [BatteryCell(**c) for c in d.get("cells", [])]
                if not cells:
                    continue
                self.devices[d["device_id"]] = DeviceBattery(
                    device_id=d["device_id"], name=d["name"], cells=cells, connected=False,
                    updated_at=float(d.get("updated_at", 0)))
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("前回の機器情報を読み込めませんでした")

    def _save_cache(self) -> None:
        try:
            data = [{"device_id": d.device_id, "name": d.name, "updated_at": d.updated_at,
                     "cells": [asdict(c) for c in d.cells]} for d in self.devices.values() if d.cells]
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.cache_path)
        except Exception:
            log.exception("機器情報を保存できませんでした")

    def forget_disconnected(self) -> None:
        with self.lock:
            for dev_id in [k for k, d in self.devices.items() if not d.connected]:
                del self.devices[dev_id]
            self._save_cache()

    def has_disconnected(self) -> bool:
        with self.lock:
            return any(not d.connected for d in self.devices.values())

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
            self._save_cache()
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
        self._change_timer: threading.Timer | None = None
        self._change_lock = threading.Lock()

    def refresh(self) -> None:
        self._wake.set()

    def notify_change(self, delay: float = 3.0) -> None:
        """A device connected or disconnected: read again shortly (the short
        delay lets the connection settle and merges bursts of events)."""
        with self._change_lock:
            if self._change_timer is not None:
                return
            timer = threading.Timer(delay, self._fire_change)
            timer.daemon = True
            self._change_timer = timer
            timer.start()

    def _fire_change(self) -> None:
        with self._change_lock:
            self._change_timer = None
        log.info("機器の接続・切断を検知したので更新します")
        self.refresh()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()

    def poll_once(self) -> list[LowBatteryAlert]:
        alerts: list[LowBatteryAlert] = []
        try:
            if self.backend is None:
                self.backend = self.factory()
                log.info("Bluetooth バックエンド: %s", self.backend.name)
                try:
                    self.backend.start_watching(self.notify_change)
                except Exception:
                    log.exception("接続状態の監視を開始できません")
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
