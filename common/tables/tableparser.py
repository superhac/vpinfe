import logging
import os
from pathlib import Path
from time import perf_counter

from common.config_access import MediaConfig
from common.media_paths import apply_media_paths
from common.tables.game_files import default_game_file, game_file_names
from common.tables.metaconfig import InvalidMetaConfigError, MetaConfig
from common.tables.table import Table
from common.tables.table_metadata import section

logger = logging.getLogger("vpinfe.common.tables.tableparser")


class TableParser:
    # static console colors
    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'

    def __init__(self, tablesRootFilePath, iniConfig=None):
        self.tablesRootFilePath = Path(tablesRootFilePath)
        self.tabletype = "table"
        self.tables: list[Table] = []
        self.missing_tables: list[dict] = []
        self.active_sets: dict[str, str] = {}
        if iniConfig:
            media_cfg = MediaConfig.from_config(iniConfig)
            self.tabletype = media_cfg.table_type
            from common.media_paths import active_set_for
            wheelset = active_set_for("wheel", media_cfg.wheelset)
            if wheelset:
                self.active_sets["wheel"] = wheelset
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
            except OSError:
                logger.exception("Failed to enumerate table directory: %s", table_dir)

            if not game_file_names(table_contents):
                logger.warning("No .vpx found in %s directory.", table.tableDirName)
                continue

            info_name = f"{table.tableDirName}.info"
            if info_name not in table_contents:
                self.missing_tables.append({
                    'folder': table.tableDirName,
                    'path': str(table_dir),
                })

            # Assets: what this table needs to play as intended, beyond the game
            # file. Media is a different thing and is loaded below. See
            # docs/conventions.md.
            if any(name.lower().endswith(".directb2s") for name in table_contents):
                table.b2sExists = True
            if "pupvideos" in table_subdirs:
                table.pupPackExists = True
            if "serum" in table_subdirs:
                table.altColorExists = True
            if "vni" in table_subdirs:
                table.vniExists = True
            if "music" in table_subdirs:
                table.musicExists = True
            if any(name.lower().endswith(".ini") for name in table_contents):
                table.iniExists = True
            if "pinmame" in table_subdirs and (table_dir / "pinmame" / "altsound").is_dir():
                table.altSoundExists = True

            self.loadMetaData(table)

            # After the metadata, so a folder with several .vpx launches the one its
            # metadata describes rather than whichever the filesystem listed first.
            recorded = section(table.metaConfig, "VPXFile").get("filename", "")
            chosen = default_game_file(table_contents, table_dir.name, recorded)
            table.fullPathVPXfile = str(table_dir / chosen)

            # Media after the default pick: tier 1 of the resolution chain keys off
            # the build that actually launches.
            self.loadImagePaths(
                table,
                table_contents=table_contents,
                has_medias_dir="medias" in table_subdirs,
                game_file_stem=Path(chosen).stem if chosen else None,
            )
            try:
                stat = os.stat(table.fullPathVPXfile)
                table.creation_time = getattr(stat, 'st_birthtime', stat.st_ctime)
            except OSError:
                logger.warning("Could not stat game file: %s", table.fullPathVPXfile)

            self.tables.append(table)

        elapsed = perf_counter() - started_at
        logger.debug(
            "Load completed in %.3fs: loaded=%s missing_info=%s",
            elapsed,
            len(self.tables),
            len(self.missing_tables)
        )

    def loadImagePaths(self, Table, table_contents=None, has_medias_dir=None,
                       game_file_stem=None):
        table_dir = Path(Table.fullPathTable)
        medias_dir = table_dir / "medias"

        # Batch directory listings to minimize disk calls
        if table_contents is None:
            try:
                table_contents = set(os.listdir(str(table_dir)))
            except Exception:
                table_contents = set()

        medias_contents: set[str] = set()
        if has_medias_dir if has_medias_dir is not None else medias_dir.is_dir():
            try:
                for dirpath, _dirs, files in os.walk(str(medias_dir)):
                    rel = os.path.relpath(dirpath, str(medias_dir))
                    for fname in files:
                        medias_contents.add(
                            fname if rel == "." else f"{rel}/{fname}".replace(os.sep, "/"))
            except Exception:
                medias_contents = set()
        apply_media_paths(Table, table_contents, medias_contents, self.tabletype,
                          game_file_stem, self.active_sets or None)

    def loadMetaData(self, Table):
        meta_path = Path(Table.fullPathTable) / f"{Table.tableDirName}.info"
        try:
            meta = MetaConfig(str(meta_path))
        except InvalidMetaConfigError as exc:
            logger.error("Invalid metadata for table '%s': %s", Table.tableDirName, exc)
            raise
        Table.metaConfig = meta.data

    def getTable(self, index):
        return self.tables[index]

    def getTableCount(self):
        return len(self.tables)

    def getAllTables(self):
        return list(self.tables)

    def getMissingTables(self):
        return [dict(row) for row in self.missing_tables]

    def isFavorite(self, Table):
        return Table.metaConfig.get("VPinFE", {}).get("favorite", "").lower() == "true"
