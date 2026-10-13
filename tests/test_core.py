import json

from kataware.backends.demo import DemoBackend
from kataware.config import SettingsStore
from kataware.icon import render_icon
from kataware.models import BatteryCell, DeviceBattery, label_cells
from kataware.monitor import Monitor, MonitorState
from kataware.backends import BackendUnavailable


def zmk(left=80, right=60, desc="Peripheral 0"):
    return DeviceBattery("kb", "moNa2", [BatteryCell(right, desc, 0x20), BatteryCell(left, "", 0x10)])


def test_zmk_central_left_by_default():
    labels = label_cells(zmk(80, 60))
    assert [(l.label, l.level) for l in labels] == [("左", 80), ("右", 60)]


def test_zmk_central_right():
    labels = label_cells(zmk(80, 60), "right")
    # central (handle 0x10, level 80) is now the right half
    assert [(l.label, l.level) for l in labels] == [("左", 60), ("右", 80)]


def test_split_without_descriptions_uses_handle_order():
    dev = DeviceBattery("kb", "kb", [BatteryCell(50, "", 0x30), BatteryCell(90, "", 0x10)])
    assert [(l.label, l.level) for l in label_cells(dev)] == [("左", 90), ("右", 50)]


def test_single_battery_device():
    dev = DeviceBattery("m", "mouse", [BatteryCell(42, "", 1)])
    assert [(l.label, l.level) for l in label_cells(dev)] == [("本体", 42)]


def test_multiple_peripherals():
    dev = DeviceBattery("kb", "kb", [BatteryCell(1, "", 1), BatteryCell(2, "Peripheral 0", 2),
                                     BatteryCell(3, "Peripheral 1", 3)])
    assert [l.label for l in label_cells(dev)] == ["左", "ペリフェラル 0", "ペリフェラル 1"]


def test_icons_render_all_states():
    for style in ("numbers", "bars"):
        for dev in (zmk(), zmk(None, 5), DeviceBattery("x", "x", [BatteryCell(100, "", 1)])):
            img = render_icon(label_cells(dev), style)
            assert img.size == (64, 64)
    assert render_icon([], "numbers").size == (64, 64)
    assert render_icon(label_cells(zmk()), "numbers", connected=False).size == (64, 64)


def test_settings_roundtrip_and_corrupt_file(tmp_path):
    path = tmp_path / "config.json"
    store = SettingsStore(path)
    store.settings.central_side["kb"] = "right"
    store.settings.poll_minutes = 15
    store.save()
    again = SettingsStore(path)
    assert again.settings.central_side == {"kb": "right"}
    assert again.settings.poll_minutes == 15
    path.write_text("{not json", encoding="utf-8")
    assert SettingsStore(path).settings.poll_minutes == 5
    path.write_text(json.dumps({"icon_style": "weird", "unknown": 1}), encoding="utf-8")
    assert SettingsStore(path).settings.icon_style == "numbers"


def test_low_battery_alert_once_with_hysteresis(tmp_path):
    state = MonitorState(SettingsStore(tmp_path / "c.json"))
    assert [a.label for a in state.apply([zmk(80, 15)])] == ["右"]
    assert state.apply([zmk(80, 14)]) == []  # already alerted
    assert state.apply([zmk(80, 23)]) == []  # within hysteresis
    assert state.apply([zmk(80, 50)]) == []  # recharged -> re-armed
    assert [a.level for a in state.apply([zmk(80, 19)])] == [19]


def test_disconnected_device_keeps_last_values(tmp_path):
    state = MonitorState(SettingsStore(tmp_path / "c.json"))
    state.apply([zmk(70, 60)])
    state.apply([])
    dev = state.devices["kb"]
    assert not dev.connected and [c.level for c in dev.cells] == [60, 70]


def test_error_reading_keeps_last_values(tmp_path):
    state = MonitorState(SettingsStore(tmp_path / "c.json"))
    state.apply([zmk(70, 60)])
    state.apply([DeviceBattery("kb", "moNa2", error="timeout")])
    dev = state.devices["kb"]
    assert dev.error == "timeout" and len(dev.cells) == 2


def test_monitor_survives_backend_failures(tmp_path):
    state = MonitorState(SettingsStore(tmp_path / "c.json"))
    calls = {"n": 0}

    class Flaky(DemoBackend):
        def read_all(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise BackendUnavailable("Bluetooth がオフになっています")
            if calls["n"] == 2:
                raise RuntimeError("boom")
            return super().read_all()

    m = Monitor(state, lambda alerts: None, backend_factory=Flaky)
    m.poll_once()
    assert not m.ok and "オフ" in state.status
    m.poll_once()
    assert not m.ok and m.backend is None
    m.poll_once()
    assert m.ok and state.status == "" and "demo-mona2" in state.devices


def test_settings_migrated_from_splitbattery(tmp_path, monkeypatch):
    from kataware.platform_utils import migrate_from_old_name

    old = tmp_path / "SplitBattery"
    old.mkdir()
    (old / "config.json").write_text('{"central_side": {"kb": "right"}}', encoding="utf-8")
    monkeypatch.setenv("KATAWARE_HOME", str(tmp_path / "Kataware"))
    migrate_from_old_name()
    assert SettingsStore(tmp_path / "Kataware" / "config.json").settings.central_side == {"kb": "right"}
