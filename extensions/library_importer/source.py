"""What a foreign library says, in that library's own words.

A source root is a foreign root: nothing here borrows a name from our launcher, our
config or our locations, and the media kinds are whatever the source calls them. Turning
any of it into ours is the importer's job and happens once, on the way in - a reader that
already spoke our vocabulary would be deciding the mapping in four places instead of one.

Nothing in this module reads a file. The readers fill it in.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceMedia:
    """One artwork file, and what the source filed it under."""

    # The source's own name for the kind - a PinballX media folder, an EmulationStation
    # element. Mapped to ours later, by the half that is allowed to know ours.
    source_kind: str
    path: str


@dataclass(frozen=True)
class SourceGame:
    """One game as the source describes it.

    `key` is what the source calls it, and is the name its media is found by. Never the
    description: the two differ in every source read so far, and matching on the
    description finds nothing.
    """

    key: str
    # What the source puts in front of a person. PinballX's `description` is one -
    # "Attack from Mars (Bally 1995)" - and EmulationStation's is prose about the game,
    # so the two cannot share a field however alike the element names look.
    display_name: str = ""
    # A sentence about the game, where the source keeps one. Nothing of ours stores it.
    blurb: str = ""
    title: str = ""
    manufacturer: str = ""
    year: str = ""
    game_type: str = ""
    themes: tuple[str, ...] = ()
    ipdb_id: str = ""
    # Some sources carry one. An import from those arrives matched rather than as a pile
    # of games somebody works through by hand.
    vps_id: str = ""
    rom: str = ""
    rating: str = ""
    players: str = ""
    author: str = ""
    version: str = ""
    comment: str = ""
    # The game file, absolute, or "" where the source names none.
    table_file: str = ""
    # The source was told not to show it.
    hidden: bool = False
    media: tuple[SourceMedia, ...] = ()
    # What the source held that has no home of ours, so a preview can say what will not
    # be carried rather than dropping it quietly.
    extras: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceSystem:
    """One of the things a source holds a library for - a PinballX emulator, an
    EmulationStation system. A source can carry several, and only some are pinball."""

    name: str
    games: tuple[SourceGame, ...] = ()
    # The directory the source keeps this system's game files in. Plural and not a
    # game folder: a source lays its tables out flat, which is the layout being
    # converted away from.
    tables_dir: str = ""
    # The application directory the source launched it from.
    working_path: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class SourceLibrary:
    """Everything one reader found under one root."""

    source_id: str
    root: str
    systems: tuple[SourceSystem, ...] = ()
    # Anything a person should be told about the read itself: a database that would not
    # parse, a media folder that was not there. Not failures - a source is somebody
    # else's data and is very often part-broken, and refusing the whole read over one
    # bad row would leave them with nothing.
    notes: tuple[str, ...] = ()

    @property
    def games(self) -> tuple[SourceGame, ...]:
        return tuple(game for system in self.systems for game in system.games)
