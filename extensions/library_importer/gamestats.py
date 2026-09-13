"""What a PinballY library remembers about playing.

A play count and a last-played date are the part of a library somebody actually misses
when they move machines: a collection that sorts by either is wrong on arrival without
them, and nobody can reconstruct them by hand.

`GameStats.csv` sits beside the frontend and is UTF-16 with a BOM, which is the same
trap its ini carries - read as UTF-8 it fails outright. Every column is text and most
are empty: of 746 rows in a real file, 92 had a play count and 33 had categories.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

STATS_FILE = "GameStats.csv"

# `Game` is "<display name>.<system>" - the same display name the artwork is filed
# under, not the table's filename. The suffix is how one name is told from another
# system's, and is dropped once the system is known.
KEY = "Game"
LAST_PLAYED = "Last Played"
PLAY_COUNT = "Play Count"
PLAY_TIME = "Play Time"
FAVORITE = "Is Favorite"
RATING = "Rating"
CATEGORIES = "Categories"


@dataclass(frozen=True)
class Played:
    """What one game's row remembers. Absent is None, which is not zero - a game nobody
    played and a game whose count was never written are different, and only one of them
    should overwrite what is already here."""

    name: str
    system: str
    play_count: int | None = None
    play_time_seconds: int | None = None
    last_played: int | None = None
    favorite: bool | None = None
    rating: int | None = None
    tags: tuple[str, ...] = ()

    @property
    def remembers_anything(self) -> bool:
        return any(one is not None for one in
                   (self.play_count, self.play_time_seconds, self.last_played,
                    self.favorite, self.rating)) or bool(self.tags)


def path_for(root: Path | str) -> Path:
    return Path(root) / STATS_FILE


def read(path: Path | str) -> tuple[list[Played], list[str]]:
    """Every row that remembers something, and anything worth saying about the read."""
    path = Path(path)
    if not path.is_file():
        return [], []
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [], [f"{path.name} could not be read: {exc}"]

    text, note = _text(raw, path.name)
    found = []
    for row in csv.DictReader(io.StringIO(text)):
        one = _played(row)
        if one is not None and one.remembers_anything:
            found.append(one)
    return found, ([note] if note else [])


def _text(raw: bytes, name: str) -> tuple[str, str]:
    """The file as text. UTF-16 first because that is what it is written in, and the
    others because a file somebody converted should still be read."""
    for encoding in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding), ""
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", "replace"), f"{name} is in no encoding this reads cleanly"


def _played(row: dict) -> Played | None:
    said = str(row.get(KEY) or "").strip()
    if not said:
        return None
    # Split from the right: a game's own name holds dots far more often than a system's
    # does - "1.2.3... (Talleres 1973).Visual Pinball X" is one real row.
    name, _, system = said.rpartition(".")
    if not name:
        name, system = said, ""
    return Played(
        name=name,
        system=system,
        play_count=_number(row.get(PLAY_COUNT)),
        play_time_seconds=_number(row.get(PLAY_TIME)),
        last_played=_when(row.get(LAST_PLAYED)),
        favorite=_flag(row.get(FAVORITE)),
        rating=_number(row.get(RATING)),
        tags=_tags(row.get(CATEGORIES)),
    )


def _number(value) -> int | None:
    said = str(value or "").strip()
    if not said:
        return None
    try:
        return int(float(said))
    except ValueError:
        return None


def _flag(value) -> bool | None:
    said = str(value or "").strip().lower()
    if not said:
        return None
    return said not in ("0", "no", "false")


def _tags(value) -> tuple[str, ...]:
    said = str(value or "").strip()
    if not said:
        return ()
    return tuple(one.strip() for one in said.split(",") if one.strip())


def _when(value) -> int | None:
    """`20221211012447` as epoch seconds.

    Read as local time, because that is what the frontend wrote: it recorded when
    somebody was standing there, with no zone beside it, and reading it as UTC would
    move every date by however far the machine is from Greenwich.
    """
    said = str(value or "").strip()
    if len(said) != 14 or not said.isdigit():
        return None
    try:
        when = datetime.strptime(said, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return int(when.astimezone(UTC).timestamp())
