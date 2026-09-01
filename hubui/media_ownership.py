"""Who owns a media file, in one vocabulary.

Six surfaces said this five different ways before this existed, because each new one
invented its own words. The names are the resolver's own: a *table* is one .vpx, a
*game* is the folder holding them. Its five tiers collapse to four states here, since
two of the distinctions are about our filename conventions and not about anything a
user has a concept for.
"""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from common.media_specs import media_label_map

# One .vpx owns it; the game owns it; something else is standing in; nothing is here.
TABLE = "table"
GAME = "game"
STAND_IN = "stand_in"
MISSING = "missing"


@dataclass(frozen=True)
class Tier:
    """The forms a surface might need: `noun` for a badge or a cell, `phrase` for
    inline in somebody else's sentence, `css` to color it, `mark` to draw it, `why`
    to explain it on hover. Whole sentences are built rather than stored, because two
    of them depend on what is being looked at."""

    key: str
    noun: str
    phrase: str
    css: str
    mark: str
    why: str


# The marks are a ramp by specificity: filled is bound to one table, hollow is the
# least specific, and a stand-in is the odd one out so it does not read as a degree of
# the others.
_TIERS = {
    TABLE: Tier(TABLE, "This table", "just this table", "hub-tier--table",
                "hub-mark--full", "A file named for this table, and only it uses it"),
    GAME: Tier(GAME, "All tables", "shared by every table", "hub-tier--game",
               "hub-mark--outline", "A file the whole game shares"),
    STAND_IN: Tier(STAND_IN, "Stand-in", "standing in for it", "hub-tier--standin",
                   "hub-mark--set", "Something else is filling this slot"),
    MISSING: Tier(MISSING, "Missing", "not here", "hub-tier--missing",
                  "hub-mark--dashed", "Nothing here"),
}

# Most specific first. `LEGEND` omits Missing, which a legend does not need - a blank
# cell is not a state anybody looks up - and `STATES` is all four, for a caller that
# has to map every one.
STATES = (TABLE, GAME, STAND_IN, MISSING)
LEGEND = (TABLE, GAME, STAND_IN)


def tier_for(key: str) -> Tier:
    """The entry for a state that is already named, which a legend walks."""
    return _TIERS[key]


def key_of(via: str | None) -> str:
    """Which of the four a resolver tier is.

    `game` and `default` are one state: both are the folder's and every table in it
    uses them. What separates them is which filename convention they follow, which is
    ours and not the user's. `set` and `fallback` are one state too - either way the
    file serving this slot was named for something other than this slot.
    """
    via = str(via or "")
    if via == TABLE:
        return TABLE
    if via in (GAME, "default"):
        return GAME
    if via.startswith(("set:", "fallback:")):
        return STAND_IN
    return MISSING


# What the asset resolver calls the same three states. It answers `dedicated` /
# `shared` / `none` where media answers a `via`, and the question is identical - which
# file wins for this table - so the words are these and not a second set.
_RESOLUTIONS = {"dedicated": TABLE, "shared": GAME, "none": MISSING}


def key_of_resolution(resolution: str | None) -> str:
    """Which tier an `asset_resolver` resolution is."""
    return _RESOLUTIONS.get(str(resolution or ""), MISSING)


def of(via: str | None) -> Tier:
    return _TIERS[key_of(via)]


def for_resolution(resolution: str | None) -> Tier:
    return _TIERS[key_of_resolution(resolution)]


def noun(via: str | None) -> str:
    return of(via).noun


def phrase(via: str | None) -> str:
    return of(via).phrase


def sentence(via: str | None, *, viewing_a_table: bool = False) -> str:
    """Who uses this file, in a line.

    No full stop: it is one line of helper text under a name, not prose, and a stop at
    the end of a lone fragment reads like the start of a paragraph that never came.
    """
    key = key_of(via)
    if key == TABLE:
        return "Only this table uses it"
    if key == GAME:
        return ("This table has none of its own, so it uses what the game shares"
                if viewing_a_table else "Every table in this game uses it")
    if key == STAND_IN:
        detail = str(via or "").split(":", 1)[-1]
        if str(via or "").startswith("set:"):
            return f"From the “{detail}” set"
        borrowed = media_label_map().get(detail, detail).lower()
        return f"Standing in from the {borrowed} - this kind has none of its own"
    return ""


def badge(via: str | None, *, extra: str = "") -> ui.element:
    """The one visual mark for who owns a file, wherever a file is shown."""
    tier = of(via)
    return ui.label(tier.noun).classes(f"hub-tier {tier.css} {extra}".strip())
