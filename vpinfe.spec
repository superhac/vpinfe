# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

# Determine platform-specific settings
is_windows = sys.platform.startswith('win')
is_mac = sys.platform == 'darwin'
is_linux = sys.platform.startswith('linux')

# Main analysis
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('web', 'web'),
        ('managerui/static', 'managerui/static'),
    ],
    hiddenimports=[
        'webview',
        'nicegui',
        'screeninfo',
        'olefile',
        'pynput',
        'pynput.keyboard',
        'pynput.keyboard._xorg',
        'pynput.mouse',
        'pynput.mouse._xorg',
        'platformdirs',
        'requests',
        'uvicorn',
        'starlette',
        'httpx',
        'httpcore',
        # NiceGUI dependencies
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # Webview platform-specific
        'webview.platforms',
        'webview.platforms.gtk',
        'webview.platforms.cocoa',
        'webview.platforms.cef',
        'webview.platforms.edgechromium',
        # Application modules
        'frontend.customhttpserver',
        'frontend.api',
        'common.iniconfig',
        'common.vpsdb',
        'common.vpxcollections',
        'common.metaconfig',
        'common.table',
        'common.standalonescripts',
        'common.vpxparser',
        'common.tableparser',
        'common.tablelistfilters',
        'managerui.managerui',
        'managerui.binders',
        'managerui.ini_store',
        'managerui.nvram_parser',
        'managerui.schema',
        'managerui.pages.buttons',
        'managerui.pages.nudge',
        'managerui.pages.highscores',
        'managerui.pages.plugins',
        'managerui.pages.video',
        'clioptions',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_gi_system.py'],
    excludes=[
        'gi',
        'gi.repository',
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='vpinfe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Set to False for GUI-only app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path if you have one: 'web/images/VPinFE_logo_main.png'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='vpinfe',
)
