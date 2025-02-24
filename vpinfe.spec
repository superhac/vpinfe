# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['vpinfe.py'],
    pathex=['vvv/lib/python3.12/site-packages/'],
    binaries=[],
    datas=[('assets', './assets'), ('dlls/SDL2.dll','.')],
    hiddenimports=['screeninfo', 'tkinter', 'PIL', 'PIL._tkinter_finder', 'pysdl2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='vpinfe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
