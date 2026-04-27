from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path

from frontend.api import API
from frontend.chromium_manager import ChromiumManager
from frontend.customhttpserver import CustomHTTPServer
from frontend.ws_bridge import WebSocketBridge
from common import system_actions
from common.config_access import DisplayConfig, NetworkConfig, SettingsConfig
from common.display_service import get_display_monitors


WINDOW_CONFIGS = (
    ("bg", "bgscreenid"),
    ("dmd", "dmdscreenid"),
    ("table", "tablescreenid"),
)


def create_api_instances(iniconfig, logger):
    network = NetworkConfig.from_config(iniconfig)
    displays = DisplayConfig.from_config(iniconfig)
    ws_bridge = WebSocketBridge(port=network.ws_port)
    frontend_browser = ChromiumManager()

    for window_name, config_key in WINDOW_CONFIGS:
        screen_id_str = displays.window_screen_id(config_key).strip()
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

    return ws_bridge, frontend_browser


def start_startup_media_sync(iniconfig, logger, build_metadata_func, started: bool = False) -> bool:
    if started:
        return True

    if iniconfig.is_new:
        logger.info("Skipping startup media sync on first run.")
        return False

    settings = SettingsConfig.from_config(iniconfig)
    enabled = settings.auto_update_media_on_startup

    if not enabled:
        return False

    table_root = settings.table_root_dir
    if not table_root:
        logger.info("Startup media sync enabled, but tablerootdir is empty. Skipping.")
        return False

    def _worker():
        logger.info("Startup media sync enabled. Checking VPinMediaDB for missing/updated media...")
        try:
            result = build_metadata_func(downloadMedia=True, updateAll=True, userMedia=False)
            if isinstance(result, dict):
                logger.info(
                    "Startup media sync complete. Scanned %s table(s); %s not found in VPSdb.",
                    result.get("found", 0),
                    result.get("not_found", 0),
                )
            else:
                logger.info("Startup media sync complete.")
        except Exception:
            logger.exception("Startup media sync failed")

    threading.Thread(target=_worker, daemon=True, name="startup-media-sync").start()
    return True


def build_mount_points(base_path: str, config_dir: Path, iniconfig):
    themes_dir = str(config_dir / "themes")
    collection_icons_dir = str(config_dir / "collection_icons")
    os.makedirs(themes_dir, exist_ok=True)
    os.makedirs(collection_icons_dir, exist_ok=True)
    mount_points = {
        "/web/": os.path.join(base_path, "web"),
        "/themes/": themes_dir,
        "/collection_icons/": collection_icons_dir,
    }
    table_root = SettingsConfig.from_config(iniconfig).table_root_dir
    if table_root:
        mount_points["/tables/"] = os.path.abspath(table_root)
    return mount_points, themes_dir


def start_asset_server(mount_points, iniconfig):
    http_server = CustomHTTPServer(mount_points)
    theme_assets_port = NetworkConfig.from_config(iniconfig).theme_assets_port
    http_server.start_file_server(port=theme_assets_port)
    return http_server


def wait_for_manager_ui_ready(port: int, timeout_seconds: float = 15.0) -> None:
    import urllib.request as _ur

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            _ur.urlopen(f"http://localhost:{port}/api/remote-launch", timeout=1)
            return
        except Exception:
            time.sleep(0.5)


def run_frontend_loop(headless, iniconfig, frontend_browser, shutdown_event, logger):
    if headless:
        def _request_shutdown(_signum, _frame):
            shutdown_event.set()

        logger.info("Headless mode: servers running without Chromium frontend")
        logger.info("Press Ctrl+C to stop...")
        signal.signal(signal.SIGTERM, _request_shutdown)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, _request_shutdown)

        try:
            while not shutdown_event.is_set():
                shutdown_event.wait(0.2)
        except KeyboardInterrupt:
            shutdown_event.set()
        logger.info("Shutting down...")
        return

    if iniconfig.is_new:
        network = NetworkConfig.from_config(iniconfig)
        displays = DisplayConfig.from_config(iniconfig)
        manager_ui_port = network.manager_ui_port
        setup_url = f"http://localhost:{manager_ui_port}/"
        screen_id = displays.table_screen_id
        monitors = get_display_monitors()
        monitor = monitors[screen_id] if screen_id < len(monitors) else monitors[0]
        logger.info("First run: loading Manager UI in chromium window for initial configuration.")
        frontend_browser.launch_window(
            window_name="table",
            url=setup_url,
            monitor=monitor,
            index=0,
        )
        frontend_browser.wait_for_exit()
        return

    frontend_browser.launch_all_windows(iniconfig)
    frontend_browser.wait_for_exit()


def shutdown_services(logger, *, vpinplay_sync, iniconfig, ws_bridge, stop_dof, stop_dmd, http_server, nicegui_app, stop_manager_ui):
    logger.info("Shutting down services...")
    for label, action in (
        ("vpinplay_sync_on_shutdown", lambda: vpinplay_sync(iniconfig)),
        ("ws_bridge.stop", ws_bridge.stop),
        ("stop_dof_service", stop_dof),
        ("stop_libdmdutil_service", lambda: stop_dmd(clear=False)),
        ("http_server.on_closed", http_server.on_closed),
        ("nicegui_app.shutdown", nicegui_app.shutdown),
        ("stop_manager_ui", stop_manager_ui),
    ):
        try:
            action()
        except Exception:
            logger.exception("%s() error", label)
    logger.info("All services stopped.")


def restart_if_requested(config_dir: Path, logger) -> None:
    system_actions.restart_if_requested(config_dir, logger)
