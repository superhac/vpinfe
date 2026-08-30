"""How a game and a table are named and shown, in one vocabulary. HUBUI section 13.

Do not reuse `media_ownership.py`'s nouns here: "This table" and "All tables" are about
which media file wins, and borrowing them would overload a vocabulary that is correct.
"""

from __future__ import annotations

from typing import Any

JOIN = " · "

# What a reference points at: whichever table the game offers, or exactly one. `GONE` is
# not a third kind - it is either of the two, naming something absent.
FOLLOWS = "default"
FIXED = "fixed"
GONE = "missing"

# The state's name, then the line behind it. Both answer "which table plays?", in the
# same shape so they read as a pair; what the difference *costs* is the legend's job.
# Short because this is read down a long list, where a sentence per row is noise. It
# goes on the table line rather than in the chip slot, which belongs to states about
# the row itself.
REFERENCE_WORDS = {
    FOLLOWS: ("Game Default", "Whichever table the game offers"),
    FIXED: ("User Defined", "Only this table"),
    GONE: ("Missing", "Not in this library"),
}

# Shared with the media glyphs in `data.py`, which ask the same question: ● is bound to
# one table, ◐ belongs to the game. One thing to learn rather than two.
GLYPHS = {
    FIXED: "\u25cf",
    FOLLOWS: "\u25d0",
    GONE: "\u25cc",
}

# The legend, because a tooltip cannot be the only one - it does not exist on a touch
# device. It names the two states; the difference between them is its own tooltip.
KEY = "\u25cf User Defined    \u25d0 Game Default"
KEY_DETAIL = ("User defined stays on the table it names. Game default follows the "
              "game, so a replacement is picked up.")


def glyph(state: str) -> str:
    return GLYPHS.get(state, GLYPHS[FOLLOWS])


# How a game's default was decided. The resolver has three steps; a reader only cares
# whether they chose it or we did.
CHOSEN = "user"
DERIVED = "auto"

DEFAULT_WORDS = {
    CHOSEN: ("User", "Somebody chose this table as the game's default."),
    DERIVED: ("Auto", "Picked for this game because nothing was chosen."),
}


def table_name(table: dict[str, Any]) -> str:
    """Which table this is: version then author, one order everywhere.

    The filename only as a fallback - section 11 is why. `authors` is a list on the wire
    and `author` a joined string in a grid row; both are read, because both call this.
    """
    authors = table.get("authors")
    if isinstance(authors, list):
        author = ", ".join(str(a) for a in authors if str(a).strip())
    else:
        author = str(table.get("author") or "").strip()
    version = str(table.get("version") or "").strip()
    said = JOIN.join(part for part in (version, author) if part)
    return said or str(table.get("filename") or "")


def reference_state(origin: str) -> tuple[str, str]:
    """The word for what a reference points at, and the sentence behind it."""
    return REFERENCE_WORDS.get(origin, REFERENCE_WORDS[FOLLOWS])


def default_state(kind: str) -> tuple[str, str] | None:
    """The word for how a default was decided, or None where this is not the default."""
    return DEFAULT_WORDS.get(kind)
