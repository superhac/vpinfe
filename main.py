#!/usr/bin/env python3

from __future__ import annotations

import multiprocessing
import os
import platform
import sys

from common.config_access import cfg_get

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
    from common.host.dof_service_worker import main as _dof_helper_main
    raise SystemExit(_dof_helper_main())


# common.paths resolves CONFIG_DIR at import time, so --configdir has to reach
# the environment before anything under common/ is imported. Do it first.
from common.config_bootstrap import apply_configdir_override

apply_configdir_override(sys.argv[1:])

from common import shutdown, theme_options
from common.app_version import get_version
from common.config_store import ConfigStore
from common.games.metadata_service import build_metadata
from common.host.dof_service import start_dof_service_if_enabled, stop_dof_service
from common.host.libdmdutil_service import (
    stop_libdmdutil_service,
)
from common.logging_config import configure_logging, get_logger
from common.online.pinmame_score_parser_updater import ensure_latest_roms_json
from common.online.themes import ThemeRegistry
from common.online.vpinplay_service import sync_on_shutdown as vpinplay_sync_on_shutdown
from common.paths import (
    THEMES_DIR,
    VPINFE_INI_PATH,
    configure_nicegui_storage,
    ensure_config_dir,
)

# Get the base path
base_path = os.path.dirname(os.path.abspath(__file__))

# Load config BEFORE importing cli_options/managerui (they create ConfigStore at import time)
config_dir = ensure_config_dir()
nicegui_storage_path = configure_nicegui_storage()
log_path = configure_logging(config_dir, enable_file=False)
config_store = ConfigStore(str(VPINFE_INI_PATH))
log_path = configure_logging(config_dir, config_store)
logger = get_logger("vpinfe.main")
logger.info("Logging to %s", log_path)
logger.info("Using NiceGUI storage path: %s", nicegui_storage_path)
logger.info("Version: %s", get_version())

# Startup downloads themes, walks the library and rewrites .info files, and it can take
# a while on a big one. Start listening for a kill now; the checks below act on it at
# the step boundaries, so nothing gets killed halfway through writing.
shutdown.watch_during_startup()

try:
    roms_update_result = ensure_latest_roms_json(config_store)
    logger.info(
        "pinmame-score-parser roms.json status=%s path=%s",
        roms_update_result.get("status"),
        roms_update_result.get("path"),
    )
except Exception:
    logger.exception("Failed to update pinmame-score-parser roms.json at startup")

shutdown.exit_if_requested(logger)


def reconfigure_app_logging() -> None:
    configure_logging(config_dir, config_store)

# Now safe to import modules that create their own ConfigStore at import time
from nicegui import app as nicegui_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

import httpapi
from cli_options import parseArgs
from frontend import runtime
from managerui.managerui import _shutdown_event, set_first_run, start_manager_ui, stop_manager_ui

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

# Mount the HTTP API. Has to happen before any ui.run(), including the early
# first-run start below.
httpapi.register(nicegui_app)

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
    ws_bridge, frontend_browser = runtime.create_api_instances(config_store, logger)


def _start_startup_media_sync():
    """Optionally sync media from VPinMediaDB on startup in a background thread."""
    global _startup_media_sync_started
    _startup_media_sync_started = runtime.start_startup_media_sync(
        config_store,
        logger,
        lambda **kwargs: build_metadata(iniconfig=config_store, **kwargs),
        started=_startup_media_sync_started,
    )


cli_args = parseArgs() if len(sys.argv) > 0 else None
headless = cli_args and cli_args.headless

# Register frontend theme assets before NiceGUI can start on the first-run path.
MOUNT_POINTS, themes_dir = runtime.build_mount_points(base_path, config_dir, config_store)
nicegui_app.add_static_files('/themes', themes_dir)

# On first run, start the manager UI early so chromium can load it
if config_store.is_new:
    set_first_run(True)
    manager_ui_port = int(cfg_get(config_store, 'Network', 'manager_ui_port', '8001'))
    start_manager_ui(port=manager_ui_port)
    reconfigure_app_logging()
    # Wait for the NiceGUI server to be ready before chromium tries to load it
    runtime.wait_for_manager_ui_ready(manager_ui_port)
    logger.info("First run: Manager UI ready on port %s", manager_ui_port)

# Before anything installs or updates a theme. An update deletes the theme's folder, and
# until now that folder is where the user's option values were kept - so this has to run
# first or the release that fixes that data loss is the release that causes it one last
# time. Cheap and idempotent: it skips any theme that already has its own options file.
try:
    theme_options.migrate_from_packages(THEMES_DIR)
except Exception:
    logger.exception("Could not move theme options out of the installed packages")

# Initialize theme registry and auto-install default themes
try:
    theme_registry = ThemeRegistry()
    theme_registry.load_registry()
    theme_registry.load_theme_manifests(default_only=True)
    theme_registry.auto_install_defaults()
except Exception:
    logger.exception("Theme registry initialization failed")

shutdown.exit_if_requested(logger)

# Give every game and every table a stable id. One-time cost per library; a no-op
# afterwards, and neither pass writes a .info it did not change.
try:
    from common.games.game_identity import ensure_unique_ids
    from common.games.game_repository import ensure_games_loaded
    from common.games.table_identity import ensure_unique_table_ids
    games = ensure_games_loaded()
    ensure_unique_ids(games)
    ensure_unique_table_ids(games)
except Exception:
    logger.exception("Id backfill failed; games or tables without an id are not addressable")

shutdown.exit_if_requested(logger)

# Collection membership moves onto game ids once the ids exist. Resolvable entries
# are rewritten; anything that does not resolve is left alone rather than dropped.
try:
    from common.games.collection_store import CollectionStore
    from common.paths import COLLECTIONS_PATH
    _collections = CollectionStore(str(COLLECTIONS_PATH))
    _collections.migrate_membership_to_game_ids(ensure_games_loaded())
except Exception:
    logger.exception("Collection membership migration failed; memberships left as they were")

shutdown.exit_if_requested(logger)

# Optionally sync media updates from VPinMediaDB in background
_start_startup_media_sync()
# Feedback hardware follows game lifecycle events from here on, so both launch
# paths get the same behaviour without either of them knowing about DOF.
from common.host import peripherals

peripherals.register()

start_dof_service_if_enabled(config_store)

# Point the archive analyzer at a configured RAR tool (blank = auto-detect from PATH)
from managerui.services.asset_analyzer_service import configure_rar_tool

configure_rar_tool(cfg_get(config_store, 'Settings', 'rar_tool_path', '').strip())

# Create API instances and register with WebSocket bridge
create_api_instances()

# Start the HTTP server to serve images from the "games" directory
http_server = runtime.start_asset_server(MOUNT_POINTS, config_store)

# Start the NiceGUI HTTP server
manager_ui_port = int(cfg_get(config_store, 'Network', 'manager_ui_port', '8001'))
start_manager_ui(port=manager_ui_port)
reconfigure_app_logging()

# Start the WebSocket bridge
ws_bridge.start()

runtime.run_frontend_loop(
    headless,
    config_store,
    frontend_browser,
    _shutdown_event,
    logger,
    is_window_connected=ws_bridge.is_window_connected,
)

# Shutdown items - wrap each in try/except so restart check always runs
runtime.shutdown_services(
    logger,
    vpinplay_sync=vpinplay_sync_on_shutdown,
    iniconfig=config_store,
    ws_bridge=ws_bridge,
    stop_dof=stop_dof_service,
    stop_dmd=stop_libdmdutil_service,
    http_server=http_server,
    nicegui_app=nicegui_app,
    stop_manager_ui=stop_manager_ui,
)

# Check for restart sentinel
runtime.restart_if_requested(config_dir, logger)
