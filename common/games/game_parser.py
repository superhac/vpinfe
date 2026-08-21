"""Walking the library folder and turning what is there into games.

Scanning is almost entirely waiting on the filesystem - a real library often sits on
a network share - so folders are read in parallel above a threshold.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from common.config_access import MediaConfig
from common.games.game import Game
from common.games.game_metadata import vpinfe_section
from common.games.info_file import InvalidMetaConfigError, MetaConfig
from common.games.info_migration import (
    BACKUP_MARKER,
    backup_names,
    restorable_backup,
)
from common.games.tables import (
    default_table,
    recorded_default,
    table_entries,
    table_names,
)
from common.media_specs import apply_media_specs, resolve_media_by_table

# Below this many folders the pool costs more than it saves.
_PARALLEL_SCAN_THRESHOLD = 12
# Enough to cover network latency without flooding a share. Measured on NFS: 16 threads
# reached 0.11s where one took 1.02s, and 32 bought only 0.02s more.
_SCAN_WORKERS = 16

logger = logging.getLogger("vpinfe.common.games.game_parser")


class GameParser:
    # static console colors
    """One pass over the library folder, turning each subfolder into a Game."""

    RED_CONSOLE_TEXT = '\033[31m'
    RESET_CONSOLE_TEXT = '\033[0m'

    def __init__(self, gamesRootFilePath, iniConfig=None):
        self.gamesRootFilePath = Path(gamesRootFilePath)
        self.playfieldvariant = "table"
        self.games: list[Game] = []
        self.missing_games: list[dict] = []
        self.unreadable_games: list[dict] = []
        self.active_sets: dict[str, str] = {}
        if iniConfig:
            media_cfg = MediaConfig.from_config(iniConfig)
            self.playfieldvariant = media_cfg.playfield_variant
            from common.media_specs import active_set_for
            wheelset = active_set_for("wheel", media_cfg.wheelset)
            if wheelset:
                self.active_sets["wheel"] = wheelset
        # Constructing reads the library; a loadGames(reload=True) after it reads it twice.
        self.loadGames()

    def loadGames(self, reload=False):  # reload if you want to rescan the games
        if not reload and self.games:
            return

        started_at = perf_counter()
        self.games.clear()
        self.missing_games.clear()
        self.unreadable_games.clear()

        if not self.gamesRootFilePath.exists():
            return

        logger.info("Loading games and image paths...")
        folders = [d for d in sorted(self.gamesRootFilePath.iterdir())
                   if d.is_dir() and not d.name.startswith('.')]

        # Reading a folder is almost entirely waiting: on the network share a real
        # library lives on, the directory listings are 6.5s of a 7.4s scan and the
        # parsing is under a second of it. Threads cover that wait - measured 1.02s to
        # 0.11s across 654 folders - and the GIL costs nothing because nothing here is
        # computing. A local disk sees a smaller win from the same change.
        for game, missing, unreadable in self._scan_folders(folders):
            self.missing_games.extend(missing)
            self.unreadable_games.extend(unreadable)
            if game is not None:
                self.games.append(game)

        elapsed = perf_counter() - started_at
        logger.debug(
            "Load completed in %.3fs: loaded=%s missing_info=%s",
            elapsed,
            len(self.games),
            len(self.missing_games)
        )

    def _scan_folders(self, folders):
        """Every folder read, in the order they were listed.

        Results are collected in order rather than as they finish: the library is sorted,
        and a scan whose output depended on which network reads returned first would make
        the wheel's order a race. `_build_game` reports what it found rather than
        appending to the parser, because two threads appending to one list is how a
        shared-state bug gets written.
        """
        if len(folders) < _PARALLEL_SCAN_THRESHOLD:
            return [self._scan_one(d) for d in folders]
        workers = min(_SCAN_WORKERS, len(folders))
        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix="library-scan") as pool:
            return list(pool.map(self._scan_one, folders))

    def _scan_one(self, game_dir):
        """One folder, with what it found kept local to this call."""
        missing, unreadable = [], []
        game = self._build_game(game_dir, missing=missing, unreadable=unreadable)
        return game, missing, unreadable

    def _build_game(self, game_dir, *, missing=None, unreadable=None):
        """One game folder, read from disk. Returns None when it holds no table.

        The whole of what a scan does per game, so refreshing one costs one folder
        rather than the library.
        """
        game = Game()
        game.gameDirName = game_dir.name
        game.fullPathGame = str(game_dir)

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
            logger.exception("Failed to enumerate game directory: %s", game_dir)

        game.table_files = table_names(game_contents)
        if not game.table_files:
            logger.warning("No .vpx found in %s directory.", game.gameDirName)
            return None

        info_name = f"{game.gameDirName}.info"
        # Only folders holding a backup open one.
        stamps = backup_names(game_contents, info_name)
        game.info_restorable = bool(
            stamps and restorable_backup(game_dir, names=game_contents))
        if stamps:
            game.info_backup_stamp = stamps[0].rsplit(BACKUP_MARKER, 1)[-1]
        if info_name not in game_contents:
            (self.missing_games if missing is None else missing).append({
                'folder': game.gameDirName,
                'path': str(game_dir),
            })

        # Assets: what this game needs to play as intended, beyond the table
        # itself. Media is a different thing and is loaded below. See
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
            (self.unreadable_games if unreadable is None else unreadable).append({
                'folder': game.gameDirName,
                'path': str(game_dir),
                'error': str(exc),
            })
            logger.error("Skipping game with unreadable metadata: %s", exc)
            return None

        # After the metadata, so a folder with several .vpx launches the one its
        # metadata describes rather than whichever the filesystem listed first.
        recorded = recorded_default(vpinfe_section(game.meta_config),
                                    table_entries(game.meta_config))
        chosen = default_table(game_contents, game_dir.name, recorded)
        game.fullPathVPXfile = str(game_dir / chosen)

        # Media after the default pick: tier 1 of the resolution chain keys off
        # the table that actually launches.
        self.loadImagePaths(
            game,
            game_contents=game_contents,
            has_medias_dir="medias" in game_subdirs,
            table_stem=Path(chosen).stem if chosen else None,
        )
        try:
            stat = os.stat(game.fullPathVPXfile)
            game.creation_time = getattr(stat, 'st_birthtime', stat.st_ctime)
        except OSError:
            logger.warning("Could not stat table: %s", game.fullPathVPXfile)

        return game


    def reload_game(self, game_dir):
        """Re-read one game folder in place. Returns the game, or None if it is gone.

        A rating, a rename or an import changes one folder, and rescanning the library
        to see it costs the whole library - on a network share, minutes of it.
        """
        game_dir = Path(game_dir)
        target = str(game_dir)
        self.missing_games = [row for row in self.missing_games if row["path"] != target]
        self.unreadable_games = [r for r in self.unreadable_games if r["path"] != target]

        game = self._build_game(game_dir) if game_dir.is_dir() else None
        for index, existing in enumerate(self.games):
            if existing.fullPathGame == target:
                if game is None:
                    del self.games[index]        # the folder went away
                else:
                    self.games[index] = game
                return game

        if game is not None:
            self.games.append(game)             # a folder that was not there before
        return game

    def loadImagePaths(self, Game, game_contents=None, has_medias_dir=None,
                       table_stem=None):
        game_dir = Path(Game.fullPathGame)
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
        apply_media_specs(Game, game_contents, medias_contents, self.playfieldvariant,
                          table_stem, self.active_sets or None)
        # And again per table, off the same two listings. The walk is what costs; a
        # second resolution is set lookups, so a folder with one table pays almost
        # nothing and one with three answers honestly for all three.
        Game.media_by_table = resolve_media_by_table(
            Game.fullPathGame, game_contents, medias_contents,
            table_names(game_contents), self.playfieldvariant,
            self.active_sets or None)

    def loadMetaData(self, Game):
        meta_path = Path(Game.fullPathGame) / f"{Game.gameDirName}.info"
        try:
            meta = MetaConfig(str(meta_path))
        except InvalidMetaConfigError as exc:
            logger.error("Invalid metadata for game '%s': %s", Game.gameDirName, exc)
            raise
        Game.meta_config = meta.data
        Game.info_pending_upgrade = meta.pending_migration

    def getGame(self, index):
        return self.games[index]

    def getGameCount(self):
        return len(self.games)

    def getAllGames(self):
        return list(self.games)

    def getUnreadableGames(self):
        """Folders whose .info could not be read, so the game was left out."""
        return [dict(row) for row in self.unreadable_games]

    def getMissingGames(self):
        return [dict(row) for row in self.missing_games]

    def isFavorite(self, Game):
        return vpinfe_section(Game.meta_config).get("favorite", "").lower() == "true"
