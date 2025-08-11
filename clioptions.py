import argparse
from screeninfo import get_monitors
import sys
from common.iniconfig import IniConfig
import colorama
from common.tableparser import TableParser
from common.vpsdb import VPSdb
from common.metaconfig import MetaConfig
from common.vpxparser import VPXParser
from common.standalonescripts import StandaloneScripts

colorama.init()
iniconfig = IniConfig("./vpinfe.ini")

def buildMetaData(downloadMedia = True):
        parservpx = VPXParser()
        print(f'Building meta.ini files for tables in {iniconfig.config["Settings"]["tableRootDir"]}')
        if downloadMedia:
            print("Including media download when available.")
        else:
            print("Skipping media download.")
        tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables();
        total = len(tables)
        print(f"Found {total} tables in {iniconfig.config['Settings']['tablerootdir']}")
        vps = VPSdb(iniconfig.config['Settings']['tablerootdir'], iniconfig)
        print(f"Found {len(vps)} tables in VPSdb")
        current = 0
        for table in tables:
            current = current + 1
            finalini = {}
            meta = MetaConfig(table.fullPathTable + "/" + "meta.ini") # check if we want it updated!!! TODO

            # vpsdb
            print(f"\rChecking VPSdb for table {current}/{total}: {table.tableDirName}")
            vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
            vpsData = vps.lookupName(vpsSearchData["name"], vpsSearchData["manufacturer"], vpsSearchData["year"]) if vpsSearchData is not None else None
            if vpsData is None:
                print(f"{colorama.Fore.RED}Not found in VPS{colorama.Style.RESET_ALL}")
                continue

            # vpx file info
            print(f"Parsing VPX file for metadata")
            print(f"Extracting {table.fullPathVPXfile} for metadata.")
            vpxData = parservpx.singleFileExtract(table.fullPathVPXfile)

            # make the config.ini
            finalini['vpsdata'] = vpsData
            finalini['vpxdata'] = vpxData
            meta.writeConfigMeta(finalini)
            if downloadMedia:
                vps.downloadMediaForTable(table, vpsData['id'])
 
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

def vpxPatches():
    tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables();
    StandaloneScripts(tables)
                        
def parseArgs():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--listres", help="ID and list your screens", action="store_true")
    parser.add_argument("--listmissing", help="List the tables from VPSdb", action="store_true")
    parser.add_argument("--listunknown", help="List the tables we can't match in VPSdb", action="store_true")
    parser.add_argument("--configfile", help="Configure the location of your vpinfe.ini file.  Default is cwd.")
    parser.add_argument("--buildmeta", help="Builds the meta.ini file in each table dir", action="store_true")
    parser.add_argument("--no-media", help="When building meta.ini files don't download the images at the same time.", action="store_true")
    parser.add_argument("--vpxpatch", help="Using vpx-standalone-scripts will attempt to load patches automatically", action="store_true")

    #args = parser.parse_args()
    args, unknown = parser.parse_known_args() # fix for mac

    if args.listres:
        # Get all available screens
        monitors = get_monitors()
        print(monitors)
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

    if args.vpxpatch:
        vpxPatches()
        sys.exit()
