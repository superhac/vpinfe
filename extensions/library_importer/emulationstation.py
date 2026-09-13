"""Reading an EmulationStation library.

Structurally the opposite of PinballX, and that is why it is here: **the media path is
stored per game rather than derived by convention.** There is no kind-folder table, no
key-to-filename rule and no extension deciding which folder a file belongs in - a game
says where its own artwork is. A model shaped only around the first source read would
have had nowhere to put that, so this is the check that it was not.

`gamelist.xml` at the folder somebody points at, with `<gameList>` holding `<game>`
elements. Paths inside are relative to that folder, or absolute, or start with `~`.

**Only `path`, `name`, `desc` and `image` are verified.** The rest below are from
EmulationStation's published documentation and have not been read off a real gamelist, so
anything depending on them should be checked against one first.
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from .source import SourceGame, SourceLibrary, SourceMedia, SourceSystem

logger = logging.getLogger(__name__)

SOURCE_ID = "emulationstation"
SOURCE_NAME = "EmulationStation"

GAMELIST = "gamelist.xml"

# Elements naming a file. The element's own name is the source kind, so what it is called
# here is what a preview shows and what the mapping is written against.
MEDIA_ELEMENTS = ("image", "video", "marquee", "thumbnail", "fanart")

# Documented rather than verified - see the module docstring.
_FIELDS = {
    "name": "title",
    "desc": "blurb",
    "developer": "manufacturer",
    "publisher": "manufacturer",
    "genre": "game_type",
    "rating": "rating",
    "players": "players",
}

_EXTRAS = ("releasedate", "playcount", "lastplayed", "region", "lang")


def gamelist_path(root: Path | str) -> Path:
    return Path(root) / GAMELIST


def detect(root: Path | str) -> bool:
    return gamelist_path(root).is_file()


def _resolve(root: Path, raw: str) -> str:
    """A path a game gave, as somewhere on this machine.

    Three forms and all of them are ordinary: relative to the folder holding the
    gamelist, absolute, and `~`. Resolved without requiring the file to be there - a
    library copied without its media still describes where the media was.
    """
    wanted = str(raw or "").strip()
    if not wanted:
        return ""
    if wanted.startswith("~"):
        return str(Path(wanted).expanduser())
    if os.path.isabs(wanted):
        return wanted
    return str((root / wanted).resolve())


def _year_of(text: str) -> str:
    """ES writes a release date as an ISO-ish stamp; we hold a year."""
    digits = "".join(ch for ch in str(text or "") if ch.isdigit())
    return digits[:4] if len(digits) >= 4 else ""


def _game_from(element, root: Path) -> SourceGame | None:
    """One `<game>`. Returns None without a path: it is the only thing identifying the
    entry, since ES has no name attribute and nothing is derived from one."""
    values: dict[str, str] = {}
    extras: dict[str, str] = {}
    media: list[SourceMedia] = []
    path = ""
    for child in element:
        tag = str(child.tag or "").lower()
        text = (child.text or "").strip()
        if tag == "path":
            path = _resolve(root, text)
        elif tag in MEDIA_ELEMENTS and text:
            media.append(SourceMedia(source_kind=tag, path=_resolve(root, text)))
        elif tag in _FIELDS:
            # publisher only where developer said nothing, since both map to the one
            # field we hold and the first is the closer answer.
            if _FIELDS[tag] not in values and text:
                values[_FIELDS[tag]] = text
        elif tag == "releasedate" and text:
            values["year"] = _year_of(text)
            extras[tag] = text
        elif tag in _EXTRAS and text:
            extras[tag] = text

    if not path:
        return None
    # The filename stem is the key, because that is the only stable name an ES entry has
    # and it is what a person recognizes it by.
    return SourceGame(key=Path(path).stem, table_file=path, media=tuple(media),
                      extras=extras, **values)


def read(root: Path | str, plays=None) -> SourceLibrary:
    """Everything one gamelist describes.

    One system per root, because a root is the folder somebody pointed at and ES keeps
    one gamelist per system. A source with several is imported one at a time, which is
    also how somebody thinks about it.

    `plays` is accepted so every reader is called the same way. This one does not
    filter on it yet: it reads one system, and what to do when that system is not
    playable here is a question about what the source declares, which is unfinished.
    """
    root = Path(root)
    path = gamelist_path(root)
    if not path.is_file():
        return SourceLibrary(source_id=SOURCE_ID, root=str(root),
                             notes=(f"No {GAMELIST} in {root.name}",))

    try:
        tree = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        return SourceLibrary(source_id=SOURCE_ID, root=str(root),
                             notes=(f"{GAMELIST} could not be read: {exc}",))

    games, skipped = [], 0
    for element in tree.iter("game"):
        game = _game_from(element, root)
        if game is None:
            skipped += 1
            continue
        games.append(game)

    notes = []
    if skipped:
        notes.append(f"{GAMELIST}: {skipped} "
                     f"{'entry names' if skipped == 1 else 'entries name'} no file and "
                     "cannot be imported")
    missing = sum(1 for game in games if game.table_file
                  and not Path(game.table_file).is_file())
    if missing:
        notes.append(f"{missing} of {len(games)} games name a file that is not reachable "
                     "from here")

    return SourceLibrary(
        source_id=SOURCE_ID, root=str(root), notes=tuple(notes),
        systems=(SourceSystem(name=root.name, games=tuple(games),
                              tables_dir=str(root)),))
