#!/usr/bin/env python3

import webview
from pathlib import Path
from screeninfo import get_monitors
from frontend.customhttpserver import CustomHTTPServer
from frontend.api import API
import threading
from common.iniconfig import IniConfig
import sys
import os
from clioptions import parseArgs
from managerui.managerui import start_manager_ui, stop_manager_ui
from nicegui import app as nicegui_app
from platformdirs import user_config_dir
from common.themes import ThemeRegistry

#debug
import sys
from common.vpxcollections import VPXCollections
from common.tableparser import TableParser

# Get the base path
base_path = os.path.dirname(os.path.abspath(__file__))

nicegui_app.add_static_files('/static', os.path.join(base_path, 'managerui/static'))
html_file = Path(base_path) / "web/splash.html"
webview_windows = [] # [ [window_name, window, api] ]

# Use platform-specific config directory
config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
config_dir.mkdir(parents=True, exist_ok=True)
config_path = config_dir / "vpinfe.ini"
iniconfig = IniConfig(str(config_path))

 # The last window created will be the one in focus.  AKA the controller for all the other windows!!!! Always "table"
import sys
import webview

def loadWindows():
    global webview_windows
    global api

    monitors = get_monitors()
    print(monitors)

    is_mac = sys.platform == "darwin"

    # macOS-safe window flags
    window_flags = {
        "fullscreen": not is_mac,
        "frameless": is_mac,
        "resizable": False if is_mac else True,
    }

    # --- BG SCREEN ---
    if iniconfig.config['Displays']['bgscreenid']:
        screen_id = int(iniconfig.config['Displays']['bgscreenid'])
        api = API(iniconfig)

        win = webview.create_window(
            "BG Screen",
            url=f"file://{html_file.resolve()}",
            js_api=api,
            x=monitors[screen_id].x,
            y=monitors[screen_id].y,
            width=monitors[screen_id].width,
            height=monitors[screen_id].height,
            background_color="#000000",
            fullscreen=window_flags["fullscreen"],
            frameless=window_flags["frameless"],
            resizable=window_flags["resizable"],
        )

        api.myWindow.append(win)
        webview_windows.append(['bg', win, api])
        api.webview_windows = webview_windows
        api.iniConfig = iniconfig
        api._finish_setup()

    # --- DMD SCREEN ---
    if iniconfig.config['Displays']['dmdscreenid']:
        screen_id = int(iniconfig.config['Displays']['dmdscreenid'])
        api = API(iniconfig)

        win = webview.create_window(
            "DMD Screen",
            url=f"file://{html_file.resolve()}",
            js_api=api,
            x=monitors[screen_id].x,
            y=monitors[screen_id].y,
            width=monitors[screen_id].width,
            height=monitors[screen_id].height,
            background_color="#000000",
            fullscreen=window_flags["fullscreen"],
            frameless=window_flags["frameless"],
            resizable=window_flags["resizable"],
        )

        api.myWindow.append(win)
        webview_windows.append(['dmd', win, api])
        api.webview_windows = webview_windows
        api.iniConfig = iniconfig
        api._finish_setup()

    # --- TABLE SCREEN (ALWAYS LAST) ---
    if iniconfig.config['Displays']['tablescreenid']:
        screen_id = int(iniconfig.config['Displays']['tablescreenid'])
        api = API(iniconfig)

        win = webview.create_window(
            "Table Screen",
            url=f"file://{html_file.resolve()}",
            js_api=api,
            x=monitors[screen_id].x,
            y=monitors[screen_id].y,
            width=monitors[screen_id].width,
            height=monitors[screen_id].height,
            background_color="#000000",
            fullscreen=window_flags["fullscreen"],
            frameless=True if is_mac else False,  # force frameless for table on mac
            resizable=window_flags["resizable"],
        )

        api.myWindow.append(win)
        webview_windows.append(['table', win, api])
        api.webview_windows = webview_windows
        api.iniConfig = iniconfig
        api._finish_setup()


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

# Initialize webview windows
loadWindows()

# Start an the HTTP server to serve the images from the "tables" directory
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

# block and start webview
if sys.platform == "darwin":
    webview.start(gui="cocoa")
else:
    webview.start()

# shutdown items
http_server.on_closed()
nicegui_app.shutdown()
stop_manager_ui()

# Check for restart sentinel
restart_flag = config_dir / '.restart'
if restart_flag.exists():
    restart_flag.unlink()
    print("[VPinFE] Restart requested, re-launching...")
    python_exe = sys.executable
    main_script = os.path.abspath(__file__)
    os.execvp(python_exe, [python_exe, main_script])
