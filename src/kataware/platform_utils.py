"""Small OS integrations: notifications, launch at login, opening files."""

from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .config import APP_ID, APP_NAME

log = logging.getLogger(__name__)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def launch_command() -> list[str]:
    if is_frozen():
        return [sys.executable]
    return [sys.executable, "-m", "kataware"]


def notify_macos(title: str, message: str) -> None:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    try:
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        log.exception("通知を表示できませんでした")


def show_message(title: str, message: str, error: bool = False) -> None:
    """Show a simple modal dialog (used when the tray icon cannot explain itself)."""
    try:
        if sys.platform == "win32":
            import ctypes

            flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
            ctypes.windll.user32.MessageBoxW(None, message, title, flags | 0x40000)  # MB_TOPMOST
        elif sys.platform == "darwin":
            def esc(s: str) -> str:
                return s.replace("\\", "\\\\").replace('"', '\\"')

            icon = "stop" if error else "note"
            subprocess.Popen(["osascript", "-e",
                              f'display dialog "{esc(message)}" with title "{esc(title)}" '
                              f'buttons {{"OK"}} default button "OK" with icon {icon}'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        log.exception("ダイアログを表示できませんでした")


def tray_location_hint() -> str:
    if sys.platform == "darwin":
        return "画面右上のメニューバーにアイコンがあります。"
    return "画面右下の通知領域（タスクバーの「^」の中）にアイコンがあります。"


def open_path(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        log.exception("ファイルを開けませんでした: %s", path)


# --- launch at login -------------------------------------------------------

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _mac_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"


def autostart_supported() -> bool:
    return sys.platform in ("win32", "darwin")


def autostart_enabled() -> bool:
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        if sys.platform == "darwin":
            return _mac_agent_path().exists()
    except OSError:
        return False
    return False


def set_autostart(enabled: bool) -> None:
    cmd = launch_command()
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                if enabled:
                    value = subprocess.list2cmdline(cmd)
                    winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, value)
                else:
                    try:
                        winreg.DeleteValue(k, APP_NAME)
                    except FileNotFoundError:
                        pass
        elif sys.platform == "darwin":
            path = _mac_agent_path()
            if enabled:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "wb") as f:
                    plistlib.dump({"Label": APP_ID, "ProgramArguments": cmd, "RunAtLoad": True,
                                   "ProcessType": "Interactive"}, f)
            else:
                path.unlink(missing_ok=True)
    except Exception:
        log.exception("ログイン時起動の設定に失敗しました")


# --- migration from the previous name (SplitBattery) ------------------------

_OLD_NAME = "SplitBattery"
_OLD_ID = "io.github.kyonccc.splitbattery"


def migrate_from_old_name() -> None:
    """Carry settings over from SplitBattery and replace its login item."""
    from .config import app_dir

    try:
        new_cfg = app_dir() / "config.json"
        old_cfg = app_dir().parent / _OLD_NAME / "config.json"
        if not new_cfg.exists() and old_cfg.exists():
            new_cfg.write_bytes(old_cfg.read_bytes())
            log.info("SplitBattery の設定を引き継ぎました")
    except Exception:
        log.exception("旧設定の引き継ぎに失敗しました")

    had_old_autostart = False
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
                try:
                    winreg.QueryValueEx(k, _OLD_NAME)
                    winreg.DeleteValue(k, _OLD_NAME)
                    had_old_autostart = True
                except FileNotFoundError:
                    pass
        elif sys.platform == "darwin":
            old = _mac_agent_path().with_name(f"{_OLD_ID}.plist")
            if old.exists():
                old.unlink()
                had_old_autostart = True
    except Exception:
        log.exception("旧ログイン項目の削除に失敗しました")
    if had_old_autostart:
        log.info("SplitBattery のログイン時起動を Kataware に置き換えました")
        set_autostart(True)
