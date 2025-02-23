import os
from pathlib import Path

class TableInfo:
    tableDirName = None
    fullPathTable = None
    fullPathVPXfile = None

    BGImagePath = None
    DMDImagePath = None
    TableImagePath = None

class Tables:
    # static
    tables = []
    tablesRootFilePath = None

    def __init__(self, tablesRootFilePath):
        Tables.tablesRootFilePath = tablesRootFilePath
        self.loadTables()

    def loadTables(self):
        print("Loading table images")
        for fname in os.listdir(Tables.tablesRootFilePath):
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
                Tables.tables.append(tableInfo)
                self.loadImagePaths(tableInfo)
        
        #for table in Tables.tables:
           # print(f'Table dir Name: "{table.tableDirName}" Table dir path: "{table.fullPathTable}" Full VPX path: "{table.fullPathVPXfile}"')

    def loadImagePaths(self, tableInfo):
        # set bg image
        bg = tableInfo.fullPathTable + "/bg.png"
        dmd = tableInfo.fullPathTable + "/dmd.png"
        table = tableInfo.fullPathTable + "/table.png"

        if os.path.exists(bg):
            tableInfo.BGImagePath = bg
        else:
            print("     Img not found: " + bg)
        if os.path.exists(dmd):
            tableInfo.DMDImagePath = dmd
        else:
            print("     Img not found: " + dmd)
        if os.path.exists(table):
            tableInfo.TableImagePath = table
        else:
            print("     Img not found: " + table)

    def getTable(self, index):
        return self.tables[index]
    
    def getTableCount(self):
        return len(Tables.tables)
    
    def getAllTables():
        return Tables.tables