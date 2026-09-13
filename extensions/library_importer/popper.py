"""Reading a PinUP Popper library.

A SQLite database rather than a parse, which makes it the third shape: PinballX derives
media from a folder convention, EmulationStation stores a path per game, and this one
answers a query.

**Three name columns, and they are not interchangeable** - verified against a real
install rather than inferred, because the inference was wrong. `GameName` is the identity
and the name media is found by; `GameFileName` is the file, with whatever mod or version
suffix it carries; `GameDisplay` is the bare title. `GameName` is already
"Title (Manufacturer Year)", which is our own folder convention arrived at separately. A
reader using one of the three for all of them finds either no artwork or no table.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from . import drivemap
from .source import SourceGame, SourceLibrary, SourceMedia, SourceSystem

logger = logging.getLogger(__name__)

SOURCE_ID = "popper"
SOURCE_NAME = "PinUP Popper"

DATABASE = "PUPDatabase.db"
MEDIA_DIR = "POPMedia"

# One folder per kind under the emulator's media directory. Taken from a real install;
# `pthumbs` and `vsthumbs` sit beside them holding generated thumbnails and are not one.
MEDIA_FOLDERS = (
    "PlayField", "BackGlass", "DMD", "Wheel", "Topper", "Loading", "Menu",
    "GameInfo", "GameHelp", "GameSelect", "Audio", "AudioLaunch", "Other1", "Other2",
)
NOT_MEDIA = ("pthumbs", "vsthumbs")

CARRIED = ("TAGS", "Category", "Notes", "DateAdded", "GAMEVER", "ALTEXE", "DOFStuff",
           "WebLinkURL", "WEBGameID", "ROMALT", "DesignedBy")


def database_path(root: Path | str) -> Path:
    return Path(root) / DATABASE


def detect(root: Path | str) -> bool:
    return database_path(root).is_file()


def _open(path: Path) -> sqlite3.Connection:
    """Read-only, so a live frontend running against this database is not blocked by an
    importer that only ever converts from it."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _text(row, column: str) -> str:
    try:
        value = row[column]
    except (IndexError, KeyError):
        return ""
    return str(value).strip() if value is not None else ""


def _hidden(value) -> bool:
    return str(value) in ("0", "False", "None")


def _media_key(row) -> str:
    """What this game's artwork is named after.

    Usually its name, and sometimes whatever the game says instead: a `MediaSearch`
    holding a `*` replaces the key with what is left once the star is removed. Rare -
    every row in the install this was checked against left it empty - and a reader
    assuming the name finds nothing at all for the ones that use it.
    """
    override = _text(row, "MediaSearch")
    if "*" in override:
        return override.replace("*", "").strip()
    return _text(row, "GameName")


def _game_from(row, tables_dir: str) -> SourceGame | None:
    name = _text(row, "GameName")
    if not name:
        return None

    file_name = _text(row, "GameFileName")
    table_file = ""
    if tables_dir and file_name:
        candidate = Path(tables_dir) / file_name
        table_file = str(candidate) if candidate.is_file() else ""

    return SourceGame(
        key=_media_key(row),
        display_name=name,
        title=_text(row, "GameDisplay"),
        manufacturer=_text(row, "Manufact"),
        year=_text(row, "GameYear"),
        game_type=_text(row, "GameType"),
        themes=tuple(part.strip() for part in _text(row, "GameTheme").split(",")
                     if part.strip()),
        ipdb_id=_text(row, "IPDBNum"),
        rom=_text(row, "ROM"),
        rating=_text(row, "GameRating"),
        players=_text(row, "NumPlayers"),
        author=_text(row, "Author"),
        # Popper hides a game rather than deleting it, the same as the other two.
        hidden=_hidden(row["Visible"]),
        table_file=table_file,
        extras={key: _text(row, key) for key in CARRIED if _text(row, key)},
    )


def read_media(media_root: Path | str, games: list[SourceGame]) -> list[SourceGame]:
    """Attach each game's artwork.

    The longest key that prefixes a filename wins, decided across the whole database -
    the same rule the other sources need, because Popper keys on a name too and two
    games' names can be prefixes of one another.
    """
    media_root = Path(media_root)
    folded = {game.key.lower(): game.key for game in games if game.key}
    found: dict[str, list[SourceMedia]] = {game.key: [] for game in games}

    for folder in MEDIA_FOLDERS:
        try:
            entries = [item for item in (media_root / folder).iterdir()
                       if item.is_file() and item.name not in NOT_MEDIA]
        except OSError:
            continue
        for item in entries:
            stem = item.stem.lower()
            owner = max((key for key in folded if stem.startswith(key)),
                        key=len, default=None)
            if owner is not None:
                found[folded[owner]].append(
                    SourceMedia(source_kind=folder, path=str(item)))

    return [SourceGame(**{**vars(game), "media": tuple(found.get(game.key, ()))})
            for game in games]


def _playable(said: str, plays) -> bool:
    """Whether anything installed here plays what this emulator holds.

    An emulator that records no extension is kept: saying nothing is not saying no, and
    refusing it would drop a library over a blank column.
    """
    suffix = str(said or "").strip().lower()
    if not suffix:
        return True
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return bool(plays(suffix)) if plays else suffix == ".vpx"


def read(root: Path | str, plays=None) -> SourceLibrary:
    """Every emulator the database declares, and the games under each.

    The media root is derived from where the database actually is rather than read off
    the row: what an install records is the path on the machine it ran on, and a library
    reached over a share is never at that path.

    `plays` is accepted so every reader is called the same way. This one does not
    filter on it yet: it reads one system, and what to do when that system is not
    playable here is a question about what the source declares, which is unfinished.
    """
    root = Path(root)
    path = database_path(root)
    if not path.is_file():
        return SourceLibrary(source_id=SOURCE_ID, root=str(root),
                             notes=(f"No {DATABASE} in {root.name}",))

    notes: list[str] = []
    mapped: set[str] = set()
    systems: list[SourceSystem] = []
    try:
        db = _open(path)
    except sqlite3.Error as exc:
        return SourceLibrary(source_id=SOURCE_ID, root=str(root),
                             notes=(f"{DATABASE} could not be opened: {exc}",))

    try:
        emulators = list(db.execute(
            "select EMUID, EmuName, DirGames, DirRoms, Visible, GamesExt "
            "from Emulators order by EMUID"))
        skipped_systems = []
        for emu in emulators:
            name = _text(emu, "EmuName")
            if not name:
                continue
            # Popper records the extension per emulator, always - which is a better
            # signal than either of the others gives, and the reason this filter is one
            # line here and three branches there.
            if not _playable(_text(emu, "GamesExt"), plays):
                skipped_systems.append(name)
                continue
            recorded = _text(emu, "DirGames")
            found = drivemap.resolve(recorded, root) if recorded else drivemap.Found()
            tables_dir = found.path
            if recorded and not tables_dir:
                notes.append(f"{name}: the tables are recorded at {recorded}, which is "
                             "not reachable from here")
            elif found.recorded_prefix and found.recorded_prefix not in mapped:
                # Said once per prefix rather than once per emulator: it is one fact
                # about where the share is, and repeating it per row buries the rest.
                mapped.add(found.recorded_prefix)
                notes.append(f"Reading {found.recorded_prefix} as {found.local_prefix} "
                             "- the paths recorded here are the old machine's")

            rows = list(db.execute(
                "select * from Games where EMUID = ? order by GameName",
                (emu["EMUID"],)))
            games = [one for one in (_game_from(row, tables_dir) for row in rows)
                     if one is not None]
            skipped = len(rows) - len(games)
            if skipped:
                notes.append(f"{name}: {skipped} "
                             f"{'row has' if skipped == 1 else 'rows have'} no name, so "
                             "nothing can be matched to "
                             f"{'it' if skipped == 1 else 'them'}")
            games = read_media(root / MEDIA_DIR / name, games)
            systems.append(SourceSystem(
                name=name, games=tuple(games), tables_dir=tables_dir,
                working_path=drivemap.resolve(_text(emu, "DirRoms"), root).path
                or _text(emu, "DirRoms"),
                enabled=not _hidden(emu["Visible"])))
        if skipped_systems:
            # Named rather than dropped in silence, the same as the other reader:
            # somebody who set Future Pinball up wants to know it was seen and left.
            notes.append("Not brought in, because this build does not play them: "
                         + ", ".join(sorted(skipped_systems)))
    except sqlite3.Error as exc:
        notes.append(f"{DATABASE} could not be read past this point: {exc}")
    finally:
        db.close()

    return SourceLibrary(source_id=SOURCE_ID, root=str(root),
                         systems=tuple(systems), notes=tuple(notes))
