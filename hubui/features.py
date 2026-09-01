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


@dataclass(frozen=True)
class State:
    """`noun` for a legend or a filter, `chip` to name it where there is room, `mark`
    to draw it where there is not, `why` to explain it on hover."""

    key: str
    noun: str
    chip: str
    mark: str
    why: str


# Not used draws nothing: most tables use most of these not at all, and a mark on every
# one would bury the two states worth seeing.
_STATES = {
    IN_SCRIPT: State(IN_SCRIPT, "In the script", "hub-tier--on", "hub-mark--full",
                     "The script uses it"),
    UNUSED: State(UNUSED, "Not used", "hub-tier--off", "",
                  "The script does not use it"),
    UNKNOWN: State(UNKNOWN, "Not parsed yet", "hub-tier--unknown", "hub-mark--dashed",
                   "Nothing has read this table's script"),
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
