import os
from pathlib import Path
import logging
from time import perf_counter
from common.config_access import MediaConfig
from common.media_paths import apply_media_paths
from common.table import Table
from common.info_restore import (
    BACKUP_MARKER,
    backup_names,
    converted_by_newer,
    restorable_backup,
)
from common.metaconfig import InvalidMetaConfigError, MetaConfig


logger = logging.getLogger("vpinfe.common.tableparser")


class TableParser:
    # static console colors
    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'

    def __init__(self, tablesRootFilePath, iniConfig=None):
        self.tablesRootFilePath = Path(tablesRootFilePath)
        self.tabletype = "table"
        self.tables: list[Table] = []
        self.missing_tables: list[dict] = []
        self.unreadable_tables: list[dict] = []
        if iniConfig:
            self.tabletype = MediaConfig.from_config(iniConfig).table_type
        self.loadTables()

    def loadTables(self, reload=False):  # reload if you want to rescan the tables
        if not reload and self.tables:
            return

        started_at = perf_counter()
        self.tables.clear()
        self.missing_tables.clear()
        self.unreadable_tables.clear()

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

            # check for addons
            if any(name.lower().endswith(".directb2s") for name in table_contents):
                table.b2sExists = True
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
            try:
                self.loadMetaData(table)
            except InvalidMetaConfigError as exc:
                # One unreadable file used to stop the whole library loading, so a single
                # truncated .info left the app with no tables at all. Drop the one table
                # and keep going: excluded rather than loaded empty, because loading it
                # empty would let the next write overwrite a file we could not read.
                self.unreadable_tables.append({
                    'folder': table.tableDirName,
                    'path': str(table_dir),
                    'error': str(exc),
                })
                logger.error("Skipping table with unreadable metadata: %s", exc)
                continue

            # Only a table a newer VPinFE upgraded has anything to put back, and only then
            # is a saved copy worth opening to check we can read it.
            stamps = backup_names(table_contents, info_name)
            table.info_restorable = bool(
                converted_by_newer(table.metaConfig)
                and stamps
                and restorable_backup(table_dir, names=table_contents))
            if stamps:
                table.info_backup_stamp = stamps[0].rsplit(BACKUP_MARKER, 1)[-1]

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
        apply_media_paths(Table, table_contents, medias_contents, self.tabletype)

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

    def getUnreadableTables(self):
        """Folders whose .info could not be read, so the table was left out."""
        return [dict(row) for row in self.unreadable_tables]

    def getMissingTables(self):
        return [dict(row) for row in self.missing_tables]

    def isFavorite(self, Table):
        return Table.metaConfig.get("VPinFE", {}).get("favorite", "").lower() == "true"
