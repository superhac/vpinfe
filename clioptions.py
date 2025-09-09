import argparse
import webview
from screeninfo import get_monitors
import sys
import os
import colorama

from common.iniconfig import IniConfig
from common.tableparser import TableParser
from common.vpsdb import VPSdb
from common.metaconfig import MetaConfig
from common.vpxparser import VPXParser
from common.standalonescripts import StandaloneScripts
from frontend.customhttpserver import CustomHTTPServer
from frontend.api import API
from pathlib import Path
import uuid

colorama.init()
iniconfig = IniConfig("./vpinfe.ini")

def _norm_path(p: str) -> str:
    try:
        return os.path.realpath(os.path.normpath(p)).lower()
    except Exception:
        return os.path.normpath(p).lower()

def buildMetaData(downloadMedia: bool = True, progress_cb=None):
    run_id = uuid.uuid4().hex[:8]
    
    #print(f'[# {run_id}] START buildMetaData (download={downloadMedia})')
    
    not_found_tables = 0
    parservpx = VPXParser()

    tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables()
    raw_count = len(tables)
    print(f"Found {raw_count} tables (.vpx).")
    seen = set()
    unique_tables = []
    for t in tables:
        key = _norm_path(t.fullPathVPXfile)
        if key in seen:
            continue
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

        # Verifying Table current/total
        if progress_cb:
            progress_cb(current, total, f'Verifying Table {current}/{total}: {table.tableDirName}')

        finalini = {}
        meta = MetaConfig(table.fullPathTable + "/" + "meta.ini")

        # vpsdb
        print(f"\rChecking VPSdb for table {current}/{total}: {table.tableDirName}")
        vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
        vpsData = vps.lookupName(vpsSearchData["name"], vpsSearchData["manufacturer"], vpsSearchData["year"]) if vpsSearchData is not None else None
        if vpsData is None:
            print(f"{colorama.Fore.RED}Not found in VPS{colorama.Style.RESET_ALL}")
            not_found_tables += 1
            continue

        # vpx file info
        print("Parsing VPX file for metadata")
        print(f"Extracting {table.fullPathVPXfile} for metadata.")
        vpxData = parservpx.singleFileExtract(table.fullPathVPXfile)

        # make the config.ini
        finalini['vpsdata'] = vpsData
        finalini['vpxdata'] = vpxData
        meta.writeConfigMeta(finalini)

        if downloadMedia:
            vps.downloadMediaForTable(table, vpsData['id'])
        result = {'found': total, 'not_found': not_found_tables}
        #print(f'[# {run_id}] END buildMetaData -> {result}')

    return {
        'found': total,
        'not_found': not_found_tables,
    }

 
def listMissingTables():
        tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables();
        print(f"Listing tables missing from {iniconfig.config["Settings"]["tableRootDir"]}")
        total = len(tables)
        print(f"Found {total} tables in {iniconfig.config["Settings"]["tableRootDir"]}")
        vps = VPSdb(iniconfig.config['Settings']['tablerootdir'], iniconfig)
        print(f"Found {len(vps)} tables in VPSdb")
        tables_found = []
        for table in tables:
            vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
            vpsData = vps.lookupName(vpsSearchData["name"], vpsSearchData["manufacturer"], vpsSearchData["year"]) if vpsSearchData is not None else None
            if vpsData is None:
                continue
            tables_found.append(vpsData)
        
        current = 0
        for vpsTable in vps.tables():
            if vpsTable not in tables_found:
                current = current + 1
                print(f"Missing table {current}: {vpsTable['name']} ({vpsTable['manufacturer']} {vpsTable['year']})")

def listUnknownTables():
        tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables();
        print(f"Listing unknown tables from {iniconfig.config["Settings"]["tableRootDir"]}")
        total = len(tables)
        print(f"Found {total} tables in {iniconfig.config["Settings"]["tableRootDir"]}")
        vps = VPSdb(iniconfig.config['Settings']['tablerootdir'], iniconfig)
        print(f"Found {len(vps)} tables in VPSdb")
        current = 0
        for table in tables:
            vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
            vpsData = vps.lookupName(vpsSearchData["name"], vpsSearchData["manufacturer"], vpsSearchData["year"]) if vpsSearchData is not None else None
            if vpsData is None:
                current = current + 1
                print(f"{colorama.Fore.RED}Unknown table {current}: {table.tableDirName} Not found in VPSdb{colorama.Style.RESET_ALL}")
                continue

def vpxPatches(progress_cb=None):
    tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables();
    StandaloneScripts(tables, progress_cb=progress_cb)
    
def loadGamepadTestWindow():
    webview_windows = [] # [ [window_name, window, api] ]
    api = API(iniconfig)
    html = Path(__file__).parent / "web/diag/gamepad.html"
    win = webview.create_window(
            "BG Screen",
             url=f"file://{html.resolve()}",
            js_api=api,
            background_color="#000000",
            fullscreen=True  # Set to False since we're manually sizing it
        )
    api.myWindow.append(win)
    webview_windows.append(['table',win, api])
    api.webview_windows = webview_windows
    api.iniConfig = iniconfig
    api._finish_setup()
    
def gamepadtest():
    loadGamepadTestWindow()
    # Start an the HTTP server to serve the images from the "tables" directory
    MOUNT_POINTS = {
            '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
            '/web/': os.path.join(os.getcwd(), 'web'),
            }
    http_server = HTTPServer(MOUNT_POINTS)
    http_server.start_file_server()

    # block and start webview
    webview.start(http_server=True)

    # shutdown items
    http_server.on_closed()
                        
def parseArgs():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--listres", help="ID and list your screens", action="store_true")
    parser.add_argument("--listmissing", help="List the tables from VPSdb", action="store_true")
    parser.add_argument("--listunknown", help="List the tables we can't match in VPSdb", action="store_true")
    parser.add_argument("--configfile", help="Configure the location of your vpinfe.ini file.  Default is cwd.")
    parser.add_argument("--buildmeta", help="Builds the meta.ini file in each table dir", action="store_true")
    parser.add_argument("--vpxpatch", help="Using vpx-standalone-scripts will attempt to load patches automatically", action="store_true")
    parser.add_argument("--gamepadtest", help="Testing and mapping your gamepad via js api", action="store_true")
    
    #second level args
    parser.add_argument("--no-media", help="When building meta.ini files don't download the images at the same time.", action="store_true")

    #args = parser.parse_args()
    args, unknown = parser.parse_known_args() # fix for mac
    
    if args.listres:
        # Get all available screens
        monitors = get_monitors()
        print([{
            'name': f'Monitor {i}',
            'x': m.x,
            'y': m.y,
            'width': m.width,
            'height': m.height
        } for i, m in enumerate(monitors)])
        sys.exit()
           
    elif args.listmissing:
        listMissingTables()
        sys.exit()

    elif args.listunknown:
        listUnknownTables()
        sys.exit()

    if args.configfile:
        configfile = args.configfile

    if args.buildmeta:
        buildMetaData(False if args.no_media else True)
        sys.exit()
        
    if args.gamepadtest:
        gamepadtest()
        sys.exit()

    if args.vpxpatch:
        vpxPatches()
        sys.exit()
