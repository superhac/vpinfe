from common.table import Table
import os
from pathlib import Path
from common.metaconfig import MetaConfig

class TableParser:
    # static
    tables = []
    tablesRootFilePath = None
    
    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'
    
    def __init__(self, tablesRootFilePath):
        TableParser.tablesRootFilePath = tablesRootFilePath
        self.loadTables()

    def loadTables(self, reload=False): # reload if you want to rescan the tables
        if not reload and len(TableParser.tables) != 0:
            return
        TableParser.tables = [] # clear on every load!
        count = 0
        print("Loading tables and image paths:")
        for fname in sorted(os.listdir(TableParser.tablesRootFilePath)):
            path = os.path.join(TableParser.tablesRootFilePath, fname)
            if os.path.isdir(path): # each table has its own dir
                table = Table()
                table.tableDirName = fname # set the indidvual table dir
                table.fullPathTable = path
                for fname2 in os.listdir(TableParser.tablesRootFilePath+fname):
                    path2 = os.path.join(TableParser.tablesRootFilePath+fname, fname2)
                    if not os.path.isdir(path2):
                        _, file_extension = os.path.splitext(path2)
                        if file_extension == ".vpx":
                            table.fullPathVPXfile = path2
                            count = count + 1
                            # check for addons
                            if os.path.isdir(table.fullPathTable+'/pupvideos'):
                                table.pupPackExists = True
                            if os.path.isdir(table.fullPathTable+'/pinmame/altcolor'):
                                table.altColorExists = True
                            if os.path.isdir(table.fullPathTable+'/pinmame/altsound'):
                                table.altSoundExists = True
                if table.fullPathVPXfile == None:
                    print(f"{TableParser.RED_CONSOLE_TEXT}    No .vpx found in {table.tableDirName} directory.{TableParser. RESET_CONSOLE_TEXT}")
                    continue  
                TableParser.tables.append(table)
                self.loadImagePaths(table)
                self.loadMetaData(table)
    
        print(f"  Found {count} tables (.vpx).")

    def loadImagePaths(self, Table):
        # set bg image
        bg = Table.fullPathTable + "/bg.png"
        dmd = Table.fullPathTable + "/dmd.png"
        table = Table.fullPathTable + "/table.png"
        wheel = Table.fullPathTable + "/wheel.png"
        cab = Table.fullPathTable + "/cab.png"

        if os.path.exists(bg):
            Table.BGImagePath = bg
        else:
            print(f"{TableParser.RED_CONSOLE_TEXT}  Img not found: {bg}{TableParser.RESET_CONSOLE_TEXT}")
        if os.path.exists(dmd):
            Table.DMDImagePath = dmd
        else:
            print(f"{TableParser.RED_CONSOLE_TEXT}  Img not found: {dmd}{TableParser.RESET_CONSOLE_TEXT}")
        if os.path.exists(table):
            Table.TableImagePath = table
        else:
            print(f"{TableParser.RED_CONSOLE_TEXT}  Img not found: {table}{TableParser.RESET_CONSOLE_TEXT}")
        if os.path.exists(wheel):
            Table.WheelImagePath = wheel
        else:
            print(f"{TableParser.RED_CONSOLE_TEXT}  Img not found: {wheel}{TableParser.RESET_CONSOLE_TEXT}")
        if os.path.exists(cab):
            Table.CabImagePath = cab
        else:
            print(f"{TableParser.RED_CONSOLE_TEXT}  Img not found: {cab}{TableParser.RESET_CONSOLE_TEXT}")

    def loadMetaData(self, Table):
        meta = MetaConfig(Table.fullPathTable + "/" + "meta.ini")
        Table.metaConfig = meta.config
   
    def getTable(self, index):
        return self.tables[index]
    
    def getTableCount(self):
        return len(TableParser.tables)
    
    def getAllTables(self):
        return TableParser.tables
    
    def isFavorite(self, Table):
        if Table.metaConfig['VPinFE']['favorite'] == 'true':
            return True
        else:
            return False