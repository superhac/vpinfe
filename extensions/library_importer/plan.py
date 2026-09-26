"""What an import would do, before it does any of it.

Two questions this answers, and they are the same question asked twice: where does each
kind of thing come from, and what is already here.

**Every source is an option with a derived default.** A reader works out where the tables
and the artwork are; the user can say otherwise, and can leave one empty. Empty means that
kind is not imported - stated rather than implied, because "no ROMs came across" should be
something somebody chose and can see they chose.

**And an import can be run more than once.** A first pass fails partway, or somebody
imports the games now and the ROMs when the old machine is back on the network. So this
says what is new and what is already here before anything is written, and an existing game
is left alone unless the user says to fill in what it is missing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.extensions.contract import words

from . import gamestats, mapping
from .source import Note, SourceGame, SourceLibrary

t = words("library_importer")

# The kinds of thing an import can bring, in the order they are asked about, by the key
# the wizard calls the field.
SOURCES = ("tables", "media", "roms", "altdata", "history")

# Derived and deliberately not offered. The reading works; there is nowhere settled to
# put what it reads, and a field that carries nothing is a promise the code cannot keep.
#
# Registry settings have no destination at all on this platform, which is upstream's
# decision rather than an omission: VPinMAME's per-ROM values live in memory, set by a
# table's own script and falling back to a table of Windows defaults. Nothing persists
# them, so anything written would be read by nothing.
NOT_YET = ("registry",)

# What a second run does about a game it has already made. The default leaves it alone:
# an import that quietly rewrites what somebody has since curated is the worse mistake.
ON_EXISTING = ("skip", "fill")
DEFAULT_ON_EXISTING = "skip"


@dataclass
class Source:
    """Where one kind of thing comes from, and how we came to think so."""

    key: str
    label: str
    help: str
    path: str = ""
    derived: bool = False

    @property
    def active(self) -> bool:
        return bool(self.path)


@dataclass
class Match:
    """One game the source holds, against what the library already has."""

    key: str
    folder: str
    game_id: str = ""
    how: str = ""
    # Counted here because here is where the game is in hand. Looking them up later by
    # key cannot work: a real library held two entries with byte-identical keys, and a
    # dict keyed on them silently counts one.
    tables: int = 0
    media: int = 0
    companions: int = 0
    history: int = 0

    @property
    def existing(self) -> bool:
        return bool(self.game_id)


@dataclass
class Plan:
    sources: list[Source] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    on_existing: str = DEFAULT_ON_EXISTING
    history: dict[str, gamestats.Played] = field(default_factory=dict)
    notes: list[Note] = field(default_factory=list)

    @property
    def new(self) -> list[Match]:
        return [one for one in self.matches if not one.existing]

    @property
    def already(self) -> list[Match]:
        return [one for one in self.matches if one.existing]

    def source(self, key: str) -> Source | None:
        return next((one for one in self.sources if one.key == key), None)


# What the report counts, in the order it reads. The same keys come back from the run,
# so expected and actual are one shape and a difference is a subtraction rather than a
# comparison somebody has to make by eye.
COUNTS = ("games", "tables", "media", "companions", "history")


def expected(plan: Plan) -> dict:
    """What this import should produce, counted before it runs.

    Counted the way the run counts, not the way the source reads, because those differ
    in two places and a report that ignores either reads as a shortfall for working
    correctly. Several builds of one machine become one game, and only the first of them
    brings artwork - the rest are the same table photographed twice.

    A source that is not set contributes nothing and says zero rather than being left
    out: "no artwork" is a number somebody chose, and an absent row reads as an oversight.
    """
    wanted = _wanted(plan)
    has = {source.key: bool(source.active) for source in plan.sources}

    folders, tables, media, companions, history = set(), 0, 0, 0, 0
    for one in wanted:
        first = one.folder.lower() not in folders
        folders.add(one.folder.lower())
        if has.get("tables"):
            tables += one.tables
            # They ride with the table, so they arrive only where it does.
            companions += one.companions
        # Artwork and history ride with the game, and the game is made once.
        if has.get("media") and first:
            media += one.media
        if first:
            history += one.history

    return {"games": len(folders), "tables": tables, "media": media,
            "companions": companions, "history": history, "roms": 0}


def _wanted(plan: Plan) -> list[Match]:
    """The games this run will act on, which is not every game the source holds."""
    return plan.matches if plan.on_existing == "fill" else plan.new


def against(expected_counts: dict, actual: dict) -> list[dict]:
    """Expected beside actual, with the difference, for the report.

    Both are shown even where they agree: a row that only appears when something went
    wrong makes a clean import look like a report with things missing from it.
    """
    rows = []
    for key in COUNTS:
        want = int(expected_counts.get(key, 0) or 0)
        got = int(actual.get(key, 0) or 0)
        rows.append({"key": key, "label": t(f"count.{key}"), "expected": want,
                     "actual": got, "short": want - got})
    return rows


def derive_sources(library: SourceLibrary, chosen: dict | None = None) -> list[Source]:
    """Where each kind of thing appears to live, and whatever the user said instead.

    Derived first so the common case is one press. A value the user typed always wins,
    including an empty one - clearing a source is how somebody says "not that".
    """
    chosen = chosen or {}
    tables = next((one.tables_dir for one in library.systems if one.tables_dir), "")
    media = ""
    for system in library.systems:
        for game in system.games:
            if game.media:
                media = str(Path(game.media[0].path).parent.parent)
                break
        if media:
            break
    # Nothing derives a registry export: a share does not carry one unless somebody
    # exported it on purpose, so this stays empty until it is pointed at.
    # VPinMAME keeps its own folders beside the emulator, not in it - a real machine
    # recorded `rompath` as `<install>\VPinMame\roms`, and the sound and color banks
    # sit beside that. So the emulator's own directory is where the search starts rather
    # than where it ends, and an empty answer leaves the field for somebody to fill.
    working = next((one.working_path for one in library.systems if one.working_path), "")
    guessed = {"tables": tables, "media": media,
               "roms": _under(working, ("VPinMAME", "roms"), ("roms",)),
               "altdata": _under(working, ("VPinMAME",), ()),
               "history": _file_at(library.root, gamestats.STATS_FILE),
               "registry": ""}

    found = []
    for key in SOURCES:
        said = chosen.get(key)
        path = str(said if said is not None else guessed.get(key, "") or "").strip()
        found.append(Source(key=key, label=t(f"kind.{key}.label"),
                            help=t(f"kind.{key}.help"), path=path,
                            derived=said is None and bool(path)))
    return found


def _file_at(root: str, name: str) -> str:
    """A file beside the frontend, where it is the source for a whole kind rather than
    a folder of them."""
    if not root:
        return ""
    wanted = Path(root) / name
    try:
        return str(wanted) if wanted.is_file() else ""
    except OSError:
        return ""


def _under(root: str, *candidates: tuple[str, ...]) -> str:
    """The first of these that is actually there, or nothing.

    Nothing rather than a guess: an empty field reads as "not being imported", which is
    a state somebody can see and correct. A path that does not exist reads as a promise.
    """
    if not root:
        return ""
    base = Path(root)
    for parts in candidates:
        wanted = base.joinpath(*parts) if parts else base
        try:
            if wanted.is_dir():
                return str(wanted)
        except OSError:
            continue
    return ""


def match_existing(library: SourceLibrary, existing: list[dict],
                   systems: list[str] | None = None,
                   folder_name_for: Callable[[str], str] | None = None,
                   source_id: str = "",
                   kinds: tuple[str, ...] = (),
                   companions_of: Callable[..., Any] | None = None,
                   history: dict[str, gamestats.Played] | None = None) -> list[Match]:
    """Which of the source's games the library already holds.

    By the folder this import would create first, because that is what a previous run of
    this import made. Then by catalog id, which catches a game somebody has since renamed
    - a rename should not turn one game into two.

    Folder names are compared with their quotes taken off. A real library held
    `\'300\' (Gottlieb 1975)` while the source called it `"300" (Gottlieb 1975)`, and
    the quote a filesystem cannot keep is the one thing separating them - matched
    literally, one machine ends up with the game twice.
    """
    by_folder = {_folded(one.get("folder_name")): one for one in existing}
    by_vps = {str(one.get("vps_id") or "").lower(): one
              for one in existing if one.get("vps_id")}

    found = []
    for game in _games(library, systems):
        folder = mapping.folder_name(game)
        if folder_name_for:
            folder = folder_name_for(folder)
        folded = _folded(folder)
        held = by_folder.get(folded)
        how = "folder" if held else ""
        if held is None and game.vps_id:
            held = by_vps.get(game.vps_id.lower())
            how = "catalog_id" if held else ""
        played = history_for(history or {}, game)
        found.append(Match(key=game.key, folder=folder,
                           game_id=str(held.get("game_id") or "") if held else "",
                           how=how,
                           tables=1 if game.table_file else 0,
                           media=len(mapping.media_for(source_id, game, kinds)),
                           companions=(len(companions_of(game.table_file))
                                       if companions_of and game.table_file else 0),
                           history=1 if played and played.counts_as_history else 0))
    return found


# Quotes and the characters a filesystem substitutes for them. Stopping here on purpose:
# stripping punctuation generally would make `Taxi` and `Taxi 2` the same game, and a
# library that merges two machines is worse than one that holds a duplicate.
_QUOTES = str.maketrans("", "", "\"'‘’“”`")


def _folded(name: Any) -> str:
    """A folder name as it is compared: cased down, quotes taken off, spaces collapsed."""
    said = str(name or "").translate(_QUOTES).lower()
    return " ".join(said.split())


def _games(library: SourceLibrary,
           systems: list[str] | None) -> list[SourceGame]:
    """The games in the systems being brought across, which is not always all of them.

    A system somebody deselected has to drop out here rather than at the run, or what
    the summary counts and what the import does are two different libraries.
    """
    wanted = set(systems or [])
    return [game for system in library.systems
            if not wanted or system.name in wanted
            for game in system.games]


def build(library: SourceLibrary, existing: list[dict], chosen: dict | None = None,
          on_existing: str = DEFAULT_ON_EXISTING,
          systems: list[str] | None = None,
          folder_name_for: Callable[[str], str] | None = None,
          source_id: str = "", kinds: tuple[str, ...] = (),
          companions_of: Callable[..., Any] | None = None) -> Plan:
    sources = derive_sources(library, chosen)
    history, notes = _history(next((one.path for one in sources if one.key == "history"),
                                   ""))
    return Plan(sources=sources,
                matches=match_existing(library, existing, systems, folder_name_for,
                                       source_id, kinds, companions_of, history),
                on_existing=on_existing if on_existing in ON_EXISTING
                else DEFAULT_ON_EXISTING,
                history=history, notes=notes)


def _history(path: str) -> tuple[dict[str, gamestats.Played], list[Note]]:
    """What the source remembers, by the name it files a game under.

    Keyed on the display name because that is what the stats file writes - the same name
    the artwork is filed under, not the table's filename. Folded, because two frontends
    disagree about case and nobody typed either of them twice.
    """
    if not path:
        return {}, []
    found, notes = gamestats.read(path)
    return {_filed_as(one.name): one for one in found}, notes


def history_for(history: dict[str, gamestats.Played],
                game: SourceGame) -> gamestats.Played | None:
    """The row the source remembers this game by, if it has one."""
    return history.get(_filed_as(game.display_name))


def _filed_as(name: str) -> str:
    return name.strip().lower()
