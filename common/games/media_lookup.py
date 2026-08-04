"""Find a game's resolved media file from its id, for the frontend's /media route.

Media resolves during the scan, so the game already holds the answer: this is a lookup,
not a second resolution.
"""

from __future__ import annotations

from pathlib import Path

from common.games import game_identity
from common.media_paths import MEDIA_SPECS

_ATTR_BY_KIND = {spec.key: spec.attr for spec in MEDIA_SPECS}


def resolved_kinds(game) -> list[str]:
    """The kinds this game has a file for, in spec order. Names, never paths."""
    return [kind for kind, attr in _ATTR_BY_KIND.items()
            if str(getattr(game, attr, "") or "").strip()]


def media_path(games, game_id: str, kind: str) -> Path | None:
    """The file behind /media/<game_id>/<kind>, or None if there is not one."""
    attr = _ATTR_BY_KIND.get(kind)
    if not attr:
        return None
    game = game_identity.find_by_id(games, game_id)
    if game is None:
        return None
    resolved = str(getattr(game, attr, "") or "").strip()
    if not resolved:
        return None
    path = Path(resolved)
    return path if path.is_file() else None
