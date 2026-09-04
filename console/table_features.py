"""What a table's script was seen to use, in one vocabulary.

Three states, not two: a table nobody has parsed yet answers null for every feature, and
reading that as no gives an unparsed table a clean bill of health it never earned.

PinMAME is not here - the ROM answers it, in more detail than a tick could.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The names as their authors write them, which is how they appear in a table's notes
# and on VPS. Case included: "nFozzy" and "FastFlips" are not sentence case by accident.
LABELS = {
    "nfozzy": "nFozzy", "fleep": "Fleep", "ssf": "SSF", "lut": "LUT",
    "scorbit": "Scorbit", "fastflips": "FastFlips", "flexdmd": "FlexDMD",
}

IN_SCRIPT = "in_script"
UNUSED = "unused"
UNKNOWN = "unknown"


def states_in(rows) -> list[str]:
    """The states this library draws, in the vocabulary's own order.

    A legend names what a reader can see. Two things are not that: a state that draws
    nothing - `media_ownership` leaves Missing out for the same reason, a blank cell is
    not something anybody looks up - and a state the library does not contain, which
    `unknown` is except between discovery finding a table and the parse job reaching it.
    """
    seen = set()
    for row in rows:
        for key in LABELS:
            if f"feature_{key}" in row:
                seen.add(state_of(row.get(f"feature_{key}")).key)
    return [key for key in STATES
            if key in seen and (_STATES[key].glyph or _STATES[key].mark)]


@dataclass(frozen=True)
class State:
    """`noun` for a legend or a filter, `chip` to name it where there is room, `mark`
    to draw it where there is not, `why` to explain it on hover."""

    key: str
    noun: str
    chip: str
    mark: str
    why: str
    # How the state is drawn, and coloured. Characters, not the shaped circles: a
    # dashed one already means Missing in the media tiers, and a table nobody has read
    # is not a missing one.
    glyph: str = ""
    glyph_class: str = ""


# Not used draws nothing: most tables use most of these not at all, and a mark on every
# one would bury the two states worth seeing.
_STATES = {
    IN_SCRIPT: State(IN_SCRIPT, "In the script", "console-tier--on", "",
                     "The script uses it", glyph="\u2713", glyph_class="console-tick"),
    UNUSED: State(UNUSED, "Not used", "console-tier--off", "",
                  "The script does not use it"),
    UNKNOWN: State(UNKNOWN, "Not parsed yet", "console-tier--unknown", "",
                   "Nothing has read this table's script", glyph="?",
                   glyph_class="console-unknown"),
}

# All three, unlike a media legend: "not used" is drawn as nothing, so it is exactly the
# one a reader has to look up.
STATES = (IN_SCRIPT, UNUSED, UNKNOWN)


def key_of(value: Any) -> str:
    """Which of the three a payload value is. Null is its own answer, never a no."""
    if value is None:
        return UNKNOWN
    return IN_SCRIPT if value else UNUSED


def state_of(value: Any) -> State:
    return _STATES[key_of(value)]


def state_for(key: str) -> State:
    return _STATES[key]
