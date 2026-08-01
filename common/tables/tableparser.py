import logging
import os
from pathlib import Path
from time import perf_counter

from common.config_access import MediaConfig
from common.media_paths import apply_media_paths
from common.tables.game_files import (
    default_game_file,
    game_file_names,
    recorded_default,
)
from common.tables.info_migration import backup_names, restorable_backup
from common.tables.metaconfig import InvalidMetaConfigError, MetaConfig
from common.tables.table import Table
from common.tables.table_metadata import section, vpinfe_section

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
        self.unreadable_tables: list[dict] = []
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
        self.unreadable_tables.clear()

        if not self.tablesRootFilePath.exists():
            return

        logger.info("Loading tables and image paths...")
        for table_dir in sorted(self.tablesRootFilePath.iterdir()):
            if not table_dir.is_dir():
                continue
            if table_dir.name.startswith('.'):
                continue
            table = self._build_table(table_dir)
            if table is not None:
                self.tables.append(table)

        elapsed = perf_counter() - started_at
        logger.debug(
            "Load completed in %.3fs: loaded=%s missing_info=%s",
            elapsed,
            len(self.tables),
            len(self.missing_tables)
        )

    def _build_table(self, table_dir):
        """One table folder, read from disk. Returns None when it holds no game file.

        The whole of what a scan does per table, so refreshing one costs one folder
        rather than the library.
        """
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
                        # Folded like the extension checks below, and like the
                        # API's own listing: a folder someone named PUPVideos
                        # holds a PUP pack whatever the shift key was doing.
                        table_subdirs.add(entry.name.lower())
                        continue
                    table_contents.add(entry.name)
        except OSError:
            logger.exception("Failed to enumerate table directory: %s", table_dir)

        if not game_file_names(table_contents):
            logger.warning("No .vpx found in %s directory.", table.tableDirName)
            return None

        info_name = f"{table.tableDirName}.info"
        # Only folders holding a backup open one.
        table.info_restorable = bool(
            backup_names(table_contents, info_name)
            and restorable_backup(table_dir, names=table_contents))
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

        try:
            self.loadMetaData(table)
        except InvalidMetaConfigError as exc:
            # This used to stop the whole library loading. Excluded rather than loaded
            # empty, so nothing can write over a file we could not read.
            self.unreadable_tables.append({
                'folder': table.tableDirName,
                'path': str(table_dir),
                'error': str(exc),
            })
            logger.error("Skipping table with unreadable metadata: %s", exc)
            return None

        # After the metadata, so a folder with several .vpx launches the one its
        # metadata describes rather than whichever the filesystem listed first.
        recorded = recorded_default(vpinfe_section(table.metaConfig))
        chosen = default_game_file(table_contents, table_dir.name, recorded)
        table.fullPathVPXfile = str(table_dir / chosen)

        # Media after the default pick: tier 1 of the resolution chain keys off
        # the game file that actually launches.
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

        return table


    def reload_table(self, table_dir):
        """Re-read one table folder in place. Returns the table, or None if it is gone.

        A rating, a rename or an import changes one folder, and rescanning the library
        to see it costs the whole library - on a network share, minutes of it.
        """
        table_dir = Path(table_dir)
        target = str(table_dir)
        self.missing_tables = [row for row in self.missing_tables if row["path"] != target]
        self.unreadable_tables = [r for r in self.unreadable_tables if r["path"] != target]

        table = self._build_table(table_dir) if table_dir.is_dir() else None
        for index, existing in enumerate(self.tables):
            if existing.fullPathTable == target:
                if table is None:
                    del self.tables[index]        # the folder went away
                else:
                    self.tables[index] = table
                return table

        if table is not None:
            self.tables.append(table)             # a folder that was not there before
        return table

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
        Table.info_pending_upgrade = meta.pending_migration

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
        return vpinfe_section(Table.metaConfig).get("favorite", "").lower() == "true"
