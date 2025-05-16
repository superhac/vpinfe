import os
from pathlib import Path
import metaconfig
from logger import get_logger

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
    logger = None
    
class Tables:
    # static
    tables = []
    tablesRootFilePath = None
    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'

    def __init__(self, tablesRootFilePath):
        global logger
        logger = get_logger()
        Tables.tablesRootFilePath = tablesRootFilePath
        self.loadTables()

    def loadTables(self):
        count = 0
        logger.info("Loading tables and image paths:")
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
                    logger.error(f"{Tables.RED_CONSOLE_TEXT}No .vpx found in {tableInfo.tableDirName} directory.{Tables. RESET_CONSOLE_TEXT}")
                    continue  
                Tables.tables.append(tableInfo)
                self.loadImagePaths(tableInfo)
                self.loadMetaData(tableInfo)
    
        logger.info(f"Found {count} tables (.vpx).")

    def findImageEndingWith(self, basePath, ending):
        files = list(Path(basePath).rglob("*" + ending + ".*"))
        if not files:
            return None
        return files[0]

    def loadImagePaths(self, tableInfo):
        # set bg image
        bg = self.findImageEndingWith(tableInfo.fullPathTable, "bg")
        dmd = self.findImageEndingWith(tableInfo.fullPathTable, "dmd")
        table = self.findImageEndingWith(tableInfo.fullPathTable, "table")
        wheel = self.findImageEndingWith(tableInfo.fullPathTable, "wheel")

        if bg and os.path.exists(bg):
            tableInfo.BGImagePath = bg
        else:
            logger.warning(f"{Tables.RED_CONSOLE_TEXT} bg image '{bg}' not found for table {tableInfo.fullPathVPXfile}{Tables.RESET_CONSOLE_TEXT}")
        if dmd and os.path.exists(dmd):
            tableInfo.DMDImagePath = dmd
        else:
            logger.warning(f"{Tables.RED_CONSOLE_TEXT} dmd image '{dmd}' not found for table {tableInfo.fullPathVPXfile}{Tables.RESET_CONSOLE_TEXT}")
        if table and os.path.exists(table):
            tableInfo.TableImagePath = table
        else:
            logger.warning(f"{Tables.RED_CONSOLE_TEXT} table image ''{table}' not found for table {tableInfo.fullPathVPXfile}{Tables.RESET_CONSOLE_TEXT}")
        if wheel and os.path.exists(wheel):
            tableInfo.WheelImagePath = wheel
        else:
            logger.warning(f"{Tables.RED_CONSOLE_TEXT} wheel image '{wheel}' not found for table {tableInfo.fullPathVPXfile}{Tables.RESET_CONSOLE_TEXT}")
            

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
