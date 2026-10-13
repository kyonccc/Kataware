"""Bluetooth backends.

Each backend exposes ``read_all() -> list[DeviceBattery]``, a blocking call
that is only ever invoked from the single monitor thread, and ``close()``.
Backends must never let an exception escape for a single misbehaving device;
per-device problems are reported through ``DeviceBattery.error``.
"""

from __future__ import annotations

import sys

from ..models import DeviceBattery

BAS_SERVICE = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
USER_DESCRIPTION = "00002901-0000-1000-8000-00805f9b34fb"


class BackendUnavailable(Exception):
    """Bluetooth cannot be used right now (no adapter, turned off, no permission)."""


class Backend:
    name = "base"

    def read_all(self) -> list[DeviceBattery]:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def start_watching(self, on_change) -> None:
        """Call ``on_change()`` (from any thread) when a device connects or
        disconnects, so the UI can refresh right away. Optional."""

    def probe(self) -> dict:
        """Exercise the OS API surface without needing a radio (used by --self-test)."""
        return {}


def create_backend(demo: bool = False) -> Backend:
    if demo:
        from .demo import DemoBackend

        return DemoBackend()
    if sys.platform == "win32":
        from .windows import WindowsBackend

        return WindowsBackend()
    if sys.platform == "darwin":
        from .macos import MacBackend

        return MacBackend()
    raise BackendUnavailable("この OS には対応していません (Windows / macOS のみ)")
