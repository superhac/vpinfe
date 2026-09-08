# -*- mode: python ; coding: utf-8 -*-
"""What a VPinFE build contains, for every platform and both variants.

PyInstaller follows imports on its own but cannot see data files, so anything that is not
Python has to be named here or it will not be in the artifact. Nothing in the test suite
checks that: a path that is wrong reaches a user as a missing splash screen or a dark DMD
panel, never as a red build.

This replaces five near-identical `pyinstaller` command lines that between them repeated
six facts twenty-six times, in two separator dialects - `:` on POSIX and `;` on Windows,
which exists only because a shell has to squeeze a pair into one string. A spec is Python,
so a pair is a tuple and the separator problem does not exist.

Two axes, and only two:

    platform   Linux and Windows each bundle their own Chromium; macOS copies one into
               the .app after the build, so it is not listed here. Linux needs pynput's
               X11 backends named because PyInstaller ships no hook for them.
    variant    slim is the same build without Chromium. VPINFE_SLIM=1 selects it.

Run it the same way everywhere:

    pyinstaller packaging/vpinfe.spec                  # full
    VPINFE_SLIM=1 pyinstaller packaging/vpinfe.spec    # slim
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(SPECPATH).parent
SLIM = os.environ.get("VPINFE_SLIM") == "1"

IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# Every directory we ship, whatever the platform or variant. Each is a data root in its
# own right - either a top-level one, or an <owner>/static/ directory belonging to the
# subsystem that reads it. `third_party/` is fetched by scripts/ before the build, not
# committed; the rest are in git.
DATA_ROOTS = [
    "frontend/static",
    "managerui/static",
    "common/host/static",
    "third_party/dof",
    "third_party/libdmdutil",
]

# Chromium is the only difference between a full build and a slim one. macOS is absent on
# purpose: its Chromium.app is copied into the bundle's Frameworks after PyInstaller runs,
# because an .app inside --add-data loses the executable bit and the symlinks it needs.
if not SLIM:
    if IS_LINUX:
        DATA_ROOTS.append("chromium/linux/chrome")
    elif IS_WINDOWS:
        DATA_ROOTS.append("chromium/windows")

datas = [(str(REPO_ROOT / root), root) for root in DATA_ROOTS]

# PyInstaller ships no pynput hook, so the backend it loads by name at runtime is invisible
# to the import scan. Only X11 matters: the Windows and macOS backends are imported
# normally.
hiddenimports = ["pynput.keyboard._xorg", "pynput.mouse._xorg"] if IS_LINUX else []

analysis = Analysis(
    [str(REPO_ROOT / "main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

# macOS ships an .app the user double-clicks, so the name is the one that shows in the
# Dock. Everywhere else the name is the binary on the command line.
APP_NAME = "VPinFE" if IS_MACOS else "vpinfe"

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # A windowed macOS build has no console; the other platforms keep one, and the
    # Windows launcher hides it when VPinFE is started from its .bat rather than a shell.
    console=not IS_MACOS,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(REPO_ROOT / "packaging" / "VPinFE.icns") if IS_MACOS else None,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

if IS_MACOS:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(REPO_ROOT / "packaging" / "VPinFE.icns"),
        bundle_identifier="com.vpinfe.main",
    )
