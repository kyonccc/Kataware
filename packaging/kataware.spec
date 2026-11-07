# PyInstaller spec for Kataware (Windows .exe / macOS .app)
#
# Windows builds a single .exe for GitHub releases by default. With
# KATAWARE_ONEDIR=1 it builds a folder instead (Kataware.exe + _internal), which
# is what goes into the Microsoft Store (MSIX) package: no self-extraction to
# %TEMP% and no second process at start-up.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "src"))
from kataware import __version__  # noqa: E402

ICONS = Path(SPECPATH) / "build-icons"

hidden = ["kataware.backends.demo"]
if sys.platform == "win32":
    hidden += ["pystray._win32", "kataware.backends.windows"] + collect_submodules("winrt")
elif sys.platform == "darwin":
    hidden += ["pystray._darwin", "kataware.backends.macos", "CoreBluetooth", "libdispatch",
               "PyObjCTools.AppHelper", "PyObjCTools.MachSignals"]

a = Analysis(
    [str(Path(SPECPATH) / "entry.py")],
    pathex=[str(ROOT / "src")],
    hiddenimports=hidden,
    datas=[(str(ROOT / "src" / "kataware" / "assets"), "kataware/assets")],
    excludes=["tkinter", "unittest", "pytest"],
)
pyz = PYZ(a.pure)

if sys.platform == "win32" and os.environ.get("KATAWARE_ONEDIR") == "1":
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="Kataware",
        console=False,
        upx=False,
        icon=str(ICONS / "app.ico"),
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="Kataware", upx=False)
elif sys.platform == "win32":
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="Kataware",
        console=False,
        upx=False,
        icon=str(ICONS / "app.ico"),
    )
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="Kataware",
        console=False,
        upx=False,
        icon=str(ICONS / "app.icns"),
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="Kataware", upx=False)
    app = BUNDLE(
        coll,
        name="Kataware.app",
        icon=str(ICONS / "app.icns"),
        bundle_identifier="io.github.kyonccc.kataware",
        version=__version__,
        info_plist={
            "CFBundleName": "Kataware",
            "CFBundleDisplayName": "Kataware",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSUIElement": True,  # menu bar only, no Dock icon
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSBluetoothAlwaysUsageDescription":
                "接続中のキーボードなど Bluetooth 機器のバッテリー残量を読み取るために使用します。",
            "NSBluetoothPeripheralUsageDescription":
                "接続中のキーボードなど Bluetooth 機器のバッテリー残量を読み取るために使用します。",
        },
    )
