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
from common.tables.info_migration import (
    BACKUP_MARKER,
    backup_names,
    restorable_backup,
)
from common.tables.metaconfig import InvalidMetaConfigError, MetaConfig
from common.tables.game import Game
from common.tables.game_metadata import section, vpinfe_section

logger = logging.getLogger("vpinfe.common.tables.gameparser")


class GameParser:
    # static console colors
    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'

    def __init__(self, gamesRootFilePath, iniConfig=None):
        self.gamesRootFilePath = Path(gamesRootFilePath)
        self.tabletype = "table"
        self.tables: list[Game] = []
        self.missing_games: list[dict] = []
        self.unreadable_games: list[dict] = []
        self.active_sets: dict[str, str] = {}
        if iniConfig:
            media_cfg = MediaConfig.from_config(iniConfig)
            self.tabletype = media_cfg.playfield_variant
            from common.media_paths import active_set_for
            wheelset = active_set_for("wheel", media_cfg.wheelset)
            if wheelset:
                self.active_sets["wheel"] = wheelset
        # Constructing reads the library; a loadTables(reload=True) after it reads it twice.
        self.loadGames()

    def loadGames(self, reload=False):  # reload if you want to rescan the tables
        if not reload and self.tables:
            return

        started_at = perf_counter()
        self.tables.clear()
        self.missing_games.clear()
        self.unreadable_games.clear()

        if not self.gamesRootFilePath.exists():
            return

        logger.info("Loading tables and image paths...")
        for game_dir in sorted(self.gamesRootFilePath.iterdir()):
            if not game_dir.is_dir():
                continue
            if game_dir.name.startswith('.'):
                continue
            game = self._build_game(game_dir)
            if game is not None:
                self.tables.append(game)

        elapsed = perf_counter() - started_at
        logger.debug(
            "Load completed in %.3fs: loaded=%s missing_info=%s",
            elapsed,
            len(self.tables),
            len(self.missing_games)
        )

    def _build_game(self, game_dir):
        """One table folder, read from disk. Returns None when it holds no game file.

        The whole of what a scan does per table, so refreshing one costs one folder
        rather than the library.
        """
        game = Game()
        game.tableDirName = game_dir.name
        game.fullPathTable = str(game_dir)

        game_contents = set()
        game_subdirs = set()

        # Search with scandir to avoid per-entry pathlib stat calls on slow volumes.
        try:
            with os.scandir(game_dir) as entries:
                for entry in entries:
                    if entry.is_dir():
                        # Folded like the extension checks below, and like the
                        # API's own listing: a folder someone named PUPVideos
                        # holds a PUP pack whatever the shift key was doing.
                        game_subdirs.add(entry.name.lower())
                        continue
                    game_contents.add(entry.name)
        except OSError:
            logger.exception("Failed to enumerate table directory: %s", game_dir)

        if not game_file_names(game_contents):
            logger.warning("No .vpx found in %s directory.", game.tableDirName)
            return None

        info_name = f"{game.tableDirName}.info"
        # Only folders holding a backup open one.
        stamps = backup_names(game_contents, info_name)
        game.info_restorable = bool(
            stamps and restorable_backup(game_dir, names=game_contents))
        if stamps:
            game.info_backup_stamp = stamps[0].rsplit(BACKUP_MARKER, 1)[-1]
        if info_name not in game_contents:
            self.missing_games.append({
                'folder': game.tableDirName,
                'path': str(game_dir),
            })

        # Assets: what this table needs to play as intended, beyond the game
        # file. Media is a different thing and is loaded below. See
        # docs/conventions.md.
        if any(name.lower().endswith(".directb2s") for name in game_contents):
            game.b2sExists = True
        if "pupvideos" in game_subdirs:
            game.pupPackExists = True
        if "serum" in game_subdirs:
            game.altColorExists = True
        if "vni" in game_subdirs:
            game.vniExists = True
        if "music" in game_subdirs:
            game.musicExists = True
        if any(name.lower().endswith(".ini") for name in game_contents):
            game.iniExists = True
        if "pinmame" in game_subdirs and (game_dir / "pinmame" / "altsound").is_dir():
            game.altSoundExists = True

        try:
            self.loadMetaData(game)
        except InvalidMetaConfigError as exc:
            # This used to stop the whole library loading. Excluded rather than loaded
            # empty, so nothing can write over a file we could not read.
            self.unreadable_games.append({
                'folder': game.tableDirName,
                'path': str(game_dir),
                'error': str(exc),
            })
            logger.error("Skipping table with unreadable metadata: %s", exc)
            return None

        # After the metadata, so a folder with several .vpx launches the one its
        # metadata describes rather than whichever the filesystem listed first.
        recorded = recorded_default(vpinfe_section(game.metaConfig))
        chosen = default_game_file(game_contents, game_dir.name, recorded)
        game.fullPathVPXfile = str(game_dir / chosen)

        # Media after the default pick: tier 1 of the resolution chain keys off
        # the game file that actually launches.
        self.loadImagePaths(
            game,
            game_contents=game_contents,
            has_medias_dir="medias" in game_subdirs,
            game_file_stem=Path(chosen).stem if chosen else None,
        )
        try:
            stat = os.stat(game.fullPathVPXfile)
            game.creation_time = getattr(stat, 'st_birthtime', stat.st_ctime)
        except OSError:
            logger.warning("Could not stat game file: %s", game.fullPathVPXfile)

        return game


    def reload_game(self, game_dir):
        """Re-read one table folder in place. Returns the table, or None if it is gone.

        A rating, a rename or an import changes one folder, and rescanning the library
        to see it costs the whole library - on a network share, minutes of it.
        """
        game_dir = Path(game_dir)
        target = str(game_dir)
        self.missing_games = [row for row in self.missing_games if row["path"] != target]
        self.unreadable_games = [r for r in self.unreadable_games if r["path"] != target]

        game = self._build_game(game_dir) if game_dir.is_dir() else None
        for index, existing in enumerate(self.tables):
            if existing.fullPathTable == target:
                if game is None:
                    del self.tables[index]        # the folder went away
                else:
                    self.tables[index] = game
                return game

        if game is not None:
            self.tables.append(game)             # a folder that was not there before
        return game

    def loadImagePaths(self, Game, game_contents=None, has_medias_dir=None,
                       game_file_stem=None):
        game_dir = Path(Game.fullPathTable)
        medias_dir = game_dir / "medias"

        # Batch directory listings to minimize disk calls
        if game_contents is None:
            try:
                game_contents = set(os.listdir(str(game_dir)))
            except Exception:
                game_contents = set()

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
        apply_media_paths(Game, game_contents, medias_contents, self.tabletype,
                          game_file_stem, self.active_sets or None)

    def loadMetaData(self, Game):
        meta_path = Path(Game.fullPathTable) / f"{Game.tableDirName}.info"
        try:
            meta = MetaConfig(str(meta_path))
        except InvalidMetaConfigError as exc:
            logger.error("Invalid metadata for table '%s': %s", Game.tableDirName, exc)
            raise
        Game.metaConfig = meta.data
        Game.info_pending_upgrade = meta.pending_migration

    def getGame(self, index):
        return self.tables[index]

    def getGameCount(self):
        return len(self.tables)

    def getAllGames(self):
        return list(self.tables)

    def getUnreadableGames(self):
        """Folders whose .info could not be read, so the table was left out."""
        return [dict(row) for row in self.unreadable_games]

    def getMissingGames(self):
        return [dict(row) for row in self.missing_games]

    def isFavorite(self, Game):
        return vpinfe_section(Game.metaConfig).get("favorite", "").lower() == "true"
