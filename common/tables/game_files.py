"""Game files: the launchable artifacts inside a table folder.

A folder can hold several .vpx, so everything asks here which one is the table.
"""

from __future__ import annotations

from collections.abc import Iterable

VPX_SUFFIX = ".vpx"

# Per-game-file settings live in the .info under this key, one entry per filename:
#
#   "GameFiles": { "Table (VR Room).vpx": { "hidden": true } }
#
# Absent means visible, so a library written by an older build behaves unchanged.
GAME_FILES_KEY = "GameFiles"


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
    """Which game file the table's METADATA is derived from, or "" when there are none.

    Not "the one to launch" - every visible game file is launchable. This picks the
    single file whose embedded version, authors and detect* flags describe the table,
    and which export uses when it has to choose one.

    In order: the one the .info records, when it is actually present - the metadata,
    media and any VPSdb match were built against that file; then one named after the
    folder; then the first by name. The last is deterministic rather than correct,
    for folders where nothing distinguishes the candidates - but deterministic is
    the point, since the alternative is directory order.
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
