#!/usr/bin/env python3

import sys
import os

# Windows --noconsole: stdout/stderr are None, redirect to devnull so print() doesn't crash
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

import multiprocessing
multiprocessing.freeze_support()

from pathlib import Path
from frontend.customhttpserver import CustomHTTPServer
from frontend.api import API
from frontend.ws_bridge import WebSocketBridge
from frontend.chromium_manager import ChromiumManager
from common.iniconfig import IniConfig
from clioptions import parseArgs
from managerui.managerui import start_manager_ui, stop_manager_ui
from nicegui import app as nicegui_app
from platformdirs import user_config_dir
from common.themes import ThemeRegistry

# Get the base path
base_path = os.path.dirname(os.path.abspath(__file__))

nicegui_app.add_static_files('/static', os.path.join(base_path, 'managerui/static'))

# Use platform-specific config directory
config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
config_dir.mkdir(parents=True, exist_ok=True)
config_path = config_dir / "vpinfe.ini"
iniconfig = IniConfig(str(config_path))

# Shared instances accessible from other modules (e.g. remote.py)
ws_bridge = None
chromium_manager = None


def create_api_instances():
    """Create API instances for each configured display window."""
    global ws_bridge, chromium_manager

    ws_bridge = WebSocketBridge(
        port=int(iniconfig.config['Network'].get('wsport', '8002'))
    )
    chromium_manager = ChromiumManager()

    # Window configs: (window_name, config_key)
    window_configs = [
        ('bg', 'bgscreenid'),
        ('dmd', 'dmdscreenid'),
        ('table', 'tablescreenid'),
    ]

    for window_name, config_key in window_configs:
        screen_id_str = iniconfig.config['Displays'].get(config_key, '').strip()
        if not screen_id_str:
            continue

        api = API(
            iniConfig=iniconfig,
            window_name=window_name,
            ws_bridge=ws_bridge,
            chromium_manager=chromium_manager,
        )
        api._finish_setup()
        ws_bridge.register_api(window_name, api)
        print(f"[Main] Registered API for window '{window_name}'")


if len(sys.argv) > 0:
    parseArgs()

# Initialize theme registry and auto-install default themes
try:
    theme_registry = ThemeRegistry()
    theme_registry.load_registry()
    theme_registry.load_theme_manifests()
    theme_registry.auto_install_defaults()
except Exception as e:
    print(f"[WARN] Theme registry initialization failed: {e}")

# Create API instances and register with WebSocket bridge
create_api_instances()

# Start the HTTP server to serve images from the "tables" directory
themes_dir = str(config_dir / "themes")
os.makedirs(themes_dir, exist_ok=True)
nicegui_app.add_static_files('/themes', themes_dir)

MOUNT_POINTS = {
        '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
        '/web/': os.path.join(base_path, 'web'),
        '/themes/': themes_dir,
        }
http_server = CustomHTTPServer(MOUNT_POINTS)
theme_assets_port = int(iniconfig.config['Network'].get('themeassetsport', '8000'))
http_server.start_file_server(port=theme_assets_port)

# Start the NiceGUI HTTP server
manager_ui_port = int(iniconfig.config['Network'].get('manageruiport', '8001'))
start_manager_ui(port=manager_ui_port)

# Start the WebSocket bridge
ws_bridge.start()

# Launch Chromium windows on configured monitors
chromium_manager.launch_all_windows(iniconfig)

# Block until Chromium windows exit (replaces webview.start())
chromium_manager.wait_for_exit()

# Shutdown items
ws_bridge.stop()
http_server.on_closed()
nicegui_app.shutdown()
stop_manager_ui()

# Check for restart sentinel
restart_flag = config_dir / '.restart'
if restart_flag.exists():
    restart_flag.unlink()
    print("[VPinFE] Restart requested, re-launching...")
    import time
    time.sleep(1)  # Allow OS to release sockets before rebinding
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle: just re-exec the bundled executable
        os.execvp(sys.executable, [sys.executable])
    else:
        # Dev mode: re-exec with Python + script
        main_script = os.path.abspath(__file__)
        os.execvp(sys.executable, [sys.executable, main_script])
