"""Data types shared between the Bluetooth backends and the UI."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

SIDE_LEFT = "left"
SIDE_RIGHT = "right"

SIDE_NAMES = {SIDE_LEFT: "左", SIDE_RIGHT: "右"}


@dataclass
class BatteryCell:
    """One Battery Level characteristic (0x2A19) found on a device."""

    level: int | None
    description: str = ""
    handle: int = 0


@dataclass
class DeviceBattery:
    """Battery state of one Bluetooth device."""

    device_id: str
    name: str
    cells: list[BatteryCell] = field(default_factory=list)
    connected: bool = True
    error: str = ""
    updated_at: float = field(default_factory=time.time)

    @property
    def is_split(self) -> bool:
        return len(self.cells) >= 2

    @property
    def min_level(self) -> int | None:
        levels = [c.level for c in self.cells if c.level is not None]
        return min(levels) if levels else None


@dataclass
class LabeledLevel:
    label: str
    short: str
    level: int | None


_PERIPHERAL_RE = re.compile(r"peripheral\s*(\d+)", re.IGNORECASE)


def _is_peripheral(cell: BatteryCell) -> bool:
    return bool(_PERIPHERAL_RE.search(cell.description or ""))


def label_cells(device: DeviceBattery, central_side: str = SIDE_LEFT) -> list[LabeledLevel]:
    """Turn raw battery cells into human readable labels.

    ZMK split keyboards expose the central half's battery as the regular
    Battery Level characteristic and each peripheral half's battery as an extra
    Battery Level characteristic whose User Description is "Peripheral N"
    (CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_PROXY). Which physical side is
    the central depends on the firmware, so the user picks it in the menu.
    """
    cells = sorted(device.cells, key=lambda c: c.handle)
    if not cells:
        return []
    if len(cells) == 1:
        return [LabeledLevel("本体", "", cells[0].level)]

    centrals = [c for c in cells if not _is_peripheral(c)]
    peripherals = [c for c in cells if _is_peripheral(c)]
    if not centrals:
        # No description information at all: the first characteristic is
        # registered by ZMK before the proxy characteristics.
        centrals, peripherals = cells[:1], cells[1:]
    elif len(centrals) > 1 and not peripherals:
        centrals, peripherals = cells[:1], cells[1:]

    other_side = SIDE_RIGHT if central_side == SIDE_LEFT else SIDE_LEFT
    result: list[LabeledLevel] = []
    for c in centrals[:1]:
        result.append(LabeledLevel(SIDE_NAMES[central_side], central_side[0].upper(), c.level))
    rest = centrals[1:] + peripherals
    if len(rest) == 1:
        result.append(LabeledLevel(SIDE_NAMES[other_side], other_side[0].upper(), rest[0].level))
    else:
        for i, c in enumerate(rest):
            m = _PERIPHERAL_RE.search(c.description or "")
            n = int(m.group(1)) if m else i
            result.append(LabeledLevel(f"ペリフェラル {n}", f"P{n}", c.level))
    order = {SIDE_NAMES[SIDE_LEFT]: 0, SIDE_NAMES[SIDE_RIGHT]: 1}
    result.sort(key=lambda x: order.get(x.label, 2))
    return result


def format_level(level: int | None) -> str:
    return "--" if level is None else f"{level}%"
