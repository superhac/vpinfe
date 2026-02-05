from pathlib import Path
from common.table import Table
from common.metaconfig import MetaConfig


class TableParser:
    # static console colors
    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'

    # Shared class variable - single instance across all TableParser instances
    tables: list[Table] = []

    def __init__(self, tablesRootFilePath, iniConfig=None):
        self.tablesRootFilePath = Path(tablesRootFilePath)
        self.tabletype = "table"
        if iniConfig:
            self.tabletype = iniConfig.config['Media'].get('tabletype', 'table').lower()
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
                    # Get creation time (cross-platform)
                    stat = f.stat()
                    table.creation_time = getattr(stat, 'st_birthtime', stat.st_ctime)

            if not getattr(table, "fullPathVPXfile", None):
                print(f"{self.RED_CONSOLE_TEXT}    No .vpx found in {table.tableDirName} directory.{self.RESET_CONSOLE_TEXT}")
                continue

            # check for addons
            if (table_dir / "pupvideos").is_dir():
                table.pupPackExists = True
            if (table_dir / "serum").is_dir():
                table.altColorExists = True
            if (table_dir / "vni").is_dir():
                table.vniExists = True
            if (table_dir / "pinmame" / "altsound").is_dir():
                table.altSoundExists = True

            self.loadImagePaths(table)
            self.loadMetaData(table)

            self.tables.append(table)

    def loadImagePaths(self, Table):
        table_dir = Path(Table.fullPathTable)
        medias_dir = table_dir / "medias"
        images = {
            "BGImagePath": "bg.png",
            "DMDImagePath": "dmd.png",
            "TableImagePath": f"{self.tabletype}.png",
            "WheelImagePath": "wheel.png",
            "CabImagePath": "cab.png",
            "realDMDImagePath": "realdmd.png",
            "realDMDColorImagePath": "realdmd-color.png",
            "FlyerImagePath": "flyer.png",
        }

        for attr, fname in images.items():
            # Check medias/ subfolder first, then fall back to root folder
            fpath_medias = medias_dir / fname
            fpath_root = table_dir / fname
            if fpath_medias.exists():
                setattr(Table, attr, str(fpath_medias))
            elif fpath_root.exists():
                setattr(Table, attr, str(fpath_root))

    def loadMetaData(self, Table):
        meta_path = Path(Table.fullPathTable) / f"{Table.tableDirName}.info"
        meta = MetaConfig(str(meta_path))
        Table.metaConfig = meta.data

    def getTable(self, index):
        return self.tables[index]

    def getTableCount(self):
        return len(self.tables)

    def getAllTables(self):
        return self.tables

    def isFavorite(self, Table):
        return Table.metaConfig.get("VPinFE", {}).get("favorite", "").lower() == "true"
