"""Reading a PinballX or PinballY library.

One reader covers both: PinballY's table parser extends PinballX's, adding `title` and
`ipdbid` over the same element set, so the database is shared and the extra children are
simply absent from a PinballX file.

Three things are read, and the source declares all three itself:

- `Config/PinballX.ini`, **UTF-16** - the emulators, and where each keeps its tables.
- `Databases/<name>/<name>.xml` - the games, one `<game>` element each.
- `Media/<name>/<folder>/` - the artwork, found by the game's name attribute.

The last two are derived from the emulator's name by convention rather than configured,
which is why a source with a database needs to be asked almost nothing.
"""

from __future__ import annotations

import configparser
import logging
import os
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path, PureWindowsPath

from . import drivemap
from .source import SourceGame, SourceLibrary, SourceMedia, SourceSystem

logger = logging.getLogger(__name__)

SOURCE_ID = "pinballx"
SOURCE_NAME = "PinballX or PinballY"

CONFIG_RELATIVE = ("Config", "PinballX.ini")
DATABASES_DIR = "Databases"
MEDIA_DIR = "Media"

# A media folder is one kind. PinballX files a still and a moving version of the same
# subject in two folders and chooses between them by the file's extension - which is a
# decision for something writing, not for something reading: each folder here is
# unambiguous on its own, and both have to be walked or half the artwork is missed.
MEDIA_FOLDERS = (
    "Table Images", "Table Videos",
    "Backglass Images", "Backglass Videos",
    "DMD Images", "DMD Videos",
    "Topper Images", "Topper Videos",
    "FullDMD Videos",
    "Wheel Images", "Logos",
    "Table Audio", "Launch Audio",
)

# The `<game>` children, verbatim from the parser both frontends share. Read as text and
# mapped where we have somewhere to put it; the rest travels in `extras` so a preview can
# say what will not be carried.
_FIELDS = {
    "description": "display_name",
    "rom": "rom",
    "year": "year",
    "manufacturer": "manufacturer",
    "type": "game_type",
    "version": "version",
    "author": "author",
    "rating": "rating",
    "players": "players",
    "comment": "comment",
    # PinballY only. PinballX has no title of its own - its description carries the name
    # with the manufacturer and year in it.
    "title": "title",
}

# Case-folded, because a hand-edited database spells these however it likes and the
# parser we read matches them without regard to case.
_IDS = {"ipdbnr": "ipdb_id", "ipdbid": "ipdb_id", "vpsid": "vps_id"}

_EXTRAS = ("hidedmd", "hidetopper", "hidebackglass", "alternateexe",
           "dateadded", "datemodified", "theme")


def detect(root: Path | str) -> bool:
    """Whether this reader has anything to say about a root.

    The databases rather than the ini: a library copied off an old machine very often
    arrives without its config, and the games are the part worth having.
    """
    root = Path(root)
    return (root / DATABASES_DIR).is_dir() or _config_path(root).is_file()


def _config_path(root: Path) -> Path:
    return root.joinpath(*CONFIG_RELATIVE)


def read_config(root: Path | str) -> tuple[list[dict], list[str]]:
    """The emulators the source declares, and anything worth saying about the read.

    UTF-16, which is not a guess: the file is written that way and a plain UTF-8 read of
    it fails outright. Read as text first so a source that is in fact UTF-8 - hand-made,
    or already converted - still works rather than being refused on principle.
    """
    root = Path(root)
    path = _config_path(root)
    if not path.is_file():
        # PinballY keeps the same facts in a different file in a different shape. Tried
        # second because a folder holding both is a PinballX install somebody pointed
        # PinballY at, and the ini is the one that frontend actually reads.
        settings = root / PINBALLY_SETTINGS
        if settings.is_file():
            return read_pinbally_config(settings)
        return [], [f"No {os.path.join(*CONFIG_RELATIVE)} and no {PINBALLY_SETTINGS}, "
                    "so the emulators were not read"]

    text, notes = "", []
    for encoding in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except (UnicodeError, OSError) as exc:
            notes = [f"Could not read {path.name}: {exc}"]
    if not text:
        return [], notes

    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        return [], [f"{path.name} could not be parsed: {exc}"]

    found = []
    for section in parser.sections():
        if not section.lower().startswith("system_"):
            continue
        values = {key.lower(): value for key, value in parser[section].items()}
        name = str(values.get("name", "")).strip()
        if not name:
            continue
        found.append({
            "name": name,
            "tables_dir": str(values.get("tablepath", "")).strip(),
            "working_path": str(values.get("workingpath", "")).strip(),
            "enabled": str(values.get("enabled", "true")).strip().lower()
                       not in ("false", "0", "no"),
            "executable": str(values.get("executable", "")).strip(),
        })
    return found, []


# What this build can actually play. A source declares whatever its owner ever set up -
# Future Pinball, the Steam FX titles, Visual Pinball 9 - and bringing those in would
# make entries for games nothing here can launch. Decided on the table extension because
# it is the one signal both frontends carry: PinballY writes `DefExt` and `Class`,
# PinballX writes neither, but the name and the executable both say it.
# What this build plays when nobody says otherwise, so the reader works standalone.
PLAYABLE_EXTENSION = ".vpx"
_VPX_HINTS = ("vpx", "visual pinball x")


def _plays_vpx(suffix: str) -> bool:
    return str(suffix or "").strip().lower() == PLAYABLE_EXTENSION


def _is_playable(entry: dict, plays=_plays_vpx, known: tuple[str, ...] = ()) -> bool:
    """Whether anything installed here could play what the system holds.

    Asked rather than assumed, because the answer changes: an extension that provides an
    app for another format makes a library of that format worth importing, and a rule
    naming `.vpx` would go on skipping it.

    The source says what it holds in three ways and none is present everywhere. PinballY
    writes `DefExt` and `Class`. PinballX writes neither. And a database the config never
    declared has nothing at all but the folder it was found in - which is why the name is
    matched against the apps this build has, rather than against a list of formats
    written down here.
    """
    said_ext = str(entry.get("default_ext", "")).strip().lower()
    if said_ext:
        return bool(plays(said_ext))
    if str(entry.get("class", "")).strip().lower() == "vpx":
        return bool(plays(PLAYABLE_EXTENSION))

    said = f"{entry.get('name', '')} {Path(entry.get('executable', '')).name}".lower()
    for app_name in known:
        folded = str(app_name or "").strip().lower()
        if folded and folded in said:
            return True
    # `visual pinball 9` must not match, which is why the hint is the X, not the family.
    return (any(hint in said for hint in _VPX_HINTS)
            and bool(plays(PLAYABLE_EXTENSION)))


PINBALLY_SETTINGS = "Settings.txt"
# `System3 = Visual Pinball X` names it; `System3.Exe = ...` configures it. The bare key
# is the display name and is also what the media and database folders are called when
# they are not overridden.
_PINBALLY_LINE = re.compile(r"^\s*System(\d+)(?:\.([A-Za-z]+))?\s*=\s*(.*?)\s*$")


def read_pinbally_config(path: Path) -> tuple[list[dict], list[str]]:
    """The emulators a PinballY install declares.

    Flat `key = value` rather than ini sections, so configparser is no help: the name of
    a system is the bare `SystemN` key and everything else hangs off `SystemN.Something`.

    `TablePath` is usually relative and resolves against the folder the emulator runs
    from, not against PinballY - `Tables` beside `P:\\Visual Pinball\\VPinballX.exe` means
    `P:\\Visual Pinball\\Tables`. Left relative it would resolve against the frontend and
    point at nothing.
    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return [], [f"Could not read {path.name}: {exc}"]

    systems: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        found = _PINBALLY_LINE.match(line)
        if found:
            number, key, value = found.groups()
            systems.setdefault(number, {})[(key or "name").lower()] = value

    found = []
    for number in sorted(systems, key=int):
        values = systems[number]
        name = values.get("name", "").strip()
        if not name:
            continue
        working = str(PureWindowsPath(values.get("exe", "")).parent) \
            if values.get("exe") else ""
        tables = values.get("tablepath", "").strip()
        if tables and working and not PureWindowsPath(tables).is_absolute():
            tables = str(PureWindowsPath(working) / tables)
        found.append({
            "name": name,
            "tables_dir": tables,
            "working_path": working,
            # The folder its media and database sit in, which is the system's own name
            # unless it says otherwise.
            "media_dir": values.get("mediadir", "").strip() or name,
            "database_dir": values.get("databasedir", "").strip() or name,
            "enabled": values.get("enabled", "1").strip() not in ("0", "false", "no"),
            "default_ext": values.get("defext", "").strip(),
            "class": values.get("class", "").strip(),
            "executable": values.get("exe", "").strip(),
        })
    return found, []


def _text(element, tag: str) -> str:
    found = element.find(tag)
    return (found.text or "").strip() if found is not None else ""


def _game_from(element, tables: tuple[dict[str, str], dict[str, str]]) -> SourceGame | None:
    """One `<game>` element. Returns None for one with no name, which is the only
    thing that makes it addressable - its media is found by it."""
    key = str(element.get("name", "") or "").strip()
    if not key:
        return None

    values: dict[str, str] = {}
    extras: dict[str, str] = {}
    themes: tuple[str, ...] = ()
    hidden = False
    for child in element:
        tag = str(child.tag or "").lower()
        text = (child.text or "").strip()
        if tag in _FIELDS:
            values[_FIELDS[tag]] = text
        elif tag in _IDS:
            if text:
                values[_IDS[tag]] = text
        elif tag == "enabled":
            hidden = text.lower() in ("false", "0", "no")
        elif tag in _EXTRAS and text:
            if tag == "theme":
                themes = tuple(part.strip() for part in text.split(",") if part.strip())
            else:
                extras[tag] = text

    file_path = ""
    if tables[0] or tables[1]:
        # The name attribute is the table's filename without its extension. Which
        # extension is not recorded, so the listing is asked rather than assumed.
        file_path = _table_file(tables, key)

    return SourceGame(key=key, themes=themes, hidden=hidden, table_file=file_path,
                      extras=extras, **values)


def _table_index(tables_dir: Path, plays=_plays_vpx) -> tuple[dict[str, str], dict[str, str]]:
    """The playable files in the tables folder, by stem: exact, and case-folded.

    **Playable, not everything.** A table sits beside its companions and they share its
    stem - `Taxi.vpx`, `Taxi.directb2s`, `Taxi.vbs` - so an index of every file has
    several answers for one name and returns whichever the directory listed first. A
    real import recorded a game's script as its table that way, and the game then had no
    table at all.

    Listed once for the whole database rather than once per game. A real library put 654
    games against a folder of some three thousand entries, and asking the folder each
    time meant two million stat calls across a mounted drive - thirty seconds, for a
    listing that does not change while it is being read.

    `scandir` rather than `iterdir` because it carries the file-or-directory answer back
    with the name, where `is_file()` is another call across the same mount.
    """
    exact: dict[str, str] = {}
    folded: dict[str, str] = {}
    try:
        with os.scandir(tables_dir) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                stem, suffix = os.path.splitext(entry.name)
                if not plays(suffix):
                    continue
                exact.setdefault(stem, entry.path)
                folded.setdefault(stem.lower(), entry.path)
    except OSError:
        pass
    return exact, folded


def _table_file(index: tuple[dict[str, str], dict[str, str]], key: str) -> str:
    """The game file this entry names, or "" when the folder does not have it.

    Exact stem first, then case-insensitively: a database written on Windows and read
    from a case-sensitive share is the ordinary way this goes wrong.
    """
    exact, folded = index
    return exact.get(key) or folded.get(key.lower(), "")


# What the frontend leaves behind when it replaces a media file. A real library held
# 1288 files in a folder serving 654 games, and 675 of them were these - importing them
# would double every game's artwork with its own superseded copies.
BACKUP_SUFFIX = re.compile(r"\.old\[\d+\]$", re.IGNORECASE)


def _database_text(path: Path) -> tuple[str | None, list[str]]:
    """The database as text, whatever it was written in.

    These files carry no encoding declaration and are not reliably one encoding. A real
    library read here was ASCII throughout except for eleven Windows-1252 bytes inside
    table names - a middle dot in `1(dot)2(dot)3... (Talleres 1973)` - which is enough to
    make a strict parse fail on the file and lose all 705 games.

    That is the shape worth guarding: an all-or-nothing loss caused by one cosmetic
    character in one name. So the encoding is tried rather than assumed, and the last
    step replaces what it cannot decode instead of refusing - a game whose name has one
    wrong character is a far better answer than no library.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, [f"{path.name} could not be read: {exc}"]

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding), []
        except UnicodeDecodeError:
            continue
    try:
        return raw.decode("cp1252"), [
            f"{path.name} is not UTF-8, so it was read as Windows-1252"]
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace"), [
            f"{path.name} holds bytes in no encoding this reads, so some characters "
            "came across wrong"]


def read_database(path: Path | str, tables_dir: str = "",
                  plays=_plays_vpx) -> tuple[list[SourceGame], list[str]]:
    """Every game in one database file."""
    path = Path(path)
    text, notes = _database_text(path)
    if text is None:
        return [], notes
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        return [], [*notes, f"{path.name} could not be read: {exc}"]

    tables = _table_index(Path(tables_dir), plays) if tables_dir else ({}, {})
    found, skipped = [], 0
    for element in root.iter("game"):
        game = _game_from(element, tables)
        if game is None:
            skipped += 1
            continue
        found.append(game)
    notes = [f"{path.name}: {skipped} "
             f"{'entry has' if skipped == 1 else 'entries have'} no name, so nothing "
             f"can be matched to {'it' if skipped == 1 else 'them'}"] if skipped else []
    return found, notes


def read_media(media_root: Path | str, games: list[SourceGame]) -> list[SourceGame]:
    """Attach each game's artwork, found the way the source finds it.

    A file belongs to a game when its filename starts with one of the game's names,
    compared without regard to case - a prefix, not an exact match, so `<name>.png` and
    `<name> (alt).png` both count.

    **Two names, because the two frontends disagree about which one they use.** PinballX
    names media after the `name` attribute, which is the table file. PinballY names it
    after the display name. Measured against a real PinballY library of 654 games: 5
    matched on the name attribute and 621 on the display name, so picking either one
    alone loses almost everything from the other frontend. Both are offered and the
    longest match wins, which is the rule that was already here.

    Where two names are prefixes of one another the longer one wins, and it has to be
    decided across the whole database rather than per game: `Taxi 2.png` starts with
    `Taxi`, so a library holding both would otherwise hand Taxi its neighbour's artwork
    while Taxi 2 kept it too. Preferring an exact name instead looks like the same fix
    and is not - it drops `<name> (alt).png`, which the source means.
    """
    media_root = Path(media_root)
    # Every name a game might be filed under, longest first, each pointing back at the
    # game it belongs to. Built once for the whole database because the longest-wins
    # rule cannot be decided a game at a time.
    folded: dict[str, str] = {}
    for game in games:
        for name in (game.key, game.display_name):
            if name:
                folded.setdefault(name.lower(), game.key)
    order = sorted(folded, key=len, reverse=True)

    found: dict[str, list[SourceMedia]] = {game.key: [] for game in games}
    for folder in MEDIA_FOLDERS:
        try:
            entries = [item for item in (media_root / folder).iterdir() if item.is_file()]
        except OSError:
            continue
        for item in entries:
            stem = item.stem
            if BACKUP_SUFFIX.search(stem):
                continue
            stem = stem.lower()
            owner = next((folded[name] for name in order if stem.startswith(name)), None)
            if owner is not None:
                found[owner].append(SourceMedia(source_kind=folder, path=str(item)))

    return [SourceGame(**{**vars(game), "media": tuple(found.get(game.key, ()))})
            for game in games]


# What a filesystem leaves lying about, which is not a system somebody set up. A share
# served from a NAS carries these beside real folders, and reporting one as a frontend
# we cannot play reads as a finding rather than as noise.
HOUSEKEEPING = ("@eadir", ".ds_store", "thumbs.db", "$recycle.bin", "system volume information")


def _housekeeping(name: str) -> bool:
    folded = name.strip().lower()
    return folded.startswith(".") or folded in HOUSEKEEPING


def _here(recorded: str, root: Path) -> str:
    """A path the source wrote down, as it is reachable from this machine."""
    if not recorded:
        return ""
    found = drivemap.resolve(recorded, root)
    return found.path or ""


def read(root: Path | str, plays=_plays_vpx,
         known_apps: tuple[str, ...] = ()) -> SourceLibrary:
    """Everything under one PinballX or PinballY root.

    Every emulator it declares, plus any database folder the config did not mention -
    a source whose ini did not travel still has its games, and they are the part worth
    having.
    """
    root = Path(root)
    declared, notes = read_config(root)
    by_name = {entry["name"]: entry for entry in declared}

    databases = root / DATABASES_DIR
    try:
        undeclared = sorted(item.name for item in databases.iterdir()
                            if item.is_dir() and item.name not in by_name
                            and not _housekeeping(item.name))
    except OSError:
        undeclared = []
    for name in undeclared:
        by_name[name] = {"name": name, "tables_dir": "", "working_path": "",
                         "enabled": True}
        notes.append(f"{name} has a database but the config does not declare it")

    systems = []
    mapped: set[str] = set()
    skipped = []
    for name, entry in by_name.items():
        if not _is_playable(entry, plays, known_apps):
            skipped.append(name)
            continue
        database = databases / name / f"{name}.xml"
        if not database.is_file():
            notes.append(f"{name} is declared but has no database at "
                         f"{DATABASES_DIR}/{name}/{name}.xml")
            continue
        recorded = entry["tables_dir"]
        found = drivemap.resolve(recorded, root) if recorded else drivemap.Found()
        declared_tables = found.path
        if recorded and not declared_tables:
            # A path written on the machine the source came from, and nothing here
            # holds it. Said out loud rather than quietly importing every game without
            # its table: the answer is to say where those files are now, and nobody can
            # give it without being told it is the question.
            notes.append(f"{name}: the tables are recorded at {recorded}, "
                         "which is not reachable from here")
        elif found.recorded_prefix and found.recorded_prefix not in mapped:
            mapped.add(found.recorded_prefix)
            notes.append(f"Reading {found.recorded_prefix} as {found.local_prefix} "
                         "- the paths recorded here are the old machine's")
        games, said = read_database(database, declared_tables, plays)
        notes.extend(said)
        games = read_media(root / MEDIA_DIR / name, games)
        systems.append(SourceSystem(name=name, games=tuple(games),
                                    # Where the tables are *here*, not where the old
                                    # machine wrote them down. Everything downstream
                                    # opens this: the plan offers it as the folder to
                                    # read from, and core is told to allow it. Handing
                                    # on `P:\...` names a folder that cannot be read and
                                    # cost a whole run of 581 files.
                                    tables_dir=declared_tables or recorded,
                                    # Resolved like the tables are, and for the same
                                    # reason: what is derived from it gets opened, and
                                    # the old machine's drive letter opens nothing.
                                    working_path=_here(entry["working_path"], root),
                                    enabled=entry["enabled"]))

    if skipped:
        # Named rather than dropped in silence. Somebody who set up Future Pinball wants
        # to know it was seen and left, not to wonder whether it was noticed at all.
        notes.append(f"Not brought in, because this build does not play them: "
                     f"{', '.join(sorted(skipped))}")

    return SourceLibrary(source_id=SOURCE_ID, root=str(root),
                         systems=tuple(systems), notes=tuple(notes))
