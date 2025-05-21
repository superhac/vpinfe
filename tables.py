import os
from pathlib import Path
import metaconfig
from pinlog import get_logger

import sys

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

    def __init__(self, tablesRootFilePath, vpinfeIniConfig):
        global logger
        logger = get_logger()

        logger.debug (f"Creating tables with {vpinfeIniConfig.get_string('Media','tableresolution','4k')} {vpinfeIniConfig.get_string('Media','tabletype','')}")
        self.tablename = vpinfeIniConfig.get_string('Media','tabletype','table').lower()
        Tables.tablesRootFilePath = tablesRootFilePath
        self.loadTables()

    def loadTables(self):
        count = 0
        logger.info("Loading tables and image paths:")
        for tabledirname in sorted(os.listdir(Tables.tablesRootFilePath)):
            tabledir = os.path.join(Tables.tablesRootFilePath, tabledirname)
            if not os.path.isdir(tabledir): # each table has its own dir
                continue
            tableInfo = TableInfo()
            tableInfo.tableDirName = tabledirname # set the indidvual table dir
            tableInfo.fullPathTable = tabledir
            for filename in os.listdir(tabledir):
                filepath = os.path.join(tabledir, filename)
                if os.path.isdir(filepath):
                    continue
                _, file_extension = os.path.splitext(filepath)
                if file_extension != ".vpx":
                    continue
                tableInfo.fullPathVPXfile = filepath
                count = count + 1
                # check for addons
                tableInfo.pupPackExists = self.dirExists(f"{tabledir}/pupvideos")
                tableInfo.altColorExists = self.dirExists(f"{tabledir}/pinmame/altcolor")
                tableInfo.altSoundExists = self.dirExists(f"{tabledir}/pinmame/altsound")
            if tableInfo.fullPathVPXfile is None:
                logger.error(f"{Tables.RED_CONSOLE_TEXT}No .vpx found in {tabledirname} directory.{Tables. RESET_CONSOLE_TEXT}")
                continue
            Tables.tables.append(tableInfo)
            self.loadImagePaths(tableInfo)
            self.loadMetaData(tableInfo)
    
        logger.info(f"Found {count} tables (.vpx).")

    def dirExists(self, dir):
        if dir is None:
            return False
        return os.path.isdir(dir)

    def findImageEndingWith(self, basePath, ending):
        logger.debug(f"Looking for files ending in {ending}.png in {basePath}")
        files = list(Path(basePath).rglob("*" + ending + ".*"))
        if not files:
            return None
        return files[0]

    def imagePath(self, path, tablePath, context):
        if path is None:
            logger.warning(f"{Tables.RED_CONSOLE_TEXT} {context} image '{path}' not found for table {tablePath}{Tables.RESET_CONSOLE_TEXT}")
            return None
        if not os.path.exists(path):
            return None
        return path

    def loadImagePaths(self, tableInfo):
        # set bg image
        bg = self.findImageEndingWith(tableInfo.fullPathTable, "bg")
        dmd = self.findImageEndingWith(tableInfo.fullPathTable, "dmd")
        table = self.findImageEndingWith(tableInfo.fullPathTable, self.tablename)
        wheel = self.findImageEndingWith(tableInfo.fullPathTable, "wheel")

        tableInfo.BGImagePath = self.imagePath(bg, tableInfo.fullPathVPXfile, 'bg')
        tableInfo.DMDImagePath = self.imagePath(dmd, tableInfo.fullPathVPXfile, 'dmd')
        tableInfo.TableImagePath = self.imagePath(table, tableInfo.fullPathVPXfile, 'table')
        tableInfo.WheelImagePath = self.imagePath(wheel, tableInfo.fullPathVPXfile, 'wheel')

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
