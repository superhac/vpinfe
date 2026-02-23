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
from platformdirs import user_config_dir
from common.themes import ThemeRegistry

#debug
import sys
from common.vpxcollections import VPXCollections
from common.tableparser import TableParser

# Get the base path
base_path = os.path.dirname(os.path.abspath(__file__))

# Load config BEFORE importing clioptions/managerui (they create IniConfig at import time)
config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
config_dir.mkdir(parents=True, exist_ok=True)
config_path = config_dir / "vpinfe.ini"
iniconfig = IniConfig(str(config_path))

# Now safe to import modules that create their own IniConfig at import time
from clioptions import parseArgs
from managerui.managerui import start_manager_ui, stop_manager_ui, set_first_run, _shutdown_event
from nicegui import app as nicegui_app

nicegui_app.add_static_files('/static', os.path.join(base_path, 'managerui/static'))
html_file = Path(base_path) / "web/splash.html"
webview_windows = [] # [ [window_name, window, api] ]

 # The last window created will be the one in focus.  AKA the controller for all the other windows!!!! Always "table"
import sys
import webview

# Monkey-patch pywebview cocoa backend to handle NSWindow.screen() returning None.
# This happens when a window is positioned on a different screen from where the app
# launched, causing windowDidMove_ to crash with AttributeError.
if sys.platform == "darwin":
    try:
        from webview.platforms import cocoa as _cocoa_module
        _WinDelegate = _cocoa_module.BrowserView.WindowDelegate
        _orig_windowDidMove_ = _WinDelegate.windowDidMove_

        def _safe_windowDidMove_(self, notification):
            try:
                _orig_windowDidMove_(self, notification)
            except AttributeError:
                pass  # screen() returned None during window positioning

        _WinDelegate.windowDidMove_ = _safe_windowDidMove_
    except Exception:
        pass  # Non-cocoa platform or import issue, skip

def _get_screen_info(screen_id):
    """Get screen position/size and optional pywebview Screen object for a given screen ID.

    On macOS, uses pywebview's native screens (Cocoa coordinate system) to avoid
    coordinate mismatches between screeninfo (top-left origin) and Cocoa (bottom-left origin).
    On other platforms, uses screeninfo.get_monitors().
    """
    if sys.platform == "darwin":
        screens = webview.screens
        if screen_id < len(screens):
            s = screens[screen_id]
            return {"x": 0, "y": 0, "width": s.width, "height": s.height, "screen": s}
        else:
            print(f"[WARN] Screen ID {screen_id} not found in webview.screens (have {len(screens)}), falling back to screen 0")
            s = screens[0]
            return {"x": 0, "y": 0, "width": s.width, "height": s.height, "screen": s}
    else:
        monitors = get_monitors()
        m = monitors[screen_id]
        return {"x": m.x, "y": m.y, "width": m.width, "height": m.height, "screen": None}


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

    # First-run: show manager UI config page in the table window instead of theme
    if iniconfig.is_new:
        manager_ui_port = int(iniconfig.config['Network'].get('manageruiport', '8001'))
        setup_url = f'http://localhost:{manager_ui_port}/'
        screen_id = int(iniconfig.config['Displays'].get('tablescreenid', '0'))
        scr = _get_screen_info(screen_id)
        print(f"[VPinFE] First run — loading Manager UI in table window for initial configuration.")

        win = webview.create_window(
            "VPinFE Setup",
            url=setup_url,
            x=scr["x"],
            y=scr["y"],
            width=scr["width"],
            height=scr["height"],
            screen=scr["screen"],
            background_color="#0f172a",
        )
        webview_windows.append(['table', win, None])
        return

    # --- BG SCREEN ---
    if iniconfig.config['Displays']['bgscreenid']:
        screen_id = int(iniconfig.config['Displays']['bgscreenid'])
        scr = _get_screen_info(screen_id)
        api = API(iniconfig)

        win = webview.create_window(
            "BG Screen",
            url=f"file://{html_file.resolve()}",
            js_api=api,
            x=scr["x"],
            y=scr["y"],
            width=scr["width"],
            height=scr["height"],
            screen=scr["screen"],
            background_color="#000000",
            fullscreen=window_flags["fullscreen"],
            frameless=window_flags["frameless"],
            resizable=window_flags["resizable"],
        )

        api.myWindow.append(win)
        webview_windows.append(['bg', win, api])
        api.webview_windows = webview_windows
        api._iniConfig = iniconfig
        api._finish_setup()

    # --- DMD SCREEN ---
    if iniconfig.config['Displays']['dmdscreenid']:
        screen_id = int(iniconfig.config['Displays']['dmdscreenid'])
        scr = _get_screen_info(screen_id)
        api = API(iniconfig)

        win = webview.create_window(
            "DMD Screen",
            url=f"file://{html_file.resolve()}",
            js_api=api,
            x=scr["x"],
            y=scr["y"],
            width=scr["width"],
            height=scr["height"],
            screen=scr["screen"],
            background_color="#000000",
            fullscreen=window_flags["fullscreen"],
            frameless=window_flags["frameless"],
            resizable=window_flags["resizable"],
        )

        api.myWindow.append(win)
        webview_windows.append(['dmd', win, api])
        api.webview_windows = webview_windows
        api._iniConfig = iniconfig
        api._finish_setup()

    # --- TABLE SCREEN ---
    if sys.platform == "darwin" or sys.platform == "win32" or not webview_windows:
        # On macOS/Windows, or when table is the only window (single-screen),
        # create the table window before starting the webview loop.
        if iniconfig.config['Displays']['tablescreenid']:
            screen_id = int(iniconfig.config['Displays']['tablescreenid'])
            scr = _get_screen_info(screen_id)
            api = API(iniconfig)

            win = webview.create_window(
                "Table Screen",
                url=f"file://{html_file.resolve()}",
                js_api=api,
                x=scr["x"],
                y=scr["y"],
                width=scr["width"],
                height=scr["height"],
                screen=scr["screen"],
                background_color="#000000",
                fullscreen=window_flags["fullscreen"],
                frameless=True, # Always frameless on mac
                resizable=window_flags["resizable"],
            )

            api.myWindow.append(win)
            webview_windows.append(['table', win, api])
            api.webview_windows = webview_windows
            api._iniConfig = iniconfig
            api._finish_setup()
    else:
        # On Linux, the table window is created after webview.start()
        # via _create_table_window() to ensure it appears on top with focus.
        pass


headless = False
if len(sys.argv) > 0:
    cli_args = parseArgs()
    if cli_args and cli_args.headless:
        headless = True

# On first run, start the manager UI early so the webview can load it
if iniconfig.is_new:
    import time
    set_first_run(True)
    manager_ui_port = int(iniconfig.config['Network'].get('manageruiport', '8001'))
    start_manager_ui(port=manager_ui_port)
    # Wait for the NiceGUI server to be ready before webview tries to load it
    for _attempt in range(30):
        try:
            import urllib.request as _ur
            _ur.urlopen(f'http://localhost:{manager_ui_port}/api/remote-launch', timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    print(f"[VPinFE] First run — Manager UI ready on port {manager_ui_port}")

# Initialize theme registry and auto-install default themes
try:
    theme_registry = ThemeRegistry()
    theme_registry.load_registry()
    theme_registry.load_theme_manifests()
    theme_registry.auto_install_defaults()
except Exception as e:
    print(f"[WARN] Theme registry initialization failed: {e}")

# Initialize webview windows
if not headless:
    loadWindows()

# Start an the HTTP server to serve the images from the "tables" directory
themes_dir = str(config_dir / "themes")
os.makedirs(themes_dir, exist_ok=True)
nicegui_app.add_static_files('/themes', themes_dir)

MOUNT_POINTS = {
        '/web/': os.path.join(base_path, 'web'),
        '/themes/': themes_dir,
        }
table_root = iniconfig.config['Settings']['tablerootdir']
if table_root:
    MOUNT_POINTS['/tables/'] = os.path.abspath(table_root)
http_server = CustomHTTPServer(MOUNT_POINTS)
theme_assets_port = int(iniconfig.config['Network'].get('themeassetsport', '8000'))
http_server.start_file_server(port=theme_assets_port)

# Start the NiceGUI HTTP server
manager_ui_port = int(iniconfig.config['Network'].get('manageruiport', '8001'))
start_manager_ui(port=manager_ui_port)

# Windows CTRL-C workaround: Python's signal module cannot interrupt native GUI
# loops, so we use the Win32 SetConsoleCtrlHandler API which runs on its own OS thread.
if sys.platform == "win32":
    import ctypes
    def _console_ctrl_handler(ctrl_type):
        if ctrl_type == 0:  # CTRL_C_EVENT
            print("\n[VPinFE] Shutting down...")
            try:
                http_server.on_closed()
            except Exception:
                pass
            try:
                nicegui_app.shutdown()
                stop_manager_ui()
            except Exception:
                pass
            os._exit(0)
        return False
    _handler_func = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)(_console_ctrl_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler_func, True)

if headless:
    print(f"[VPinFE] Running in headless mode (no frontend)")
    print(f"[VPinFE] Theme assets server on port {theme_assets_port}")
    print(f"[VPinFE] Manager UI on port {manager_ui_port}")
    print(f"[VPinFE] Press Ctrl+C to stop")
    try:
        _shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    print("\n[VPinFE] Shutting down...")
else:
    def _create_table_window():
        """Create the table window after a delay so it appears on top with focus."""
        global webview_windows
        import time
        time.sleep(.5)  # delay to ensure this runs after the initial windows are created

        if not iniconfig.config['Displays']['tablescreenid']:
            return

        screen_id = int(iniconfig.config['Displays']['tablescreenid'])
        scr = _get_screen_info(screen_id)
        api = API(iniconfig)

        win = webview.create_window(
            "Table Screen",
            url=f"file://{html_file.resolve()}",
            js_api=api,
            x=scr["x"],
            y=scr["y"],
            width=scr["width"],
            height=scr["height"],
            screen=scr["screen"],
            background_color="#000000",
            fullscreen=True,
            frameless=False,
            resizable=True,
        )

        api.myWindow.append(win)
        webview_windows.append(['table', win, api])
        api.webview_windows = webview_windows
        api._iniConfig = iniconfig
        api._finish_setup()

    def _focus_table_window():
        """macOS: ensure focus goes to the table window regardless of launch screen."""
        import time
        time.sleep(0.5)
        try:
            import AppKit
            AppKit.NSApp.activateIgnoringOtherApps_(True)
            for win_name, window, api in webview_windows:
                if win_name == 'table':
                    window.show()
                    break
        except Exception:
            pass

    def _on_webview_started():
        """Create the table window after webview starts (Linux multi-screen only)."""
        if sys.platform == "linux" and not any(w[0] == 'table' for w in webview_windows):
            threading.Thread(target=_create_table_window, daemon=True).start()
        if sys.platform == "darwin":
            threading.Thread(target=_focus_table_window, daemon=True).start()

    # Ensure at least one window was created before starting webview
    if not webview_windows:
        print("[ERROR] No display windows configured. Check your vpinfe.ini [Displays] section.")
        print("[ERROR] At minimum, 'tablescreenid' must be set (e.g. tablescreenid = 0).")
        sys.exit(1)

    # block and start webview
    if sys.platform == "darwin":
        webview.start(func=_on_webview_started, gui="cocoa")
    else:
        webview.start(func=_on_webview_started)

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
