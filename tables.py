import os
from pathlib import Path
import metaconfig

class TableInfo:
    tableDirName = None
    fullPathTable = None
    fullPathVPXfile = None
    
    pupPackExists = False
    altColorExists = False
    altSoundExists = False

    BGImagePath = None
    DMDImagePath = None
    TableImagePath = None
    WheelImagePath = None
    
    metaConfig = None
    
class Tables:
    # static
    tables = []
    tablesRootFilePath = None
    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'

    def __init__(self, tablesRootFilePath):
        Tables.tablesRootFilePath = tablesRootFilePath
        self.loadTables()

    def loadTables(self):
        count = 0
        print("Loading tables and image paths:")
        for fname in sorted(os.listdir(Tables.tablesRootFilePath)):
            path = os.path.join(Tables.tablesRootFilePath, fname)
            if os.path.isdir(path): # each table has its own dir
                tableInfo = TableInfo()
                tableInfo.tableDirName = fname # set the indidvual table dir
                tableInfo.fullPathTable = path
                for fname2 in os.listdir(Tables.tablesRootFilePath+fname):
                    path2 = os.path.join(Tables.tablesRootFilePath+fname, fname2)
                    if not os.path.isdir(path2):
                        _, file_extension = os.path.splitext(path2)
                        if file_extension == ".vpx":
                            tableInfo.fullPathVPXfile = path2
                            count = count + 1
                            # check for addons
                            if os.path.isdir(tableInfo.fullPathTable+'/pupvideos'):
                                tableInfo.pupPackExists = True
                            if os.path.isdir(tableInfo.fullPathTable+'/pinmame/altcolor'):
                                tableInfo.altColorExists = True
                            if os.path.isdir(tableInfo.fullPathTable+'/pinmame/altsound'):
                                tableInfo.altSoundExists = True
                if tableInfo.fullPathVPXfile == None:
                    print(f"{Tables.RED_CONSOLE_TEXT}    No .vpx found in {tableInfo.tableDirName} directory.{Tables. RESET_CONSOLE_TEXT}")
                    continue  
                Tables.tables.append(tableInfo)
                self.loadImagePaths(tableInfo)
                self.loadMetaData(tableInfo)
    
        print(f"  Found {count} tables (.vpx).")

    def loadImagePaths(self, tableInfo):
        # set bg image
        bg = tableInfo.fullPathTable + "/bg.png"
        dmd = tableInfo.fullPathTable + "/dmd.png"
        table = tableInfo.fullPathTable + "/table.png"
        wheel = tableInfo.fullPathTable + "/wheel.png"

        if os.path.exists(bg):
            tableInfo.BGImagePath = bg
        else:
            print(f"{Tables.RED_CONSOLE_TEXT}  Img not found: {bg}{Tables.RESET_CONSOLE_TEXT}")
        if os.path.exists(dmd):
            tableInfo.DMDImagePath = dmd
        else:
            print(f"{Tables.RED_CONSOLE_TEXT}  Img not found: {dmd}{Tables.RESET_CONSOLE_TEXT}")
        if os.path.exists(table):
            tableInfo.TableImagePath = table
        else:
            print(f"{Tables.RED_CONSOLE_TEXT}  Img not found: {table}{Tables.RESET_CONSOLE_TEXT}")
        if os.path.exists(wheel):
            tableInfo.WheelImagePath = wheel
        else:
            print(f"{Tables.RED_CONSOLE_TEXT}  Img not found: {wheel}{Tables.RESET_CONSOLE_TEXT}")
            

    def loadMetaData(self, tableInfo):
        meta = metaconfig.MetaConfig(tableInfo.fullPathTable + "/" + "meta.ini")
        tableInfo.metaConfig = meta.config
   
    def getTable(self, index):
        return self.tables[index]
    
    def getTableCount(self):
        return len(Tables.tables)
    
    def getAllTables():
        return Tables.tables
    
    def isFavorite(self, tableInfo):
        if tableInfo.metaConfig['VPinFE']['favorite'] == 'true':
            return True
        else:
            return False