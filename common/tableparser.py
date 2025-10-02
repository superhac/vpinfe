from pathlib import Path
from common.table import Table
from common.metaconfig import MetaConfig


class TableParser:
    # static console colors
    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'

    def __init__(self, tablesRootFilePath):
        self.tablesRootFilePath = Path(tablesRootFilePath)
        self.tables: list[Table] = []
        self.loadTables()

    def loadTables(self, reload=False):  # reload if you want to rescan the tables
        if not reload and self.tables:
            return

        self.tables.clear()
        print("Loading tables and image paths:")

        for table_dir in sorted(self.tablesRootFilePath.iterdir()):
            if not table_dir.is_dir():
                continue

            table = Table()
            table.tableDirName = table_dir.name
            table.fullPathTable = str(table_dir)

            # search for .vpx file
            for f in table_dir.iterdir():
                if f.is_file() and f.suffix.lower() == ".vpx":
                    table.fullPathVPXfile = str(f)

            if not getattr(table, "fullPathVPXfile", None):
                print(f"{self.RED_CONSOLE_TEXT}    No .vpx found in {table.tableDirName} directory.{self.RESET_CONSOLE_TEXT}")
                continue

            # check for addons
            if (table_dir / "pupvideos").is_dir():
                table.pupPackExists = True
            if (table_dir / "pinmame" / "altcolor").is_dir():
                table.altColorExists = True
            if (table_dir / "pinmame" / "altsound").is_dir():
                table.altSoundExists = True

            self.loadImagePaths(table)
            self.loadMetaData(table)

            self.tables.append(table)

    def loadImagePaths(self, Table):
        table_dir = Path(Table.fullPathTable)
        images = {
            "BGImagePath": "bg.png",
            "DMDImagePath": "dmd.png",
            "TableImagePath": "table.png",
            "WheelImagePath": "wheel.png",
            "CabImagePath": "cab.png",
            "realDMDImagePath":"realdmd.png",
            "realDMDColorImagePath" :"realdmd-color.png",
        }

        for attr, fname in images.items():
            fpath = table_dir / fname
            if fpath.exists():
                setattr(Table, attr, str(fpath))
            else:
                print(f"{self.RED_CONSOLE_TEXT}  Img not found: {fpath}{self.RESET_CONSOLE_TEXT}")

    def loadMetaData(self, Table):
        meta_path = Path(Table.fullPathTable) / "meta.ini"
        meta = MetaConfig(str(meta_path))
        Table.metaConfig = meta.config

    def getTable(self, index):
        return self.tables[index]

    def getTableCount(self):
        return len(self.tables)

    def getAllTables(self):
        return self.tables

    def isFavorite(self, Table):
        return Table.metaConfig.get("VPinFE", {}).get("favorite", "").lower() == "true"
