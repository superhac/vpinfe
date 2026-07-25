"""Game files: the launchable artifacts inside a table folder.

A folder can hold several .vpx, so everything asks here which one is the table.
"""

from __future__ import annotations

from collections.abc import Iterable

VPX_SUFFIX = ".vpx"


def game_file_names(names: Iterable[str]) -> list[str]:
    """The game files in a folder listing, sorted case-insensitively."""
    return sorted((n for n in names if n.lower().endswith(VPX_SUFFIX)), key=str.lower)


def default_game_file(names: Iterable[str], folder_name: str = "", recorded: str = "") -> str:
    """Which game file to treat as the table, or "" when there are none.

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
