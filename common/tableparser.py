import os
from pathlib import Path
import logging
from common.table import Table
from common.metaconfig import MetaConfig


logger = logging.getLogger("vpinfe.common.tableparser")


class TableParser:
    # static console colors
    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'

    # Shared class variable - single instance across all TableParser instances
    tables: list[Table] = []
    missing_tables: list[dict] = []

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
        self.missing_tables.clear()
        logger.info("Loading tables and image paths:")

        if not self.tablesRootFilePath.exists():
            return

        for table_dir in sorted(self.tablesRootFilePath.iterdir()):
            if not table_dir.is_dir():
                continue

            try:
                dir_entries = sorted(os.listdir(table_dir))
            except Exception:
                logger.warning("Could not list %s directory.", table_dir.name)
                continue

            vpx_names = [name for name in dir_entries if name.lower().endswith(".vpx")]
            if not vpx_names:
                logger.warning("No .vpx found in %s directory.", table_dir.name)
                continue

            info_name = f"{table_dir.name}.info"
            if info_name not in dir_entries:
                self.missing_tables.append({
                    'folder': table_dir.name,
                    'path': str(table_dir),
                })
                continue

            table = Table()
            table.tableDirName = table_dir.name
            table.fullPathTable = str(table_dir)

            vpx_path = table_dir / vpx_names[0]
            table.fullPathVPXfile = str(vpx_path)
            stat = vpx_path.stat()
            table.creation_time = getattr(stat, 'st_birthtime', stat.st_ctime)

            # check for addons
            dir_entries_set = set(dir_entries)
            if "pupvideos" in dir_entries_set and (table_dir / "pupvideos").is_dir():
                table.pupPackExists = True
            if "serum" in dir_entries_set and (table_dir / "serum").is_dir():
                table.altColorExists = True
            if "vni" in dir_entries_set and (table_dir / "vni").is_dir():
                table.vniExists = True
            if "pinmame" in dir_entries_set and (table_dir / "pinmame" / "altsound").is_dir():
                table.altSoundExists = True

            self.loadImagePaths(table, dir_entries_set)
            self.loadMetaData(table)

            self.tables.append(table)

    def loadImagePaths(self, Table, table_contents=None):
        table_dir = Path(Table.fullPathTable)
        medias_dir = table_dir / "medias"
        if table_contents is None:
            try:
                table_contents = set(os.listdir(table_dir))
            except Exception:
                table_contents = set()
        try:
            medias_contents = set(os.listdir(medias_dir)) if "medias" in table_contents and medias_dir.is_dir() else set()
        except Exception:
            medias_contents = set()
        images = {
            "BGImagePath": "bg.png",
            "DMDImagePath": "dmd.png",
            "TableImagePath": f"{self.tabletype}.png",
            "FSSImagePath": "fss.png",
            "WheelImagePath": "wheel.png",
            "CabImagePath": "cab.png",
            "realDMDImagePath": "realdmd.png",
            "realDMDColorImagePath": "realdmd-color.png",
            "FlyerImagePath": "flyer.png",
        }

        videos = {
            "TableVideoPath": f"{self.tabletype}.mp4",
            "BGVideoPath": "bg.mp4",
            "DMDVideoPath": "dmd.mp4",
        }

        audio = {
            "AudioPath": "audio.mp3",
        }

        for attr, fname in {**images, **videos, **audio}.items():
            if fname in medias_contents:
                setattr(Table, attr, str(medias_dir / fname))
            elif fname in table_contents:
                setattr(Table, attr, str(table_dir / fname))

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

    def getMissingTables(self):
        return self.missing_tables

    def isFavorite(self, Table):
        return Table.metaConfig.get("VPinFE", {}).get("favorite", "").lower() == "true"
