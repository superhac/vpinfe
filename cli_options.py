"""The command-line interface: the flags, and what each one runs."""

import argparse
import os
import sys

from screeninfo import get_monitors

from common.config_store import ConfigStore
from common.deprecations import announce
from common.games import game_report_service, info_maintenance, metadata_service
from common.logging_config import get_logger
from common.paths import VPINFE_INI_PATH, ensure_config_dir
from frontend.custom_http_server import CustomHTTPServer

logger = get_logger("vpinfe.cli")

# Initialize config
ensure_config_dir()
logger.info("Using config file at: %s", VPINFE_INI_PATH)
config_store = ConfigStore(str(VPINFE_INI_PATH))


def buildMetaData(downloadMedia: bool = True, updateAll: bool = True, gameName: str = None, userMedia: bool = False, progress_cb=None, log_cb=None):
    return metadata_service.build_metadata(
        downloadMedia=downloadMedia,
        updateAll=updateAll,
        gameName=gameName,
        userMedia=userMedia,
        progress_cb=progress_cb,
        log_cb=log_cb,
        iniconfig=config_store,
    )


def _game_root_dir():
    from common.config_access import SettingsConfig

    return SettingsConfig.from_config(config_store).game_root_dir


def upgrade_info_files(game_name: str = None, progress_cb=None, log_cb=None):
    return info_maintenance.upgrade_library(
        _game_root_dir(), game_name=game_name, progress_cb=progress_cb, log_cb=log_cb)


def restore_info_files(game_name: str = None, progress_cb=None, log_cb=None):
    from common.paths import CONFIG_DIR

    return info_maintenance.restore_library(
        _game_root_dir(), game_name=game_name, config_dir=CONFIG_DIR,
        progress_cb=progress_cb, log_cb=log_cb)


def listMissingGames():
    return game_report_service.list_missing_games(iniconfig=config_store, log=logger.info)


def listUnknownGames():
    return game_report_service.list_unknown_games(iniconfig=config_store, log=logger.info)


def vpxPatches(progress_cb=None):
    return metadata_service.apply_vpx_patches(progress_cb=progress_cb, iniconfig=config_store)


def gamepadtest():
    """Run the gamepad test window using Chromium and the HTTP server."""
    from common.config_access import SettingsConfig, cfg_get, cfg_int
    from frontend.api import API
    from frontend.chromium_manager import ChromiumManager
    from frontend.ws_bridge import WebSocketBridge

    mount_points = {
        '/tables/': os.path.abspath(SettingsConfig.from_config(config_store).game_root_dir),
        '/web/': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web'),
    }
    http_server = CustomHTTPServer(mount_points)
    theme_assets_port = int(cfg_get(config_store, 'Network', 'theme_assets_port', '8000'))
    ws_port = cfg_int(config_store, 'network', 'wsport', 8002)
    http_server.start_file_server(port=theme_assets_port)

    monitors = get_monitors()
    ws_bridge = WebSocketBridge(port=ws_port)
    chromium = ChromiumManager()
    api = API(
        iniConfig=config_store,
        window_name="gamepad",
        ws_bridge=ws_bridge,
        frontend_browser=chromium,
    )
    api._finish_setup()
    ws_bridge.register_api("gamepad", api)

    ws_bridge.start()
    try:
        url = f"http://127.0.0.1:{theme_assets_port}/web/diag/gamepad.html?window=gamepad"
        chromium.launch_window("gamepad", url, monitors[0], 0)
        chromium.wait_for_exit()
    finally:
        ws_bridge.stop()
        http_server.on_closed()


def parseArgs():
    """Parse and dispatch command-line arguments."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--version", action="store_true", help="Show the app version")
    parser.add_argument("--listres", action="store_true", help="ID and list your screens")
    parser.add_argument("--listmissing", action="store_true", help="List the games from VPSdb")
    parser.add_argument("--listunknown", action="store_true", help="List the games we can't match in VPSdb")
    parser.add_argument("--configdir", metavar="DIR", help="Use DIR as the config directory (vpinfe.ini, themes, caches, logs) instead of the OS default. Same as the VPINFE_CONFIG_DIR env var; applied at startup in main.py.")
    parser.add_argument("--buildmeta", action="store_true", help="Builds the .info file in each game dir")
    parser.add_argument("--vpxpatch", action="store_true", help="Attempt to apply patches automatically")
    parser.add_argument("--gamepadtest", action="store_true", help="Test and map your gamepad via JS API")
    parser.add_argument("--headless", action="store_true", help="Run web servers/services only, skip the Chromium frontend")
    parser.add_argument("--claim-user-media", action="store_true", help="Deprecated and does nothing; your own media is protected automatically")

    # Secondary args
    parser.add_argument("--no-media", action="store_true", help="Do not download images when building the .info files")
    parser.add_argument("--update-all", action="store_true", help="Reparse all games when building the .info files")
    parser.add_argument("--user-media", action="store_true", help="With --buildmeta: skip vpinmediadb downloads entirely and supply all media yourself")
    parser.add_argument("--upgrade-info", action="store_true", help="Upgrade every game's .info file to the current format, backing up each one first. Normally done automatically at startup; use this to finish an upgrade that was interrupted")
    parser.add_argument("--restore-info", action="store_true", help="Put back the .info files saved before they were upgraded, for every game that has one. Your current .info is kept first")
    # --table is the pre-3.0 spelling, kept working and hidden from --help so the
    # documented flag is the current one. A user's script does not break.
    parser.add_argument("--game", "--table", dest="game",
                        help="Specify a single game folder name to process with "
                             "--buildmeta, --upgrade-info or --restore-info")

    args, unknown = parser.parse_known_args()  # macOS-friendly parsing

    # argparse does not report which spelling reached it, so ask argv directly.
    if any(a == "--table" or a.startswith("--table=") for a in sys.argv[1:]):
        announce("cli-game-flag", "--table")

    if unknown:
        parser.error(f"Unknown arguments: {' '.join(unknown)}")

    if args.version:
        sys.exit(0)

    if args.listres:
        monitors = get_monitors()
        logger.info("screeninfo monitors:")
        for i, m in enumerate(monitors):
            logger.info({
                'ID': f'Monitor {i}',
                'output': m.name,
                'x': m.x,
                'y': m.y,
                'width': m.width,
                'height': m.height,
            })
        if sys.platform == "darwin":
            from frontend.chromium_manager import get_mac_screens
            logger.info("NSScreen monitors (used for window positioning on macOS):")
            for i, s in enumerate(get_mac_screens()):
                logger.info({
                    'ID': f'Screen {i}',
                    'x': s.x,
                    'y': s.y,
                    'width': s.width,
                    'height': s.height,
                })
        sys.exit()

    if args.listmissing:
        listMissingGames()
        sys.exit()

    if args.listunknown:
        listUnknownGames()
        sys.exit()

    # Kept as a stub because it shipped in 2.x and somebody has it in a script. It
    # marked media as yours so vpinmediadb would not overwrite it; the downloader now
    # proves ownership by hash before touching anything, so there is nothing to mark.
    if args.claim_user_media:
        logger.info("--claim-user-media is deprecated and does nothing. Media that is "
                    "not vpinmediadb's is left alone automatically; no need to claim it.")
        sys.exit()

    if args.upgrade_info:
        upgrade_info_files(game_name=args.game)
        sys.exit()

    if args.restore_info:
        restore_info_files(game_name=args.game)
        sys.exit()

    if args.buildmeta:
        buildMetaData(downloadMedia=not args.no_media, updateAll=args.update_all, gameName=args.game, userMedia=args.user_media)
        sys.exit()

    if args.gamepadtest:
        gamepadtest()
        sys.exit()

    if args.vpxpatch:
        vpxPatches()
        sys.exit()

    return args
