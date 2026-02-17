import argparse
import sys
import os
import uuid
from pathlib import Path

from screeninfo import get_monitors
from platformdirs import user_config_dir

from common.iniconfig import IniConfig
from common.tableparser import TableParser
from common.vpsdb import VPSdb
from common.metaconfig import MetaConfig
from common.vpxparser import VPXParser
from common.standalonescripts import StandaloneScripts
from frontend.customhttpserver import CustomHTTPServer

# Initialize config
config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
config_dir.mkdir(parents=True, exist_ok=True)
config_path = config_dir / "vpinfe.ini"
print(f"Using config file at: {config_path}")
iniconfig = IniConfig(str(config_path))


def _norm_path(p: str) -> str:
    """Normalize a filesystem path for consistent comparisons."""
    try:
        return os.path.realpath(os.path.normpath(p)).lower()
    except Exception:
        return os.path.normpath(p).lower()


def buildMetaData(downloadMedia: bool = True, updateAll: bool = True, tableName: str = None, userMedia: bool = False, progress_cb=None, log_cb=None):

    def log(msg):
        print(msg)
        if log_cb:
            log_cb(msg)

    not_found_tables = 0
    parservpx = VPXParser()

    tp = TableParser(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()

    if tableName:
        tables = [t for t in tables if t.tableDirName == tableName]
        if not tables:
            log(f"Table folder '{tableName}' not found")
            return {"found": 0, "not_found": 0}
        log(f"Processing single table: {tableName}")

    total = len(tables)

    vps = VPSdb(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    log(f"Found {len(vps)} tables in VPSdb")

    if progress_cb:
        progress_cb(0, total, "Starting")

    current = 0
    for table in tables:
        current += 1

        info_path = os.path.join(
            table.fullPathTable,
            f"{table.tableDirName}.info"
        )

        if os.path.exists(info_path) and not updateAll:
            if progress_cb:
                progress_cb(current, total, f"Skipping {table.tableDirName}")
            continue

        meta = MetaConfig(info_path)

        log(f"Checking VPSdb for {table.tableDirName}")
        if progress_cb:
            progress_cb(current, total, f"Processing {table.tableDirName}")

        vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
        vpsData = (
            vps.lookupName(
                vpsSearchData["name"],
                vpsSearchData["manufacturer"],
                vpsSearchData["year"]
            ) if vpsSearchData else None
        )

        if not vpsData:
            log("  - Not found in VPS")
            not_found_tables += 1
            continue

        log(f"Parsing VPX file: {table.fullPathVPXfile}")
        vpxData = parservpx.singleFileExtract(table.fullPathVPXfile)

        if not vpxData:
            log(f"  - VPX file not found or failed to parse: {table.fullPathVPXfile}")
            not_found_tables += 1
            continue

        meta.writeConfigMeta({
            "vpsdata": vpsData,
            "vpxdata": vpxData
        })

        log(f"Created {table.tableDirName}.info")

        if userMedia:
            tabletype = iniconfig.config['Media'].get('tabletype', 'table').lower()
            claimed = _claimMediaForTable(table, tabletype, log)
            if claimed:
                log(f"  Claimed {claimed} media file(s) as user-sourced")
        elif downloadMedia:
            try:
                vps.downloadMediaForTable(table, vpsData["id"], metaConfig=meta)
                log("Downloaded media")
            except KeyError:
                log("No media found")

    if progress_cb:
        progress_cb(total, total, "Complete")

    return {
        "found": total,
        "not_found": not_found_tables
    }



def listMissingTables():
    """List VPSdb tables that are not present locally."""
    tp = TableParser(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()
    print(f"Listing tables missing from {iniconfig.config['Settings']['tablerootdir']}")
    total = len(tables)
    print(f"Found {total} tables in {iniconfig.config['Settings']['tablerootdir']}")

    vps = VPSdb(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    print(f"Found {len(vps)} tables in VPSdb")

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
            print(f"Missing table {current}: {vpsTable['name']} ({vpsTable['manufacturer']} {vpsTable['year']})")


def listUnknownTables():
    """List local tables that could not be matched in VPSdb."""
    tp = TableParser(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()
    print(f"Listing unknown tables from {iniconfig.config['Settings']['tablerootdir']}")
    total = len(tables)
    print(f"Found {total} tables in {iniconfig.config['Settings']['tablerootdir']}")

    vps = VPSdb(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    print(f"Found {len(vps)} tables in VPSdb")

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
            print(f"Unknown table {current}: {table.tableDirName} Not found in VPSdb")


def vpxPatches(progress_cb=None):
    """Apply VPX standalone script patches."""
    tp = TableParser(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()
    StandaloneScripts(tables, progress_cb=progress_cb)


def _claimMediaForTable(table, tabletype, log=print):
    """Scan a table's medias/ dir and mark all found files as user-sourced in the .info."""
    info_path = os.path.join(table.fullPathTable, f"{table.tableDirName}.info")
    if not os.path.exists(info_path):
        log(f"  Skipping {table.tableDirName}: no .info file")
        return 0

    # Media keys mapped to their filenames, accounting for tabletype (table vs fss)
    media_files = {
        'bg': 'bg.png',
        'dmd': 'dmd.png',
        tabletype: f'{tabletype}.png',
        'wheel': 'wheel.png',
        'cab': 'cab.png',
        'realdmd': 'realdmd.png',
        'realdmd_color': 'realdmd-color.png',
        'flyer': 'flyer.png',
        f'{tabletype}_video': f'{tabletype}.mp4',
        'bg_video': 'bg.mp4',
        'dmd_video': 'dmd.mp4',
    }

    medias_dir = os.path.join(table.fullPathTable, "medias")
    meta = MetaConfig(info_path)
    claimed = 0

    for media_key, filename in media_files.items():
        filepath = os.path.join(medias_dir, filename)
        if os.path.exists(filepath):
            existing = meta.getMedia(media_key)
            if existing and existing.get("Source") == "user":
                continue
            meta.addMedia(media_key, "user", filepath, "")
            log(f"  Claimed {media_key} ({filename}) as user media")
            claimed += 1

    return claimed


def claimUserMedia(tableName=None, progress_cb=None, log_cb=None):
    """Bulk scan tables and mark existing media files as user-sourced."""

    def log(msg):
        print(msg)
        if log_cb:
            log_cb(msg)

    tp = TableParser(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()

    tabletype = iniconfig.config['Media'].get('tabletype', 'table').lower()

    if tableName:
        tables = [t for t in tables if t.tableDirName == tableName]
        if not tables:
            log(f"Table folder '{tableName}' not found")
            return {"tables_processed": 0, "media_claimed": 0}
        log(f"Processing single table: {tableName}")

    total = len(tables)
    total_claimed = 0

    if progress_cb:
        progress_cb(0, total, "Starting")

    for current, table in enumerate(tables, 1):
        log(f"Scanning {table.tableDirName}")
        if progress_cb:
            progress_cb(current, total, f"Scanning {table.tableDirName}")

        claimed = _claimMediaForTable(table, tabletype, log)
        total_claimed += claimed

    if progress_cb:
        progress_cb(total, total, "Complete")

    log(f"\nDone. Scanned {total} tables, claimed {total_claimed} media files as user-sourced.")
    return {"tables_processed": total, "media_claimed": total_claimed}


def gamepadtest():
    """Run the gamepad test window using Chromium and the HTTP server."""
    from frontend.chromium_manager import ChromiumManager

    mount_points = {
        '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
        '/web/': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web'),
    }
    http_server = CustomHTTPServer(mount_points)
    theme_assets_port = int(iniconfig.config['Network'].get('themeassetsport', '8000'))
    http_server.start_file_server(port=theme_assets_port)

    monitors = get_monitors()
    chromium = ChromiumManager()
    url = f"http://127.0.0.1:{theme_assets_port}/web/diag/gamepad.html"
    chromium.launch_window("gamepad", url, monitors[0], 0)
    chromium.wait_for_exit()
    http_server.on_closed()


def parseArgs():
    """Parse and dispatch command-line arguments."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
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

    if args.listres:
        monitors = get_monitors()
        [print({
            'ID': f'Monitor {i}',
            'output': m.name,
            'x': m.x,
            'y': m.y,
            'width': m.width,
            'height': m.height
        }) for i, m in enumerate(monitors)]
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

