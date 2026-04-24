import argparse
import sys
import os

from screeninfo import get_monitors

from common.iniconfig import IniConfig
from common.tableparser import TableParser
from common.vpsdb import VPSdb
from common.logging_config import get_logger
from common.paths import VPINFE_INI_PATH, ensure_config_dir
from common import metadata_service
from frontend.customhttpserver import CustomHTTPServer

logger = get_logger("vpinfe.cli")

# Initialize config
ensure_config_dir()
logger.info("Using config file at: %s", VPINFE_INI_PATH)
iniconfig = IniConfig(str(VPINFE_INI_PATH))


def buildMetaData(downloadMedia: bool = True, updateAll: bool = True, tableName: str = None, userMedia: bool = False, progress_cb=None, log_cb=None):
    return metadata_service.build_metadata(
        downloadMedia=downloadMedia,
        updateAll=updateAll,
        tableName=tableName,
        userMedia=userMedia,
        progress_cb=progress_cb,
        log_cb=log_cb,
        iniconfig=iniconfig,
    )


def listMissingTables():
    """List VPSdb tables that are not present locally."""
    tp = TableParser(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()
    logger.info("Listing tables missing from %s", iniconfig.config['Settings']['tablerootdir'])
    total = len(tables)
    logger.info("Found %s tables in %s", total, iniconfig.config['Settings']['tablerootdir'])

    vps = VPSdb(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    logger.info("Found %s tables in VPSdb", len(vps))

    tables_found = []
    for table in tables:
        vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
        vpsData = (
            vps.lookupName(
                vpsSearchData["name"],
                vpsSearchData["manufacturer"],
                vpsSearchData["year"]
            ) if vpsSearchData else None
        )
        if vpsData:
            tables_found.append(vpsData)

    current = 0
    for vpsTable in vps.tables():
        if vpsTable not in tables_found:
            current += 1
            logger.info(
                "Missing table %s: %s (%s %s)",
                current,
                vpsTable["name"],
                vpsTable["manufacturer"],
                vpsTable["year"],
            )


def listUnknownTables():
    """List local tables that could not be matched in VPSdb."""
    tp = TableParser(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()
    logger.info("Listing unknown tables from %s", iniconfig.config['Settings']['tablerootdir'])
    total = len(tables)
    logger.info("Found %s tables in %s", total, iniconfig.config['Settings']['tablerootdir'])

    vps = VPSdb(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    logger.info("Found %s tables in VPSdb", len(vps))

    current = 0
    for table in tables:
        vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
        vpsData = (
            vps.lookupName(
                vpsSearchData["name"],
                vpsSearchData["manufacturer"],
                vpsSearchData["year"]
            ) if vpsSearchData else None
        )
        if vpsData is None:
            current += 1
            logger.info("Unknown table %s: %s Not found in VPSdb", current, table.tableDirName)


def vpxPatches(progress_cb=None):
    return metadata_service.apply_vpx_patches(progress_cb=progress_cb, iniconfig=iniconfig)


def _claimMediaForTable(table, tabletype, log=None):
    return metadata_service.claim_media_for_table(table, tabletype, log)


def claimUserMedia(tableName=None, progress_cb=None, log_cb=None):
    return metadata_service.claim_user_media(
        tableName=tableName,
        progress_cb=progress_cb,
        log_cb=log_cb,
        iniconfig=iniconfig,
    )


def gamepadtest():
    """Run the gamepad test window using Chromium and the HTTP server."""
    from frontend.chromium_manager import ChromiumManager
    from frontend.api import API
    from frontend.ws_bridge import WebSocketBridge

    mount_points = {
        '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
        '/web/': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web'),
    }
    http_server = CustomHTTPServer(mount_points)
    theme_assets_port = int(iniconfig.config['Network'].get('themeassetsport', '8000'))
    ws_port = int(iniconfig.config['Network'].get('wsport', '8002'))
    http_server.start_file_server(port=theme_assets_port)

    monitors = get_monitors()
    ws_bridge = WebSocketBridge(port=ws_port)
    chromium = ChromiumManager()
    api = API(
        iniConfig=iniconfig,
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
    parser.add_argument("--listmissing", action="store_true", help="List the tables from VPSdb")
    parser.add_argument("--listunknown", action="store_true", help="List the tables we can't match in VPSdb")
    parser.add_argument("--configfile", help="Configure the location of your vpinfe.ini file. Default is cwd.")
    parser.add_argument("--buildmeta", action="store_true", help="Builds the meta.ini file in each table dir")
    parser.add_argument("--vpxpatch", action="store_true", help="Attempt to apply patches automatically")
    parser.add_argument("--gamepadtest", action="store_true", help="Test and map your gamepad via JS API")
    parser.add_argument("--headless", action="store_true", help="Run web servers/services only, skip the Chromium frontend")
    parser.add_argument("--claim-user-media", action="store_true", help="Bulk mark existing media files as user-sourced so they won't be overwritten by vpinmediadb")

    # Secondary args
    parser.add_argument("--no-media", action="store_true", help="Do not download images when building meta.ini")
    parser.add_argument("--update-all", action="store_true", help="Reparse all tables when building meta.ini")
    parser.add_argument("--user-media", action="store_true", help="With --buildmeta: skip vpinmediadb downloads and claim existing local media as user-sourced")
    parser.add_argument("--table", help="Specify a single table folder name to process with --buildmeta or --claim-user-media")

    args, unknown = parser.parse_known_args()  # macOS-friendly parsing

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
        listMissingTables()
        sys.exit()

    if args.listunknown:
        listUnknownTables()
        sys.exit()

    if args.configfile:
        configfile = args.configfile  # TODO: wire into IniConfig if needed

    if args.claim_user_media:
        claimUserMedia(tableName=args.table)
        sys.exit()

    if args.buildmeta:
        buildMetaData(downloadMedia=not args.no_media, updateAll=args.update_all, tableName=args.table, userMedia=args.user_media)
        sys.exit()

    if args.gamepadtest:
        gamepadtest()
        sys.exit()

    if args.vpxpatch:
        vpxPatches()
        sys.exit()

    return args
