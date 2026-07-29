"""Game files: the launchable artifacts inside a table folder.

A folder can hold several .vpx, so everything asks here which one is the table.
"""

from __future__ import annotations

from collections.abc import Iterable

VPX_SUFFIX = ".vpx"

# One entry per .vpx in the folder, keyed by filename - everything the build says
# about itself, plus what the user has decided about it:
#
#   "game_files": {
#     "Table (VR Room).vpx": {"version": "1.2", "rom": "afm_113b", "hidden": false, ...}
#   }
#
# The filename is the key, so it is not repeated inside the entry. A missing entry
# means an unparsed build, and a missing `hidden` means visible.
GAME_FILES_KEY = "game_files"

# Which build is the default, kept in the vpinfe section because it is a table-level
# choice rather than something a build says about itself.
DEFAULT_GAME_FILE_KEY = "default_game_file"

# What a game_files entry takes from a parse. The parser emits these names directly -
# there is no translation layer, because we own both ends.
#
# manufacturer/year/type are the .vpx's own claim about the machine and can disagree
# with what VPS says in Info. Both are kept: the disagreement is a signal, not noise.
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
    """Authors as the .vpx records them. Per build, never rolled up to the table -
    measured across the test library, half of the multi-build folders name different
    authors on different builds."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(a).strip() for a in value if str(a).strip()]
    return [a.strip() for a in str(value).split(",") if a.strip()]


def entry_from_parsed(parsed: dict | None) -> dict:
    """A game_files entry from one VPXParser result.

    Everything here is what the file says about itself. A failed parse resolves to
    empty values rather than to anything borrowed from elsewhere in the .info -
    a half-filled entry reads as fact and isn't.
    """
    parsed = parsed if isinstance(parsed, dict) else {}
    entry = {key: parsed.get(key, "") or "" for key in PARSED_KEYS}
    entry["authors"] = parse_authors(parsed.get("author_name", ""))
    for key in DETECT_KEYS:
        entry[key] = _as_bool(parsed.get(key, False))
    return entry


def game_file_names(names: Iterable[str]) -> list[str]:
    """The game files in a folder listing, sorted case-insensitively."""
    return sorted((n for n in names if n.lower().endswith(VPX_SUFFIX)), key=str.lower)


def hidden_game_files(settings: dict | None) -> set[str]:
    """Filenames the user has hidden from the frontend.

    Hiding is a user decision, not a property of the artifact - a patch base is kept
    because the patched table cannot be rebuilt without it, and a variant is kept because
    someone may want it back. Neither is deleted; both simply stop being offered.
    """
    if not isinstance(settings, dict):
        return set()
    return {
        name for name, entry in settings.items()
        if isinstance(entry, dict) and entry.get("hidden") is True
    }


def visible_game_files(names: Iterable[str], settings: dict | None = None) -> list[str]:
    """The game files a frontend should offer. Each is independently launchable -
    several builds of one table (desktop, VR, a patched variant) are peers, not a
    primary with alternates."""
    hidden = hidden_game_files(settings)
    return [n for n in game_file_names(names) if n not in hidden]


def default_game_file(names: Iterable[str], folder_name: str = "", recorded: str = "") -> str:
    """Which build a single-game-file consumer gets, or "" when there are none.

    Not "the one to launch" - every visible game file is launchable, and the API lists
    them all. This is for the places that must pick exactly one: an export bundles one
    game, a table row shows one version, and every theme written so far assumes one
    table means one build.

    In order: an explicitly recorded choice, when it is actually present; then a build
    named after the folder; then the first by name. The last is deterministic rather
    than correct, for folders where nothing distinguishes the candidates - but
    deterministic is the point, since the alternative is directory order.
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
    """A default someone chose for this table, or "". Takes the vpinfe section itself,
    so this module stays out of what that section is called.

    Absent is the normal case and means "resolve from what is in the folder". It is
    written only by an explicit choice, and by the migration, which seeds it from
    VPXFile.filename so an existing table keeps selecting what it selects today.

    Deliberately not written on every rebuild: seeding it from whatever the resolver
    picked would freeze an arbitrary first choice with nothing to change it.
    """
    if not isinstance(vpinfe, dict):
        return ""
    return str(vpinfe.get(DEFAULT_GAME_FILE_KEY, "") or "").strip()
