"""The library, as an extension is allowed to see it.

A curated view over the same services the API's own routes call, so the two cannot
answer differently. An extension in this process cannot use the HTTP API - a synchronous
call into the server it is running inside deadlocks, which the Console already pays for
elsewhere - and it may not import the library either. This is the door.

What it will do is bounded twice. The manifest's scopes decide which of these an
extension may call at all, which is what makes declaring them mean something. And a path
it hands over has to be inside a folder it said it works from, so an extension cannot use
core as a way to read somewhere it never declared.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .contract import ContractError

logger = logging.getLogger("vpinfe.common.extensions.games")

GAMES_READ = "games:read"
GAMES_WRITE = "games:write"

# What core has said an extension may do to the library, by the name an extension calls
# it: `name -> (scope, callable)`.
#
# Core fills this in, because these are core's own functions and the host is not the
# place that knows them. Filled in rather than imported so this module stays underneath
# the API rather than reaching up into it, and rather than reimplemented so the two
# cannot answer differently - they already did, and it showed up as an importer that
# guessed at core's folder-naming rule and got it wrong.
_OFFERED: dict[str, tuple[str, object]] = {}


def offer(name: str, scope: str, run) -> None:
    """Core: let extensions call this, for anything declaring `scope`."""
    _OFFERED[name] = (scope, run)


def offered() -> tuple[str, ...]:
    return tuple(sorted(_OFFERED))


def withdraw_all() -> None:
    """For tests, which build an app per case and must not inherit the last one's."""
    _OFFERED.clear()


class ExtensionGames:
    def __init__(self, name: str, scopes, files) -> None:
        self._name = name
        self._scopes = frozenset(scopes)
        self._files = files

    def __getattr__(self, name: str):
        """Anything core offered that this does not wrap itself.

        The named methods below stay because they are worth having a shape for - they
        take a path and check it, or they answer with something an importer wants. The
        rest an extension calls the way the API names them, gated the same way.
        """
        if name.startswith("_") or name not in _OFFERED:
            raise AttributeError(
                f"core offers nothing called {name!r} to an extension"
                + (f"; it offers {', '.join(offered())}" if _OFFERED else ""))
        scope, run = _OFFERED[name]
        self._needs(scope)

        def call(*args, **kwargs):
            return run(*args, **kwargs)

        call.__name__ = name
        return call

    def reaches(self) -> tuple[str, ...]:
        """What this extension may actually call, which is what core offers narrowed to
        what its manifest declared."""
        return tuple(name for name, (scope, _run) in sorted(_OFFERED.items())
                     if scope in self._scopes)

    # -- the two bounds -------------------------------------------------------

    def _needs(self, scope: str) -> None:
        if scope not in self._scopes:
            raise ContractError(
                f"{self._name} asks core to do something needing {scope}, which its "
                "manifest does not declare")

    def _source(self, path) -> Path:
        """A file the extension is handing over, checked against what it declared.

        Tighter than the same check on the HTTP routes, and it can be: this one knows
        which extension is asking, where a route only knows a path.
        """
        wanted = Path(str(path or "")).expanduser().resolve()
        self._inside_declared(wanted)
        if not wanted.is_file():
            raise FileNotFoundError(f"there is no file at {wanted}")
        return wanted

    def _inside_declared(self, wanted: Path) -> None:
        """The bound itself, for something that may be a file or a folder.

        An asset arrives as a directory as often as a file - a ROM set is one, a sound
        bank is one - so the check cannot insist on a file.

        Both sides are resolved before comparing. A root is not always handed over
        already resolved, and on a machine where `/var` is a link to `/private/var` an
        unresolved root never contains a resolved path - which reads as an extension
        reaching somewhere it did not declare, for a folder it did.
        """
        roots = [Path(one).expanduser().resolve() for one in self._files.roots()]
        if not any(wanted == root or root in wanted.parents for root in roots):
            raise ContractError(
                f"{self._name} offered {wanted}, which is not inside any folder it says "
                "it works from")

    def _game(self, game_id: str):
        from common.games import game_identity
        from common.games.game_repository import all_games

        found = game_identity.ensure_unique_ids(all_games()).get(str(game_id or ""))
        if found is None:
            raise LookupError(f"No game with id {game_id}")
        return found

    # -- reading --------------------------------------------------------------

    def kinds(self) -> tuple[str, ...]:
        """Every media kind this build stores. The vocabulary an importer maps onto, and
        the reason it does not have to hard-code a list that would go stale."""
        self._needs(GAMES_READ)
        from common.media_specs import MEDIA_SPECS

        return tuple(spec.kind for spec in MEDIA_SPECS)

    def existing(self) -> list[dict]:
        """Every game already here, in the little an importer needs to recognise one.

        Not the whole library: what a second run is asking is "have I made this one
        before", and folder name, catalog id and title answer it. Anything more would be
        handing over the library to answer a question about names.
        """
        self._needs(GAMES_READ)
        from common.games import game_identity
        from common.games.game_metadata import game_title, normalize_meta, section
        from common.games.game_repository import all_games

        found = []
        for game in all_games():
            meta = normalize_meta(getattr(game, "meta_config", {}))
            info = section(meta, "Info")
            found.append({
                "game_id": game_identity.game_id(game),
                "folder_name": Path(str(game.fullPathGame)).name,
                "name": game_title(game),
                "vps_id": str(info.get("VPSId", "") or ""),
                "ipdb_id": str(info.get("IPDBId", "") or ""),
            })
        return found

    def folder_name_for(self, name: str) -> str:
        """The folder a game of this name would get.

        Asked rather than guessed. An importer needs this before it creates anything -
        to see what it already has, and to notice that two of its own games want the
        same folder - and a second copy of the rule drifts from this one silently. It
        did: `Star Trek: The Next Generation` and `Star Trek The Next Generation` are one
        folder here and were two to the importer, so the second failed on a name that was
        already taken.
        """
        self._needs(GAMES_READ)
        from common.games.game_service import sanitize_dir_name

        return sanitize_dir_name(name)

    def folder(self, game_id: str) -> str:
        self._needs(GAMES_READ)
        return str(self._game(game_id).fullPathGame)

    # -- writing --------------------------------------------------------------

    def create(self, name: str, location: str = "") -> str:
        """Make an entry and answer with its id."""
        self._needs(GAMES_WRITE)
        from common.games import game_identity, game_service

        folder = game_service.create_game(name, location)
        from common.games.game_repository import all_games

        made = next((game for game in all_games()
                     if Path(str(game.fullPathGame)).resolve() == folder.resolve()), None)
        if made is None:
            raise LookupError(f"Created {folder} but this install does not read it")
        return game_identity.ensure_id(made)

    def add_table(self, game_id: str, path) -> dict:
        """Copy a game file into an entry, with whatever belongs to it.

        Answers with the table's id, the companions that came, and the ROM the table
        turns out to need - a caller counting what an import produced needs to know what
        actually landed, and anything keyed on the ROM has no other way to learn it this
        early.
        """
        self._needs(GAMES_WRITE)
        from common.games import game_service
        from common.games.ids import new_id

        source = self._source(path)
        table_id = new_id()
        found = game_service.add_table_file(Path(self.folder(game_id)), source, table_id)
        return {"table_id": table_id, "companions": tuple(found["companions"]),
                "rom": found.get("rom", "")}

    def companions_of(self, path) -> tuple[str, ...]:
        """What would come with this table if it were added. For counting beforehand,
        so a plan and the run that follows it agree."""
        self._needs(GAMES_READ)
        from common.games import game_service

        return tuple(one.name for one in
                     game_service.companions_beside(self._source(path)))

    def asset_kinds(self) -> tuple[str, ...]:
        """The kinds that live in a folder of their own, and so can be placed whole."""
        self._needs(GAMES_READ)
        from common.uploads.asset_import_service import folder_kinds

        return folder_kinds()

    def put_asset(self, game_id: str, kind: str, path, rom: str = "") -> str:
        """Put a file or a whole folder where this kind of asset belongs.

        For the things that are neither the game file nor artwork: a ROM set, an
        alternative sound bank, a colour set. Where each goes is the registry's answer,
        the same one an upload gets, so a library imported from another frontend puts
        them where an upload would have.

        Answers with the path it took, relative to the game. Never replaces: a second
        run, or something somebody put there on purpose, is not ours to overwrite - the
        same rule the import applies to games and to a table's companions.
        """
        self._needs(GAMES_WRITE)
        import shutil

        from common.uploads.asset_import_service import folder_for

        source = Path(str(path or "")).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"there is nothing at {source}")
        self._inside_declared(source)

        game_dir = Path(self.folder(game_id))
        into = folder_for(kind, game_dir, rom)
        if into is None:
            raise ValueError(
                f"{kind!r} is not a kind with a folder of its own"
                + ("; it needs a ROM name" if kind in self.asset_kinds() else ""))

        landing = into / source.name
        if landing.exists():
            raise FileExistsError(str(landing.relative_to(game_dir)))
        into.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, landing)
        else:
            shutil.copy2(source, landing)
        logger.info("%s put %s into %s", self._name, source.name, into)
        # Forward slashes, because this is answered to a caller rather than used as a
        # path here - the same rule every other path this project hands out follows.
        return landing.relative_to(game_dir).as_posix()

    def put_media(self, game_id: str, kind: str, path, table_stem: str = "") -> str:
        """Put a file in one of an entry's media slots. Answers with what it landed as."""
        self._needs(GAMES_WRITE)
        from common.games import media_placement

        if kind not in self.kinds():
            raise ValueError(f"No media kind called {kind!r}")
        source = self._source(path)
        game_dir = Path(self.folder(game_id))
        written = media_placement.place(game_dir, kind, table_stem or game_dir.name,
                                        source)
        # Recorded as the user's, because it is: somebody's own library came across, and
        # a later media refresh must leave it alone rather than treat it as ours to
        # replace.
        media_placement.record_origin(game_dir, written, "user", "")
        return written.name
