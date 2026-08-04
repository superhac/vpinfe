"""Find the media file behind /media/<table_id>/<kind>.

Addressed by table, because tier 1 of the resolution chain keys off the table that
launches - `(Wheel) <table>.png` beats `(Wheel) <folder>.png`. **The scan does not do
that per table yet**: it resolves once per game against the default table's stem, so
every table of a game currently answers with the same files, and a tier-1 file named
for a non-default table resolves nowhere at all.

The id in the URL is the table's regardless, so fixing the scan later does not move a
URL a theme has already built.
"""

from __future__ import annotations

from pathlib import Path

from common.games.game_metadata import normalize_meta
from common.games.tables import table_entries
from common.media_paths import MEDIA_SPECS

_ATTR_BY_KIND = {spec.key: spec.attr for spec in MEDIA_SPECS}


def resolved_kinds(game) -> list[str]:
    """The kinds this game has a file for, in spec order. Names, never paths."""
    return [kind for kind, attr in _ATTR_BY_KIND.items()
            if str(getattr(game, attr, "") or "").strip()]


def game_for_table(games, table_id: str):
    """The game that owns a table id, or None."""
    wanted = str(table_id or "").strip()
    if not wanted:
        return None
    for game in games:
        if wanted in table_entries(normalize_meta(getattr(game, "metaConfig", {}))):
            return game
    return None


def media_path(games, table_id: str, kind: str) -> Path | None:
    """The file behind /media/<table_id>/<kind>, or None if there is not one."""
    attr = _ATTR_BY_KIND.get(kind)
    if not attr:
        return None
    game = game_for_table(games, table_id)
    if game is None:
        return None
    resolved = str(getattr(game, attr, "") or "").strip()
    if not resolved:
        return None
    path = Path(resolved)
    return path if path.is_file() else None
