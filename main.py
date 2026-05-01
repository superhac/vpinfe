#!/usr/bin/env python3

from __future__ import annotations

import sys
import os
import platform
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

if "--dof-helper" in sys.argv[1:]:
    from common.dof_service_worker import main as _dof_helper_main
    raise SystemExit(_dof_helper_main())

from common.logging_config import configure_logging, get_logger
from common.iniconfig import IniConfig
from common.dof_service import start_dof_service_if_enabled, stop_dof_service
from common.libdmdutil_service import (
    stop_libdmdutil_service,
)
from common.pinmame_score_parser_updater import ensure_latest_roms_json
from common.vpinplay_service import sync_on_shutdown as vpinplay_sync_on_shutdown
from common.app_version import get_version
from common.themes import ThemeRegistry
from common.paths import VPINFE_INI_PATH, ensure_config_dir
from common.metadata_service import build_metadata

# Get the base path
base_path = os.path.dirname(os.path.abspath(__file__))

# Load config BEFORE importing clioptions/managerui (they create IniConfig at import time)
config_dir = ensure_config_dir()
log_path = configure_logging(config_dir, enable_file=False)
iniconfig = IniConfig(str(VPINFE_INI_PATH))
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
from frontend import runtime
from clioptions import parseArgs
from managerui.managerui import start_manager_ui, stop_manager_ui, set_first_run, _shutdown_event
from nicegui import app as nicegui_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

nicegui_app.add_static_files('/static', os.path.join(base_path, 'managerui/static'))


class _SuppressNoResponseReturnedMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except RuntimeError as exc:
            if str(exc) == "No response returned.":
                # Harmless client disconnect race in Starlette/NiceGUI middleware chain.
                return Response(status_code=204)
            raise


nicegui_app.add_middleware(_SuppressNoResponseReturnedMiddleware)

# On Windows, the Proactor event loop logs a noisy ConnectionResetError (WinError 10054)
# whenever a browser tab is closed mid-connection. Install a startup handler that
# silently drops those and forwards everything else to the default handler.
if sys.platform == "win32":
    import asyncio as _asyncio
    _windows_logger = get_logger("vpinfe.windows")

    @nicegui_app.on_startup
    async def _suppress_proactor_connection_reset() -> None:
        loop = _asyncio.get_running_loop()
        _default = loop.get_exception_handler()

        def _handler(loop: _asyncio.AbstractEventLoop, ctx: dict) -> None:
            exc = ctx.get("exception")
            if isinstance(exc, ConnectionResetError):
                _windows_logger.debug(str(exc))
                return  # swallow WinError 10054 noise from browser disconnects
            if _default is not None:
                _default(loop, ctx)
            else:
                loop.default_exception_handler(ctx)

        loop.set_exception_handler(_handler)

# Shared instances accessible from other modules (e.g. remote.py)
ws_bridge = None
frontend_browser = None
_startup_media_sync_started = False


def create_api_instances():
    """Create API instances for each configured display window."""
    global ws_bridge, frontend_browser
    ws_bridge, frontend_browser = runtime.create_api_instances(iniconfig, logger)


def _start_startup_media_sync():
    """Optionally sync media from VPinMediaDB on startup in a background thread."""
    global _startup_media_sync_started
    _startup_media_sync_started = runtime.start_startup_media_sync(
        iniconfig,
        logger,
        lambda **kwargs: build_metadata(iniconfig=iniconfig, **kwargs),
        started=_startup_media_sync_started,
    )


cli_args = parseArgs() if len(sys.argv) > 0 else None
headless = cli_args and cli_args.headless

# Register frontend theme assets before NiceGUI can start on the first-run path.
MOUNT_POINTS, themes_dir = runtime.build_mount_points(base_path, config_dir, iniconfig)
nicegui_app.add_static_files('/themes', themes_dir)

# On first run, start the manager UI early so chromium can load it
if iniconfig.is_new:
    set_first_run(True)
    manager_ui_port = int(iniconfig.config['Network'].get('manageruiport', '8001'))
    start_manager_ui(port=manager_ui_port)
    reconfigure_app_logging()
    # Wait for the NiceGUI server to be ready before chromium tries to load it
    runtime.wait_for_manager_ui_ready(manager_ui_port)
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
http_server = runtime.start_asset_server(MOUNT_POINTS, iniconfig)

# Start the NiceGUI HTTP server
manager_ui_port = int(iniconfig.config['Network'].get('manageruiport', '8001'))
start_manager_ui(port=manager_ui_port)
reconfigure_app_logging()

# Start the WebSocket bridge
ws_bridge.start()

runtime.run_frontend_loop(
    headless,
    iniconfig,
    frontend_browser,
    _shutdown_event,
    logger,
    is_window_connected=ws_bridge.is_window_connected,
)

# Shutdown items - wrap each in try/except so restart check always runs
runtime.shutdown_services(
    logger,
    vpinplay_sync=vpinplay_sync_on_shutdown,
    iniconfig=iniconfig,
    ws_bridge=ws_bridge,
    stop_dof=stop_dof_service,
    stop_dmd=stop_libdmdutil_service,
    http_server=http_server,
    nicegui_app=nicegui_app,
    stop_manager_ui=stop_manager_ui,
)

# Check for restart sentinel
runtime.restart_if_requested(config_dir, logger)
