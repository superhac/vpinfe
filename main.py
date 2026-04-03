#!/usr/bin/env python3

from __future__ import annotations

import sys
import os
import platform
import threading
import multiprocessing
multiprocessing.freeze_support()

# On Windows, hide the console window when launched via icon (not from terminal).
# When double-clicked, the process is the sole owner of its console.
# When run from cmd/powershell, multiple processes share the console - don't hide it.
if platform.system() == "Windows" and getattr(sys, 'frozen', False):
    import ctypes
    kernel32 = ctypes.windll.kernel32
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE

from pathlib import Path
from platformdirs import user_config_dir

from common.logging_config import configure_logging, get_logger
from common.iniconfig import IniConfig
from common.dof_service import start_dof_service_if_enabled, stop_dof_service
from common.pinmame_score_parser_updater import ensure_latest_roms_json
from common.vpinplay_service import sync_on_shutdown as vpinplay_sync_on_shutdown
from common.app_version import get_version
from common.themes import ThemeRegistry

# Get the base path
base_path = os.path.dirname(os.path.abspath(__file__))

# Load config BEFORE importing clioptions/managerui (they create IniConfig at import time)
config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
config_dir.mkdir(parents=True, exist_ok=True)
log_path = configure_logging(config_dir, enable_file=False)
config_path = config_dir / "vpinfe.ini"
iniconfig = IniConfig(str(config_path))
log_path = configure_logging(config_dir, iniconfig)
logger = get_logger("vpinfe.main")
logger.info("Logging to %s", log_path)
logger.info("Version: %s", get_version())

try:
    roms_update_result = ensure_latest_roms_json(iniconfig)
    logger.info(
        "pinmame-score-parser roms.json status=%s path=%s",
        roms_update_result.get("status"),
        roms_update_result.get("path"),
    )
except Exception:
    logger.exception("Failed to update pinmame-score-parser roms.json at startup")


def reconfigure_app_logging() -> None:
    configure_logging(config_dir, iniconfig)

# Now safe to import modules that create their own IniConfig at import time
from frontend.customhttpserver import CustomHTTPServer
from frontend.api import API
from frontend.ws_bridge import WebSocketBridge
from frontend.chromium_manager import ChromiumManager
from clioptions import parseArgs, buildMetaData
from managerui.managerui import start_manager_ui, stop_manager_ui, set_first_run, _shutdown_event
from nicegui import app as nicegui_app

nicegui_app.add_static_files('/static', os.path.join(base_path, 'managerui/static'))

# Shared instances accessible from other modules (e.g. remote.py)
ws_bridge = None
frontend_browser = None
_startup_media_sync_started = False


def create_api_instances():
    """Create API instances for each configured display window."""
    global ws_bridge, frontend_browser

    ws_bridge = WebSocketBridge(
        port=int(iniconfig.config['Network'].get('wsport', '8002'))
    )
    frontend_browser = ChromiumManager()

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
            frontend_browser=frontend_browser,
        )
        api._finish_setup()
        ws_bridge.register_api(window_name, api)
        logger.info("Registered API for window '%s'", window_name)


def _start_startup_media_sync():
    """Optionally sync media from VPinMediaDB on startup in a background thread."""
    global _startup_media_sync_started
    if _startup_media_sync_started:
        return

    if iniconfig.is_new:
        logger.info("Skipping startup media sync on first run.")
        return

    try:
        enabled = iniconfig.config.getboolean('Settings', 'autoupdatemediaonstartup', fallback=False)
    except Exception:
        enabled = str(iniconfig.config['Settings'].get('autoupdatemediaonstartup', 'false')).strip().lower() in ('1', 'true', 'yes', 'on')

    if not enabled:
        return

    table_root = iniconfig.config['Settings'].get('tablerootdir', '').strip()
    if not table_root:
        logger.info("Startup media sync enabled, but tablerootdir is empty. Skipping.")
        return

    _startup_media_sync_started = True

    def _worker():
        logger.info("Startup media sync enabled. Checking VPinMediaDB for missing/updated media...")
        try:
            result = buildMetaData(downloadMedia=True, updateAll=True, userMedia=False)
            if isinstance(result, dict):
                found = result.get('found', 0)
                not_found = result.get('not_found', 0)
                logger.info(
                    "Startup media sync complete. Scanned %s table(s); %s not found in VPSdb.",
                    found,
                    not_found,
                )
            else:
                logger.info("Startup media sync complete.")
        except Exception:
            logger.exception("Startup media sync failed")

    threading.Thread(target=_worker, daemon=True, name="startup-media-sync").start()


cli_args = parseArgs() if len(sys.argv) > 0 else None
headless = cli_args and cli_args.headless

# On first run, start the manager UI early so chromium can load it
if iniconfig.is_new:
    import time
    set_first_run(True)
    manager_ui_port = int(iniconfig.config['Network'].get('manageruiport', '8001'))
    start_manager_ui(port=manager_ui_port)
    reconfigure_app_logging()
    # Wait for the NiceGUI server to be ready before chromium tries to load it
    for _attempt in range(30):
        try:
            import urllib.request as _ur
            _ur.urlopen(f'http://localhost:{manager_ui_port}/api/remote-launch', timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    logger.info("First run: Manager UI ready on port %s", manager_ui_port)

# Initialize theme registry and auto-install default themes
try:
    theme_registry = ThemeRegistry()
    theme_registry.load_registry()
    theme_registry.load_theme_manifests(default_only=True)
    theme_registry.auto_install_defaults()
except Exception:
    logger.exception("Theme registry initialization failed")

# Optionally sync media updates from VPinMediaDB in background
_start_startup_media_sync()
start_dof_service_if_enabled(iniconfig)

# Create API instances and register with WebSocket bridge
create_api_instances()

# Start the HTTP server to serve images from the "tables" directory
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
reconfigure_app_logging()

# Start the WebSocket bridge
ws_bridge.start()

if headless:
    import signal
    logger.info("Headless mode: servers running without Chromium frontend")
    logger.info("Press Ctrl+C to stop...")
    signal.signal(signal.SIGINT, lambda s, f: _shutdown_event.set())
    signal.signal(signal.SIGTERM, lambda s, f: _shutdown_event.set())
    _shutdown_event.wait()
    logger.info("Shutting down...")
elif iniconfig.is_new:
    # First-run: show manager UI config page in a chromium window instead of theme
    manager_ui_port = int(iniconfig.config['Network'].get('manageruiport', '8001'))
    setup_url = f'http://localhost:{manager_ui_port}/'
    screen_id = int(iniconfig.config['Displays'].get('tablescreenid', '0'))
    if sys.platform == "darwin":
        from frontend.chromium_manager import get_mac_screens
        monitors = get_mac_screens()
    else:
        from screeninfo import get_monitors
        monitors = get_monitors()
    monitor = monitors[screen_id] if screen_id < len(monitors) else monitors[0]
    logger.info("First run: loading Manager UI in chromium window for initial configuration.")
    frontend_browser.launch_window(
        window_name='table',
        url=setup_url,
        monitor=monitor,
        index=0,
    )
    # Block until the setup chromium window exits
    frontend_browser.wait_for_exit()
else:
    # Launch Chromium windows on configured monitors
    frontend_browser.launch_all_windows(iniconfig)

    # Block until Chromium windows exit (replaces the legacy UI main loop)
    frontend_browser.wait_for_exit()

# Shutdown items - wrap each in try/except so restart check always runs
logger.info("Shutting down services...")
try:
    vpinplay_sync_on_shutdown(iniconfig)
except Exception:
    logger.exception("vpinplay_sync_on_shutdown() error")
try:
    ws_bridge.stop()
except Exception:
    logger.exception("ws_bridge.stop() error")
try:
    stop_dof_service()
except Exception:
    logger.exception("stop_dof_service() error")
try:
    http_server.on_closed()
except Exception:
    logger.exception("http_server.on_closed() error")
try:
    nicegui_app.shutdown()
except Exception:
    logger.exception("nicegui_app.shutdown() error")
try:
    stop_manager_ui()
except Exception:
    logger.exception("stop_manager_ui() error")
logger.info("All services stopped.")

# Check for restart sentinel
restart_flag = config_dir / '.restart'
if restart_flag.exists():
    restart_flag.unlink()
    logger.info("Restart requested, re-launching...")
    import time
    time.sleep(1)  # Allow OS to release sockets before rebinding
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle: just re-exec the bundled executable
        os.execvp(sys.executable, [sys.executable])
    else:
        # Dev mode: re-exec with Python + script
        main_script = os.path.abspath(__file__)
        os.execvp(sys.executable, [sys.executable, main_script])
else:
    logger.info("No restart requested, exiting.")
