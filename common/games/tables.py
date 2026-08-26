"""Tables: the launchable artifacts inside a game folder.

A folder can hold several .vpx, so everything asks here which one is the default.
"""

from __future__ import annotations

from common.games import apps

from collections.abc import Iterable

from common.timestamps import iso_from_asctime, iso_from_authored_date

# Kept because callers outside this module still name it. Which extensions make a file
# a table is `apps.table_suffixes()` now - this is one app's, not the answer.
VPX_SUFFIX = ".vpx"

# One entry per .vpx, keyed by the table's id so a rename rewrites one field:
#
#   "tables": {
#     "9kRm2QvT8x": {"filename": "Table (VR Room).vpx", "version": "1.2", ...}
#   }
#
# A missing entry means a table nothing has parsed, and a missing `hidden` means visible.
TABLES_KEY = "tables"

# When the file behind an entry was first not found. Absent while the file is there.
# A timestamp rather than a bare flag because "gone for thirty seconds" and "gone for a
# week" are the same fact to a flag and different answers to a person - the first is
# almost always a share that has not mounted yet. Written by discovery, read by anyone
# deciding whether a table can be offered or acted on.
ABSENT_SINCE_KEY = "absent_since"

# Minted on the first rebuild that sees the file, and outlives its name - see
# `adopted_entry`, which is what carries it across a rename.
TABLE_ID_KEY = "id"
TABLE_FILENAME_KEY = "filename"

# Which table is the default, kept in the vpinfe section because it is a game-level
# choice rather than something a table says about itself.
DEFAULT_TABLE_KEY = "default_table"

# What a tables entry takes from a parse, in the parser's own names. The .vpx's
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
    """Authors as the .vpx records them. Per table, never rolled up to the game."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(a).strip() for a in value if str(a).strip()]
    return [a.strip() for a in str(value).split(",") if a.strip()]


def entry_from_parsed(parsed: dict | None) -> dict:
    """A tables entry from one VPXParser result.

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


def table_id(entry: dict | None) -> str:
    """An entry's id, or "" if it predates ids. Never mints."""
    if not isinstance(entry, dict):
        return ""
    return str(entry.get(TABLE_ID_KEY, "") or "").strip()


def adopted_entry(entries: dict, filename: str, file_hash: str,
                  seen: Iterable[str]) -> dict | None:
    """The prior entry this file should keep, matched by content when it was renamed.

    The hash says it is the same file; its recorded name being absent from this scan says
    it moved rather than that a copy was made beside it.
    """
    _, direct = entry_for_filename(entries, filename)
    if direct:
        return direct
    if not file_hash:
        return None

    seen = set(seen)
    for entry in entries.values():
        if not isinstance(entry, dict) or entry_filename(entry) in seen:
            continue
        if entry.get("file_hash") == file_hash:
            return entry
    return None


def is_parsed(entry: dict | None) -> bool:
    """Whether an entry describes a table we have read, rather than one we only
    recorded something about - hidden, or where it came from. Reading those as parsed
    answers "no rom declared" for a file nothing has opened.
    """
    if not isinstance(entry, dict):
        return False
    return any(key in entry for key in PARSED_KEYS)


def table_names(names: Iterable[str]) -> list[str]:
    """The tables in a folder listing, sorted case-insensitively."""
    known = apps.table_suffixes()
    return sorted((n for n in names if n.lower().endswith(known)), key=str.lower)


def entry_filename(entry: dict | None) -> str:
    """The .vpx an entry describes, or ""."""
    if not isinstance(entry, dict):
        return ""
    return str(entry.get(TABLE_FILENAME_KEY, "") or "").strip()


def entry_for_filename(entries: dict | None, filename: str) -> tuple[str, dict]:
    """(id, entry) for the table with this filename, or ("", {}). Callers arrive holding
    a name off a directory listing; the storage is keyed by id."""
    for found_id, entry in (entries or {}).items():
        if entry_filename(entry) == filename:
            return found_id, entry
    return "", {}


def table_filenames(entries: dict | None) -> list[str]:
    """Every .vpx the entries describe. What `default_table` and the disk both speak."""
    return [n for n in (entry_filename(e) for e in (entries or {}).values()) if n]


def rekey_by_id(entries: dict | None) -> dict:
    """The tables map keyed by id, converting the filename-keyed shape on the way.

    An entry with no `filename` predates the re-key and its key is the name. One with no
    id yet keeps that name as its key until the minting pass assigns one - dropping it
    would destroy the `hidden` and play stats the id exists to protect.
    """
    if not isinstance(entries, dict):
        return {}
    # Callers test identity to mean "nothing to convert", so an empty map belongs here
    # too: a game with no .vpx would otherwise be rewritten on every startup.
    if all(isinstance(e, dict) and TABLE_FILENAME_KEY in e for e in entries.values()):
        return entries

    rekeyed = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            continue    # not a record; there is nothing to address or carry
        entry = dict(entry)
        entry.setdefault(TABLE_FILENAME_KEY, key)
        rekeyed[table_id(entry) or key] = entry
    return rekeyed


def hidden_tables(entries: dict | None) -> set[str]:
    """Filenames the user has hidden - never ids, because the caller is comparing against
    a folder listing. Hiding never deletes; a patch base has to stay on disk."""
    return {
        name for name in (entry_filename(entry)
                          for entry in rekey_by_id(entries).values()
                          if isinstance(entry, dict) and entry.get("hidden") is True)
        if name
    }


def visible_tables(names: Iterable[str], settings: dict | None = None) -> list[str]:
    """The tables a frontend should offer. Each is independently launchable: several
    tables of one game are peers, not a primary with alternates."""
    hidden = hidden_tables(settings)
    return [n for n in table_names(names) if n not in hidden]


def default_table(names: Iterable[str], folder_name: str = "", recorded: str = "") -> str:
    """Which table a single-table consumer gets, or "" when there are none.

    Not "the one to launch" - every visible table is launchable. This is for the
    places that must pick exactly one: an export, a game row, any theme written so far.

    Falling through to the first by name is deterministic rather than correct, which is
    the point: the alternative is directory order.
    """
    candidates = table_names(names)
    if not candidates:
        return ""

    recorded = (recorded or "").strip()
    if recorded in candidates:
        return recorded

    stem = (folder_name or "").strip().lower()
    if stem:
        for name in candidates:
            if apps.strip_suffix(name).lower() == stem:
                return name

    return candidates[0]


def table_entries(meta: dict | None) -> dict:
    """The tables section keyed by id, or {}. Normalizes the pre-re-key shape on the way
    out, so a reader sees the current shape whether or not the file has been rewritten -
    only `table_identity.ensure_unique_table_ids` persists the conversion."""
    if not isinstance(meta, dict):
        return {}
    entries = meta.get(TABLES_KEY)
    return rekey_by_id(entries) if isinstance(entries, dict) else {}


def recorded_default(vpinfe: dict | None, entries: dict | None = None) -> str:
    """The filename of the default someone chose for this game, or "".

    Stored as a table id so the choice survives a rename; resolved to a name here
    because every caller is about to match it against a folder listing. A value that
    is not a known id is read as a filename - that is what the 2.x migration seeds,
    and what a hand-edited .info is likely to hold.

    Absent is the normal case and means "resolve from what is in the folder" - it is
    never written on a rebuild, which would freeze an arbitrary pick as a choice.
    """
    if not isinstance(vpinfe, dict):
        return ""
    recorded = str(vpinfe.get(DEFAULT_TABLE_KEY, "") or "").strip()
    if not recorded:
        return ""
    entry = (entries or {}).get(recorded)
    return entry_filename(entry) if isinstance(entry, dict) else recorded
