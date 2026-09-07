"""How a game and a table are named and shown, in one vocabulary.

Do not reuse `media_ownership.py`'s nouns here: "This table" and "All tables" are about
which media file wins, and borrowing them would overload a vocabulary that is correct.
"""

from __future__ import annotations

from typing import Any

JOIN = " · "

# The groups a fact belongs to, spelled once: the panel draws them as headings and the
# grid's built-in views are named for them, so crossing between the two is not a
# translation. Only the groups that have rows.
MACHINE = "Machine"
# "Table File", not "File": a panel that also shows a table ini, a script and a rom
# left a reader asking which file. Chris, 2026-09-01, with `Default Table` below.
FILE = "Table File"
FEATURES = "Features"
# What a keyed entry's group is called where the file group would be. There is no file,
# so "Table File" would be a heading over a blank - and the thing it does have is the
# name its program knows it by.
KNOWN_AS = "Known As"
# A referenced entry's group. Not "Table File", which reads as a file of this game's -
# the whole point of one of these is that the file belongs somewhere else.
ELSEWHERE = "Where It Is"

# What a reference is doing right now. Notable first, like every pair here. **Not
# Missing** - nothing is lost when a share has not mounted, and the word that tells
# somebody a file was deleted is the wrong word for a location being away.
REACH_WORDS = ("Unreachable", "Reachable")
LAUNCH = "Launch"
PLAY = "Play"
FRONTEND = "Frontend"

# What a reference points at: whichever table the game offers, or exactly one. `GONE` is
# not a third kind - it is either of the two, naming something absent.
FOLLOWS = "default"
FIXED = "fixed"
GONE = "missing"

# The state's name, then the line behind it. Both answer "which table plays?", in the
# same shape so they read as a pair. Short because this is read down a long list, where
# a sentence per row is noise.
REFERENCE_WORDS = {
    FOLLOWS: ("Game Default", "Whichever table the game offers"),
    FIXED: ("User Defined", "Only this table"),
    GONE: ("Missing", "Not in this library"),
}

# Drawn, not typed: as characters these are not a matched pair. Measured in the Console's
# own font at 15px, ● is 9.4px across and ◐ is 15px, so the smaller state read as a
# speck. CSS circles are the same diameter by construction.
#
# Full and outline are the two ends of the ramp - the clearest pair there is, and this
# vocabulary has only two states to spend.
MARKS = {
    FIXED: "console-mark--full",
    FOLLOWS: "console-mark--outline",
    GONE: "console-mark--dashed",
}

# The legend, because a tooltip cannot be the only one - it does not exist on a touch
# device. It names the two states; the difference between them is its own tooltip.
KEY_WORDS = ((FIXED, "User Defined"), (FOLLOWS, "Game Default"))
KEY_DETAIL = ("User defined stays on the table it names. Game default follows the "
              "game, so a replacement is picked up.")


def native_key(table: dict[str, Any] | None) -> str:
    """What names this entry to the install: its filename, or `app:key` where it has no
    file. The one string the launch path, the API and this surface all speak."""
    held = table or {}
    key = str(held.get("key") or "").strip()
    if key:
        return f"{str(held.get('app') or '').strip()}:{key}"
    reference = str((held.get("reference") or {}).get("path") or "").strip()
    return reference or str(held.get("filename") or "")


def is_keyed(table: dict[str, Any] | None) -> bool:
    """Whether this entry has no file. Read off `form`, which the install derives."""
    return str((table or {}).get("form") or "") == "keyed"


def is_referenced(table: dict[str, Any] | None) -> bool:
    """Whether this entry's file is somewhere other than the game folder."""
    return str((table or {}).get("form") or "") == "referenced"


def mark(state: str) -> str:
    """The classes for one state's mark, base first."""
    return f"console-mark {MARKS.get(state, MARKS[FOLLOWS])}"


# How a game's default was decided, said as a state rather than as an actor: "User"
# named who acted. The pair differs in kind - a decision, or the absence of one - and
# the second of each is what it costs the reader, which is the part they act on.
CHOSEN = "user"
DERIVED = "auto"

DEFAULT_WORDS = {
    CHOSEN: ("Chosen", "Stays on this table"),
    DERIVED: ("Automatic", "May move when the library changes"),
}

# One name and one direction per fact, read by the column, the panel, the funnel and the
# row menu. Notable is first; docs/conventions.md has why.
HIDDEN_WORDS = ("Hidden", "Offered")
FILE_WORDS = ("Missing", "Present")
# Which script runs, not how the file got there: VPX loads a `<table>.vbs` sidecar in
# place of the one inside the .vpx, so the sidecar is an override and "Extracted" named
# only its provenance. External is the notable half - it is the table running something
# other than what its author shipped.
SCRIPT_WORDS = ("External", "Internal")
# Whether every required asset resolves. Notable first, like the pairs above, because
# the ordinary table runs - a word on every row that says so tells a reader nothing.
# Three-valued, so the unknown has its own word: a table nothing has parsed cannot be
# called ready and has not been found wanting either.
LAUNCH_WORDS = ("Blocked", "Ready")

# The label, not the state - "Default" alone left a reader asking "default what?" on a
# panel that also has a default launcher and a default view. Named here so the grid and
# the workbench cannot answer it differently. Chris, 2026-09-01.
DEFAULT_LABEL = "Default Table"
LAUNCH_UNKNOWN = "Unknown"


def word_for(pair: tuple[str, str], notable: bool) -> str:
    """A fact's own word for the state it is in, notable first. A helper for a one-line
    lookup because the one line is where it goes wrong: `pair[not present]` at a call
    site put "Missing" on a file that was on disk."""
    return pair[0] if notable else pair[1]


def table_name(table: dict[str, Any]) -> str:
    """Which table this is: version then author, one order everywhere.

    The filename only as a fallback: it is what the pair above exists to avoid falling
    back to. `authors` is a list on the wire
    and `author` a joined string in a grid row; both are read, because both call this.
    """
    authors = table.get("authors")
    if isinstance(authors, list):
        author = ", ".join(str(a) for a in authors if str(a).strip())
    else:
        author = str(table.get("author") or "").strip()
    version = str(table.get("version") or "").strip()
    said = JOIN.join(part for part in (version, author) if part)
    # An entry with no file has no version or author either - nothing read one. What
    # names it is what its program calls it, or the file it points at.
    if said:
        return said
    reference = table.get("reference") or {}
    return (str(table.get("filename") or "") or str(table.get("key") or "")
            or str(reference.get("path") or ""))


def reference_state(origin: str) -> tuple[str, str]:
    """The word for what a reference points at, and the sentence behind it."""
    return REFERENCE_WORDS.get(origin, REFERENCE_WORDS[FOLLOWS])


def default_state(kind: str) -> tuple[str, str] | None:
    """The word for how a default was decided, or None where this is not the default."""
    return DEFAULT_WORDS.get(kind)
