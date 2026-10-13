"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
import threading
import time
import traceback
from pathlib import Path

from . import __version__
from .config import setup_logging

log = logging.getLogger(__name__)


def _print(*args) -> None:
    if sys.stdout is not None:  # windowed builds have no console
        print(*args, flush=True)


def _single_instance() -> object | None:
    """Prevent two copies fighting over the same tray slot / Bluetooth reads."""
    try:
        if sys.platform == "win32":
            import ctypes

            handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\KatawareBatteryMonitor")
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                return None
            return handle
        import fcntl

        from .config import app_dir

        f = open(app_dir() / ".lock", "w")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        return None
    except Exception:
        return True  # never refuse to start because of the lock itself


def read_once(demo: bool) -> int:
    from .backends import BackendUnavailable, create_backend
    from .models import format_level, label_cells

    try:
        backend = create_backend(demo)
        devices = backend.read_all()
        backend.close()
    except BackendUnavailable as e:
        _print(f"Bluetooth 利用不可: {e}")
        return 2
    if not devices:
        _print("バッテリー情報を持つ接続中の Bluetooth 機器はありません")
    for d in devices:
        levels = ", ".join(f"{lv.label} {format_level(lv.level)}" for lv in label_cells(d))
        _print(f"{d.name}: {levels} {d.error}".rstrip())
        for c in d.cells:
            _print(f"    handle=0x{c.handle:04x} level={c.level} description={c.description!r}")
    return 0


def self_test(report_path: Path, seconds: float) -> int:
    """Smoke test used by CI on the real Windows / macOS builds."""
    report: dict = {"version": __version__, "platform": platform.platform(), "python": sys.version,
                    "frozen": bool(getattr(sys, "frozen", False)), "steps": {}}
    ok = True

    def step(name, fn):
        nonlocal ok
        try:
            report["steps"][name] = {"ok": True, "detail": fn()}
        except Exception:
            ok = False
            report["steps"][name] = {"ok": False, "detail": traceback.format_exc()}

    def icons():
        from .icon import render_icon
        from .models import LabeledLevel

        img = render_icon([LabeledLevel("左", "L", 80), LabeledLevel("右", "R", 15)])
        img2 = render_icon([LabeledLevel("左", "L", 80), LabeledLevel("右", "R", None)], "bars")
        assert img.size == (64, 64) and img2.size == (64, 64)
        return "ok"

    def real_backend():
        # Real Bluetooth stack: CI machines usually have no radio, so
        # "unavailable" is an expected, *handled* outcome. Anything else that
        # raises (import errors, API mismatches) fails the test.
        from .backends import BackendUnavailable, create_backend

        result: dict = {}

        def worker():
            try:
                b = create_backend(False)
                result["backend"] = b.name
                result["probe"] = b.probe()
                try:
                    devs = b.read_all()
                    result["devices"] = [(d.name, [c.level for c in d.cells], d.error) for d in devs]
                finally:
                    b.close()
            except BackendUnavailable as e:
                result["unavailable"] = str(e)
            except BaseException:
                result["error"] = traceback.format_exc()

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(90)
        if t.is_alive():
            raise TimeoutError("backend did not return within 90s")
        if "error" in result:
            raise RuntimeError(result["error"])
        return result

    def tray():
        from .app import TrayApp
        from .config import SettingsStore

        app = TrayApp(demo=True, store=SettingsStore(report_path.parent / "selftest-config.json"))
        start = time.monotonic()
        app.run(auto_exit_seconds=seconds)
        elapsed = time.monotonic() - start
        assert app.monitor.polls >= 1, "monitor never polled"
        items = list(app._menu_items())
        texts = [str(getattr(i, "text", "")) for i in items]
        assert any("moNa2" in t for t in texts), texts
        assert any("左: " in t for t in texts) and any("右: " in t for t in texts), texts
        return {"elapsed": round(elapsed, 1), "polls": app.monitor.polls, "menu": texts,
                "tooltip": app.icon.title}

    step("icons", icons)
    step("real_backend", real_backend)
    step("tray", tray)
    report["ok"] = ok
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="Kataware", description="Bluetooth battery monitor")
    p.add_argument("--demo", action="store_true", help="Bluetooth を使わずデモデータで起動")
    p.add_argument("--once", action="store_true", help="一度だけ読み取って結果を表示")
    p.add_argument("--self-test", metavar="REPORT", help="動作確認を実行して JSON レポートを書き出す")
    p.add_argument("--self-test-seconds", type=float, default=8.0)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--version", action="version", version=__version__)
    # macOS passes -psn_XXX when launched from Finder on old systems
    args, _unknown = p.parse_known_args(argv)

    setup_logging(args.verbose)
    log.info("Kataware %s を起動 (%s)", __version__, platform.platform())

    if args.self_test:
        return self_test(Path(args.self_test).resolve(), args.self_test_seconds)
    if args.once:
        return read_once(args.demo)

    from .config import APP_NAME, log_path
    from .platform_utils import migrate_from_old_name, refresh_autostart_path, show_message, tray_location_hint

    lock = _single_instance()
    if lock is None:
        log.info("既に起動しています")
        show_message(APP_NAME, f"{APP_NAME} は既に起動しています。\n{tray_location_hint()}")
        return 0
    migrate_from_old_name()
    refresh_autostart_path()
    try:
        from .app import TrayApp

        TrayApp(demo=args.demo).run()
    except Exception as e:
        log.exception("アプリが異常終了しました")
        show_message(APP_NAME, f"{APP_NAME} を起動できませんでした。\n\n{e}\n\nログ: {log_path()}", error=True)
        return 1
    return 0
