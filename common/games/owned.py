from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from common.games import game_identity, game_repository
from common.games.game_metadata import game_title, game_vps_id, normalize_meta
from common.games.tables import table_entries


def owned(vps_ids: Iterable[Any]) -> dict[str, Any]:
    wanted = {str(one or "").strip() for one in vps_ids} - {""}
    found: dict[str, dict[str, str]] = {}
    if not wanted:
        return {"owned": found}
    for game in game_repository.all_games():
        game_id = game_identity.game_id(game)
        name = game_title(game)
        entry = game_vps_id(game)
        if entry in wanted and entry not in found:
            found[entry] = {"game_id": game_id, "table_id": "", "name": name}
        for key, table in table_entries(normalize_meta(game.meta_config)).items():
            source = table.get("source") if isinstance(table, dict) else None
            release = str((source or {}).get("vps_file_id") or "").strip()
            if release in wanted and release not in found:
                found[release] = {"game_id": game_id, "table_id": str(key), "name": name}
    return {"owned": found}
