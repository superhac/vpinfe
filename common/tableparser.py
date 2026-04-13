import os
from pathlib import Path
import logging
from time import perf_counter
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

        started_at = perf_counter()
        self.tables.clear()
        self.missing_tables.clear()

        if not self.tablesRootFilePath.exists():
            return

        logger.info("Loading tables and image paths...")
        for table_dir in sorted(self.tablesRootFilePath.iterdir()):
            if not table_dir.is_dir():
                continue
            if table_dir.name.startswith('.'):
                continue

            table = Table()
            table.tableDirName = table_dir.name
            table.fullPathTable = str(table_dir)
            table_contents = set()
            table_subdirs = set()

            # Search with scandir to avoid per-entry pathlib stat calls on slow volumes.
            try:
                with os.scandir(table_dir) as entries:
                    for entry in entries:
                        if entry.is_dir():
                            table_subdirs.add(entry.name)
                            continue
                        table_contents.add(entry.name)
                        if getattr(table, "fullPathVPXfile", None) or not entry.name.lower().endswith('.vpx'):
                            continue
                        table.fullPathVPXfile = entry.path
                        stat = entry.stat()
                        table.creation_time = getattr(stat, 'st_birthtime', stat.st_ctime)
            except OSError:
                logger.exception("Failed to enumerate table directory: %s", table_dir)

            if not getattr(table, "fullPathVPXfile", None):
                logger.warning("No .vpx found in %s directory.", table.tableDirName)
                continue

            info_name = f"{table.tableDirName}.info"
            if info_name not in table_contents:
                self.missing_tables.append({
                    'folder': table.tableDirName,
                    'path': str(table_dir),
                })
                continue

            # check for addons
            if "pupvideos" in table_subdirs:
                table.pupPackExists = True
            if "serum" in table_subdirs:
                table.altColorExists = True
            if "vni" in table_subdirs:
                table.vniExists = True
            if "pinmame" in table_subdirs and (table_dir / "pinmame" / "altsound").is_dir():
                table.altSoundExists = True

            self.loadImagePaths(
                table,
                table_contents=table_contents,
                has_medias_dir="medias" in table_subdirs,
            )
            self.loadMetaData(table)

            self.tables.append(table)

        elapsed = perf_counter() - started_at
        logger.debug(
            "Load completed in %.3fs: loaded=%s missing_info=%s",
            elapsed,
            len(self.tables),
            len(self.missing_tables)
        )

    def loadImagePaths(self, Table, table_contents=None, has_medias_dir=None):
        table_dir = Path(Table.fullPathTable)
        medias_dir = table_dir / "medias"

        # Batch directory listings to minimize disk calls
        if table_contents is None:
            try:
                table_contents = set(os.listdir(str(table_dir)))
            except Exception:
                table_contents = set()

        try:
            medias_contents = set(os.listdir(str(medias_dir))) if (has_medias_dir if has_medias_dir is not None else medias_dir.is_dir()) else set()
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
