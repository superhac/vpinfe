"""Game files: the launchable artifacts inside a table folder.

A folder can hold several .vpx, so everything asks here which one is the table.
"""

from __future__ import annotations

from collections.abc import Iterable

from common.timestamps import iso_from_asctime, iso_from_authored_date

VPX_SUFFIX = ".vpx"

# One entry per .vpx, keyed by filename:
#
#   "game_files": {
#     "Table (VR Room).vpx": {"version": "1.2", "rom": "afm_113b", "hidden": false, ...}
#   }
#
# A missing entry means a game file nothing has parsed, and a missing `hidden` means
# visible.
GAME_FILES_KEY = "game_files"

# Which game file is the default, kept in the vpinfe section because it is a table-level
# choice rather than something a game file says about itself.
DEFAULT_GAME_FILE_KEY = "default_game_file"

# What a game_files entry takes from a parse, in the parser's own names. The .vpx's
# manufacturer/year/type can disagree with what VPS says in Info; both are kept.
PARSED_KEYS = (
    "file_hash", "vbs_hash", "version", "release_date", "save_date", "save_rev",
    "rom", "manufacturer", "year", "type",
)

DETECT_KEYS = (
    "detect_nfozzy", "detect_fleep", "detect_ssf", "detect_lut",
    "detect_scorbit", "detect_fastflips", "detect_flex", "detect_pinmame",
)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return value == 1


def parse_authors(value) -> list[str]:
    """Authors as the .vpx records them. Per game file, never rolled up to the table."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(a).strip() for a in value if str(a).strip()]
    return [a.strip() for a in str(value).split(",") if a.strip()]


def entry_from_parsed(parsed: dict | None) -> dict:
    """A game_files entry from one VPXParser result.

    A failed parse resolves to empty values rather than borrowing from elsewhere in
    the .info: a half-filled entry reads as fact and isn't.
    """
    parsed = parsed if isinstance(parsed, dict) else {}
    entry = {key: parsed.get(key, "") or "" for key in PARSED_KEYS}
    # Dates are normalized on the way in, so the stored value sorts and filters. The
    # author's raw string is recoverable by re-parsing the .vpx beside the .info.
    entry["release_date"] = iso_from_authored_date(entry["release_date"])
    entry["save_date"] = iso_from_asctime(entry["save_date"])
    entry["authors"] = parse_authors(parsed.get("author_name", ""))
    for key in DETECT_KEYS:
        entry[key] = _as_bool(parsed.get(key, False))
    return entry


def is_parsed(entry: dict | None) -> bool:
    """Whether an entry describes a game file we have read, rather than one we only recorded
    something about - hidden, or where it came from. Reading those as parsed answers "no
    rom declared" for a file nothing has opened.
    """
    if not isinstance(entry, dict):
        return False
    return any(key in entry for key in PARSED_KEYS)


def game_file_names(names: Iterable[str]) -> list[str]:
    """The game files in a folder listing, sorted case-insensitively."""
    return sorted((n for n in names if n.lower().endswith(VPX_SUFFIX)), key=str.lower)


def hidden_game_files(settings: dict | None) -> set[str]:
    """Filenames the user has hidden from the frontend. Hiding never deletes - a patch
    base has to stay on disk - it only stops the game file being offered.
    """
    if not isinstance(settings, dict):
        return set()
    return {
        name for name, entry in settings.items()
        if isinstance(entry, dict) and entry.get("hidden") is True
    }


def visible_game_files(names: Iterable[str], settings: dict | None = None) -> list[str]:
    """The game files a frontend should offer. Each is independently launchable: several
    game files of one table are peers, not a primary with alternates."""
    hidden = hidden_game_files(settings)
    return [n for n in game_file_names(names) if n not in hidden]


def default_game_file(names: Iterable[str], folder_name: str = "", recorded: str = "") -> str:
    """Which game file a single-game-file consumer gets, or "" when there are none.

    Not "the one to launch" - every visible game file is launchable. This is for the
    places that must pick exactly one: an export, a table row, any theme written so far.

    Falling through to the first by name is deterministic rather than correct, which is
    the point: the alternative is directory order.
    """
    candidates = game_file_names(names)
    if not candidates:
        return ""

    recorded = (recorded or "").strip()
    if recorded in candidates:
        return recorded

    stem = (folder_name or "").strip().lower()
    if stem:
        for name in candidates:
            if name[: -len(VPX_SUFFIX)].lower() == stem:
                return name

    return candidates[0]


def game_file_entries(meta: dict | None) -> dict:
    """The game_files section of a table's metadata, or {} when it has none."""
    if not isinstance(meta, dict):
        return {}
    entries = meta.get(GAME_FILES_KEY)
    return entries if isinstance(entries, dict) else {}


def recorded_default(vpinfe: dict | None) -> str:
    """A default someone chose for this table, or "". Takes the vpinfe section itself, so
    this module stays out of what that section is called.

    Absent is the normal case and means "resolve from what is in the folder" - it is
    never written on a rebuild, which would freeze an arbitrary pick as a choice.
    """
    if not isinstance(vpinfe, dict):
        return ""
    return str(vpinfe.get(DEFAULT_GAME_FILE_KEY, "") or "").strip()
