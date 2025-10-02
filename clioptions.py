import argparse
import sys
import os
import uuid
from pathlib import Path

import colorama
import webview
from screeninfo import get_monitors

from common.iniconfig import IniConfig
from common.tableparser import TableParser
from common.vpsdb import VPSdb
from common.metaconfig import MetaConfig
from common.vpxparser import VPXParser
from common.standalonescripts import StandaloneScripts
from frontend.customhttpserver import CustomHTTPServer
from frontend.api import API

# Initialize config
colorama.init()
iniconfig = IniConfig("./vpinfe.ini")


def _norm_path(p: str) -> str:
    """Normalize a filesystem path for consistent comparisons."""
    try:
        return os.path.realpath(os.path.normpath(p)).lower()
    except Exception:
        return os.path.normpath(p).lower()


def buildMetaData(downloadMedia: bool = True, updateAll: bool = True, progress_cb=None):
    """Build meta.ini files for all VPX tables and sync with VPSdb."""
    not_found_tables = 0
    parservpx = VPXParser()
    
    tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables()
    raw_count = len(tables)
    print(f"Found {raw_count} tables (.vpx).")

    seen = set()
    unique_tables = []
    for t in tables:
        key = _norm_path(t.fullPathVPXfile)
        if key not in seen:
            seen.add(key)
            unique_tables.append(t)

    total = len(unique_tables)
    vps = VPSdb(iniconfig.config['Settings']['tablerootdir'], iniconfig)
    print(f"Found {len(vps)} tables in VPSdb")

    if progress_cb:
        progress_cb(0, total, 'Starting')

    current = 0
    for table in tables:
        current += 1
        finalini = {}
        
        meta_path = os.path.join(table.fullPathTable, "meta.ini")

        if os.path.exists(meta_path) and not updateAll:
            continue
        
        meta = MetaConfig(meta_path)

        # VPSdb lookup
        print(f"\rChecking VPSdb for table {current}/{total}: {table.tableDirName}")
        vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
        vpsData = (
            vps.lookupName(
                vpsSearchData["name"],
                vpsSearchData["manufacturer"],
                vpsSearchData["year"]
            ) if vpsSearchData else None
        )
        if vpsData is None:
            print(f"{colorama.Fore.RED}Not found in VPS{colorama.Style.RESET_ALL}")
            not_found_tables += 1
            continue

        # Parse VPX file
        print("Parsing VPX file for metadata")
        print(f"Extracting {table.fullPathVPXfile} for metadata.")
        vpxData = parservpx.singleFileExtract(table.fullPathVPXfile)

        finalini['vpsdata'] = vpsData
        finalini['vpxdata'] = vpxData
        meta.writeConfigMeta(finalini)

        if downloadMedia:
            try:
                vps.downloadMediaForTable(table, vpsData['id'])
                print("Downloaded media for table")
            except KeyError:
                print(f"{colorama.Fore.RED}No Media found{colorama.Style.RESET_ALL}")

    return {'found': total, 'not_found': not_found_tables}


def listMissingTables():
    """List VPSdb tables that are not present locally."""
    tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables()
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
    tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables()
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
            print(f"{colorama.Fore.RED}Unknown table {current}: {table.tableDirName} Not found in VPSdb{colorama.Style.RESET_ALL}")


def vpxPatches(progress_cb=None):
    """Apply VPX standalone script patches."""
    tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables()
    StandaloneScripts(tables, progress_cb=progress_cb)


def loadGamepadTestWindow():
    """Open a test webview window for gamepad diagnostics."""
    webview_windows = []
    api = API(iniconfig)
    html = Path(__file__).parent / "web/diag/gamepad.html"

    win = webview.create_window(
        "BG Screen",
        url=f"file://{html.resolve()}",
        js_api=api,
        background_color="#000000",
        fullscreen=True
    )

    api.myWindow.append(win)
    webview_windows.append(['table', win, api])
    api.webview_windows = webview_windows
    api.iniConfig = iniconfig
    api._finish_setup()


def gamepadtest():
    """Run the gamepad test window and serve local files."""
    loadGamepadTestWindow()

    mount_points = {
        '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
        '/web/': os.path.join(os.getcwd(), 'web'),
    }
    http_server = CustomHTTPServer(mount_points)
    http_server.start_file_server()

    webview.start(http_server=True)
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

    # Secondary args
    parser.add_argument("--no-media", action="store_true", help="Do not download images when building meta.ini")
    parser.add_argument("--update-all", action="store_true", help="Reparse all tables when building meta.ini")

    args, unknown = parser.parse_known_args()  # macOS-friendly parsing

    if unknown:
        parser.error(f"Unknown arguments: {' '.join(unknown)}")

    if args.listres:
        monitors = get_monitors()
        print([{
            'name': f'Monitor {i}',
            'x': m.x,
            'y': m.y,
            'width': m.width,
            'height': m.height
        } for i, m in enumerate(monitors)])
        sys.exit()

    if args.listmissing:
        listMissingTables()
        sys.exit()

    if args.listunknown:
        listUnknownTables()
        sys.exit()

    if args.configfile:
        configfile = args.configfile  # TODO: wire into IniConfig if needed

    if args.buildmeta:
        buildMetaData(downloadMedia=not args.no_media, updateAll=args.update_all)
        sys.exit()

    if args.gamepadtest:
        gamepadtest()
        sys.exit()

    if args.vpxpatch:
        vpxPatches()
        sys.exit()

