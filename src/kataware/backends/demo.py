"""Fake devices for trying the UI without Bluetooth hardware (``--demo``)."""

from __future__ import annotations

import random

from ..models import BatteryCell, DeviceBattery
from . import Backend


class DemoBackend(Backend):
    name = "demo"

    def __init__(self):
        self._left = 87
        self._right = 64

    def read_all(self) -> list[DeviceBattery]:
        self._left = max(0, self._left - random.randint(0, 2))
        self._right = max(0, self._right - random.randint(0, 3))
        return [
            DeviceBattery(
                device_id="demo-mona2",
                name="moNa2 (デモ)",
                cells=[
                    BatteryCell(self._left, "", 0x10),
                    BatteryCell(self._right, "Peripheral 0", 0x14),
                ],
            ),
            DeviceBattery(device_id="demo-mouse", name="BT Mouse (デモ)", cells=[BatteryCell(55, "", 0x10)]),
        ]
