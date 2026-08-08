"""Find the media file behind /media/<table_id>/<kind>.

Addressed by table because tier 1 of the chain keys off the table that launches, though
the scan still resolves once per game - so every table of a game answers the same today.
Keeping the table's id in the URL means fixing that does not move a URL a theme built.
"""

from __future__ import annotations

from pathlib import Path

from common.games import game_identity
from common.games.game_metadata import normalize_meta
from common.games.tables import table_entries
from common.media_specs import MEDIA_SPECS, canonical_kind

_ATTR_BY_KIND = {spec.key: spec.attr for spec in MEDIA_SPECS}


def resolved_kinds(game) -> list[str]:
    """The kinds this game has a file for, in spec order. Names, never paths."""
    return [kind for kind, attr in _ATTR_BY_KIND.items()
            if str(getattr(game, attr, "") or "").strip()]


def game_for_table(games, table_id: str):
    """The game that owns a table id, or the game with that id.

    A folder no build has touched has no table ids yet but still has art, so its entry
    addresses media by the game's id.
    """
    wanted = str(table_id or "").strip()
    if not wanted:
        return None
    for game in games:
        if wanted in table_entries(normalize_meta(getattr(game, "meta_config", {}))):
            return game
    return game_identity.find_by_id(games, wanted)


def media_path(games, table_id: str, kind: str) -> Path | None:
    """The file behind /media/<table_id>/<kind>, or None if there is not one."""
    # A theme built against an older kind name still addresses media by it.
    attr = _ATTR_BY_KIND.get(canonical_kind(kind))
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
