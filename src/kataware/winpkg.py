"""Running as an MSIX package (the Microsoft Store build) on Windows.

A packaged desktop app gets a private view of the registry and of %APPDATA%,
so the unpackaged build's ways of launching at login (the HKCU Run key) and of
storing files would silently not work there. When packaged we use the
package's own storage folder (LocalState) and the StartupTask declared in the
package manifest instead.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

STARTUP_TASK_ID = "KatawareStartup"

_ERROR_INSUFFICIENT_BUFFER = 122


@lru_cache(maxsize=1)
def package_family_name() -> str | None:
    """The package family name, or None when not running from a package."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        fn = ctypes.windll.kernel32.GetCurrentPackageFamilyName
        length = ctypes.c_uint32(0)
        if fn(ctypes.byref(length), None) != _ERROR_INSUFFICIENT_BUFFER:
            return None  # APPMODEL_ERROR_NO_PACKAGE: a normal .exe
        buf = ctypes.create_unicode_buffer(length.value)
        if fn(ctypes.byref(length), buf) != 0:
            return None
        return buf.value or None
    except Exception:
        return None


def is_packaged() -> bool:
    return package_family_name() is not None


def local_state_dir() -> Path:
    """The package's LocalState folder: not virtualized, so other programs
    (e.g. Notepad opening the log) see the same files, and Windows removes it
    when the app is uninstalled."""
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Packages" / package_family_name() / "LocalState"


# --- StartupTask (launch at login for packaged apps) -----------------------

_STATES = {0: "disabled", 1: "disabled_by_user", 2: "enabled", 3: "disabled_by_policy", 4: "enabled_by_policy"}
_cache: tuple[float, str] | None = None
_cache_lock = threading.Lock()


def _run(coro_factory, timeout: float = 10.0):
    """Run a WinRT coroutine on a private event loop in a helper thread, so it
    can be called from the UI thread or the monitor thread alike."""
    result: dict = {}

    def worker():
        try:
            result["value"] = asyncio.run(asyncio.wait_for(coro_factory(), timeout))
        except BaseException as e:  # reported to the caller below
            result["error"] = e

    t = threading.Thread(target=worker, name="startup-task", daemon=True)
    t.start()
    t.join(timeout + 2)
    if "error" in result:
        raise result["error"]
    if "value" not in result:
        raise TimeoutError("StartupTask did not answer")
    return result["value"]


async def _get_task():
    from winrt.windows.applicationmodel import StartupTask

    return await StartupTask.get_async(STARTUP_TASK_ID)


def startup_state(force: bool = False) -> str:
    """'enabled', 'disabled', 'disabled_by_user', 'disabled_by_policy',
    'enabled_by_policy', or 'unavailable' (not packaged / API failure)."""
    global _cache
    if not is_packaged():
        return "unavailable"
    with _cache_lock:
        if not force and _cache and time.monotonic() - _cache[0] < 30:
            return _cache[1]
    try:
        task = _run(_get_task)
        state = _STATES.get(int(task.state), "disabled")
    except Exception as e:
        log.warning("スタートアップ タスクを取得できません: %r", e)
        state = "unavailable"
    with _cache_lock:
        _cache = (time.monotonic(), state)
    return state


def set_startup(enabled: bool) -> str:
    """Enable / disable launching at login; returns the resulting state."""
    global _cache

    async def change():
        task = await _get_task()
        if enabled:
            return int(await task.request_enable_async())
        task.disable()
        return int(task.state)

    try:
        state = _STATES.get(_run(change), "disabled")
    except Exception as e:
        log.warning("スタートアップ タスクを変更できません: %r", e)
        state = "unavailable"
    with _cache_lock:
        _cache = (time.monotonic(), state)
    return state
