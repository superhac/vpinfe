"""The play lens: one resolved entry as a frontend reads it.

The forward half of the wire boundary. `wire_entry` rebuilds a game-like object from one
of these on a machine that does not hold the library; this is what it is rebuilt from.
"""

from __future__ import annotations

from common.extensions import contributions
from common.games import game_identity
from common.games.collection_resolver import Entry, visible_entries
from common.games.game_metadata import (
    game_rating,
    game_themes,
    game_title,
    play_record,
    table_descriptor,
)
from common.games.media_lookup import resolved_kinds
from common.shared_assets import manufacturer_logo_web_path
from common.timestamps import epoch_to_iso


def entry_resource(entry: Entry, group: str | None = None) -> dict:
    """One entry as REST serves it.

    `default` is computed, never read off the entry: it is the game's own choice and
    lives in the vpinfe section, not on the table. visible_entries puts it first.
    """
    game_ident = game_identity.game_id(entry.game)
    offered = visible_entries(entry.game)
    default_id = offered[0].get("id", "") if offered else ""
    meta = entry.game.meta_config or {}
    info = meta.get("Info") or {}
    vpinfe = meta.get("vpinfe") or {}
    prefix = f"/api/v1/games/{game_ident}"
    maker = str(info.get("Manufacturer", "") or "")
    return {
        "game": {
            "id": game_ident,
            "vps_id": str(info.get("VPSId", "") or ""),
            "name": game_title(entry.game),
            "manufacturer": maker,
            "year": str(info.get("Year", "") or ""),
            "type": str(info.get("Type", "") or ""),
            "themes": game_themes(entry.game),
            "dir_name": str(entry.game.game_dir_name or ""),
            "manufacturer_logo": manufacturer_logo_web_path(maker),
            "created_at": epoch_to_iso(getattr(entry.game, "creation_time", None)) or None,
            "rating": game_rating(entry.game),
            "user": play_record(meta),
            "ipdb_id": str(info.get("IPDBId", "") or ""),
            "tutorial": str(info.get("PinballPrimerTut", "") or ""),
            "overrides": {
                "alt_title": str(vpinfe.get("alt_title", "") or ""),
                "alt_vps_id": str(vpinfe.get("alt_vpsid", "") or ""),
                "frontend_dof_event": str(vpinfe.get("frontend_dof_event", "") or ""),
            },
        },
        "table": table_descriptor(entry.table, default_id=default_id),
        "siblings": entry.siblings,
        "assets": {
            "pup_pack": bool(entry.game.pup_pack_exists),
            "alt_color": bool(entry.game.alt_color_exists),
            "alt_sound": bool(entry.game.alt_sound_exists),
        },
        "media": resolved_kinds(entry.game),
        # None when the order has no groups; `group_by` on the list says which.
        "group": group,
        # What extensions have contributed. Here as well as in the theme payload
        # because this lens exists to be what a frontend on another machine is built
        # from, and one missing this renders a wheel with a badge short.
        "ext": contributions.held(game_ident),
        "links": {"game": prefix, "launch": f"{prefix}/launch",
                  "media": f"{prefix}/media"},
    }
