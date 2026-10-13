"""System tray (Windows) / menu bar (macOS) application."""

from __future__ import annotations

import logging
import sys
import threading
import time

from . import __version__
from .config import APP_NAME, SettingsStore, log_path
from .icon import render_icon
from .models import SIDE_LEFT, SIDE_NAMES, SIDE_RIGHT, format_level
from .monitor import LowBatteryAlert, Monitor, MonitorState
from .platform_utils import (
    tray_location_hint,
    autostart_enabled,
    autostart_supported,
    notify_macos,
    open_path,
    set_autostart,
)

log = logging.getLogger(__name__)

POLL_CHOICES = [1, 5, 15, 30]
THRESHOLD_CHOICES = [0, 10, 20, 30]


def _on_main_thread(fn):
    """Run ``fn`` on the UI thread (required by AppKit on macOS)."""
    if sys.platform == "darwin":
        try:
            from PyObjCTools import AppHelper

            AppHelper.callAfter(fn)
            return
        except Exception:
            log.exception("callAfter に失敗")
    fn()


class TrayApp:
    def __init__(self, demo: bool = False, store: SettingsStore | None = None):
        import pystray  # imported lazily: needs a display / GUI session

        self.pystray = pystray
        self.store = store or SettingsStore()
        self.state = MonitorState(self.store)
        self.monitor = Monitor(self.state, self._on_update, demo=demo)
        self.icon = pystray.Icon(
            APP_NAME,
            icon=render_icon([], self.store.settings.icon_style),
            title=APP_NAME,
            menu=pystray.Menu(self._menu_items),
        )
        self._ui_lock = threading.Lock()

    # --- lifecycle ---------------------------------------------------------

    def run(self, auto_exit_seconds: float | None = None) -> None:
        def setup(icon):
            icon.visible = True
            self.monitor.start()
            if not self.store.settings.welcomed and not auto_exit_seconds:
                threading.Timer(2.0, self._welcome).start()
            if auto_exit_seconds:
                threading.Timer(auto_exit_seconds, self.quit).start()

        self.icon.run(setup=setup)

    def _welcome(self) -> None:
        # The app has no window, so tell first-time users where it lives.
        self._notify_raw("起動しました", f"{tray_location_hint()}\nクリックすると左右の残量が表示されます。")
        self.store.settings.welcomed = True
        self.store.save()

    def quit(self, *_):
        log.info("終了します")
        self.monitor.stop()
        _on_main_thread(self.icon.stop)

    # --- updates from the monitor thread -----------------------------------

    def _on_update(self, alerts: list[LowBatteryAlert]) -> None:
        _on_main_thread(self._refresh_ui)
        for a in alerts:
            self._notify(f"{a.device_name} の{a.label}側のバッテリーが {a.level}% です"
                         if a.label in SIDE_NAMES.values()
                         else f"{a.device_name} ({a.label}) のバッテリーが {a.level}% です")

    def _refresh_ui(self) -> None:
        with self._ui_lock:
            try:
                s = self.store.settings
                dev = self.state.icon_device()
                if dev is None:
                    self.icon.icon = render_icon([], s.icon_style, s.low_threshold)
                    self.icon.title = f"{APP_NAME}\n{self.state.status}"[:127]
                else:
                    levels = self.state.labeled(dev)
                    self.icon.icon = render_icon(levels, s.icon_style, s.low_threshold, dev.connected)
                    self.icon.title = self._tooltip()
                self.icon.update_menu()
            except Exception:
                log.exception("アイコン更新に失敗")

    def _tooltip(self) -> str:
        lines = []
        for dev in self.state.sorted_devices():
            if not dev.connected:
                continue
            parts = " / ".join(f"{lv.label} {format_level(lv.level)}" for lv in self.state.labeled(dev))
            lines.append(f"{dev.name}: {parts}" if parts else dev.name)
        text = "\n".join(lines) or self.state.status or APP_NAME
        return text[:127]  # Windows tooltip limit

    def _notify(self, message: str) -> None:
        self._notify_raw("バッテリー残量低下", message)

    def _notify_raw(self, title: str, message: str) -> None:
        log.info("通知: %s %s", title, message)
        title = f"{APP_NAME}: {title}"
        if sys.platform == "darwin":
            notify_macos(title, message)
            return
        try:
            self.icon.notify(message, title)
        except Exception:
            log.exception("通知に失敗")

    # --- menu ----------------------------------------------------------------

    def _menu_items(self):
        Item, Menu = self.pystray.MenuItem, self.pystray.Menu
        s = self.store.settings
        devices = self.state.sorted_devices()

        if self.state.status:
            yield Item(self.state.status, None, enabled=False)
        if not devices and not self.state.status:
            yield Item("読み取り中…", None, enabled=False)

        for dev in devices:
            header = dev.name if dev.connected else f"{dev.name}（未接続）"
            yield Item(header, None, enabled=False)
            for lv in self.state.labeled(dev):
                yield Item(f"    {lv.label}: {format_level(lv.level)}", None, enabled=False)
            if dev.error:
                yield Item(f"    ⚠ {dev.error}", None, enabled=False)

        if self.state.last_poll:
            yield Item(f"最終更新 {time.strftime('%H:%M', time.localtime(self.state.last_poll))}",
                       None, enabled=False)
        yield Menu.SEPARATOR
        yield Item("今すぐ更新", lambda *_: self.monitor.refresh())
        yield Menu.SEPARATOR

        split_devs = [d for d in devices if d.is_split]
        if split_devs:
            yield Item("左右の設定（メイン側）", Menu(*[
                Item(d.name, Menu(*[
                    Item(f"メイン(セントラル)は{SIDE_NAMES[side]}側", self._set_side(d.device_id, side),
                         checked=self._is_side(d.device_id, side), radio=True)
                    for side in (SIDE_LEFT, SIDE_RIGHT)
                ])) for d in split_devs
            ]))
        if devices:
            yield Item("アイコンに表示する機器", Menu(
                Item("自動", self._set_icon_device(""), checked=lambda _: not s.icon_device, radio=True),
                *[Item(d.name, self._set_icon_device(d.device_id),
                       checked=self._is_icon_device(d.device_id), radio=True) for d in devices],
            ))
        yield Item("アイコンの表示形式", Menu(
            Item("数字", self._set_style("numbers"), checked=lambda _: s.icon_style == "numbers", radio=True),
            Item("バー", self._set_style("bars"), checked=lambda _: s.icon_style == "bars", radio=True),
        ))
        yield Item("更新間隔", Menu(*[
            Item(f"{m} 分", self._set_poll(m), checked=self._is_poll(m), radio=True) for m in POLL_CHOICES
        ]))
        yield Item("残量低下の通知", Menu(*[
            Item("通知しない" if t == 0 else f"{t}% 以下で通知", self._set_threshold(t),
                 checked=self._is_threshold(t), radio=True) for t in THRESHOLD_CHOICES
        ]))
        if autostart_supported():
            yield Item("ログイン時に起動", self._toggle_autostart, checked=lambda _: autostart_enabled())
        yield Item("ログを開く", lambda *_: open_path(log_path()))
        yield Menu.SEPARATOR
        yield Item(f"{APP_NAME} v{__version__}", None, enabled=False)
        yield Item("終了", self.quit)

    # menu helpers (closures keep pystray's callback signature simple)
    def _changed(self, refresh_backend: bool = False):
        self.store.save()
        _on_main_thread(self._refresh_ui)
        if refresh_backend:
            self.monitor.refresh()

    def _set_side(self, dev_id, side):
        def action(*_):
            self.store.settings.central_side[dev_id] = side
            self._changed()
        return action

    def _is_side(self, dev_id, side):
        return lambda _: self.state.central_side(dev_id) == side

    def _set_icon_device(self, dev_id):
        def action(*_):
            self.store.settings.icon_device = dev_id
            self._changed()
        return action

    def _is_icon_device(self, dev_id):
        return lambda _: self.store.settings.icon_device == dev_id

    def _set_style(self, style):
        def action(*_):
            self.store.settings.icon_style = style
            self._changed()
        return action

    def _set_poll(self, minutes):
        def action(*_):
            self.store.settings.poll_minutes = minutes
            self._changed(refresh_backend=True)
        return action

    def _is_poll(self, minutes):
        return lambda _: self.store.settings.poll_minutes == minutes

    def _set_threshold(self, t):
        def action(*_):
            self.store.settings.low_threshold = t
            self._changed()
        return action

    def _is_threshold(self, t):
        return lambda _: self.store.settings.low_threshold == t

    def _toggle_autostart(self, *_):
        set_autostart(not autostart_enabled())
        _on_main_thread(self._refresh_ui)
