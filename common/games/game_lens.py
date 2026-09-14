"""One game answered as a resource: identity, overrides, and what its folder holds.

The catalog row is what the last scan recorded. This is that row turned into the shape
every surface reads, plus an inventory that is recomputed per call - an audit reporting
yesterday's folder is worse than none.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common.games import asset_resolver
from common.games.tables import table_names


def parked_match(row: dict) -> dict | None:
    """A superseded manual match, for the surface that offers it back."""
    parked = row.get("alt_vpsid_previous")
    if not isinstance(parked, dict) or not str(parked.get("value") or "").strip():
        return None
    return {"value": str(parked["value"]).strip(),
            "table": str(parked.get("table") or ""),
            "set_aside": str(parked.get("set_aside") or "")}


def asset_summary(row: dict) -> dict:
    """Presence per kind, as objects so a kind can grow attributes without a
    breaking change. alt_color keeps its formats - the flat boolean lost them."""
    formats = [name for name, flag in (("serum", "serum_exists"), ("vni", "vni_exists"))
               if row.get(flag)]
    return {
        "backglass": {"present": bool(row.get("b2s_exists"))},
        # `ini`, not `settings`: console has a Settings section, and one word for a
        # nav destination and a file kind is two things sharing a name.
        "ini": {"present": bool(row.get("ini_exists"))},
        "pup_pack": {"present": bool(row.get("pup_pack_exists"))},
        "alt_color": {"present": bool(formats), "formats": formats},
        "alt_sound": {"present": bool(row.get("alt_sound_exists"))},
        "music": {"present": bool(row.get("music_exists"))},
    }


def inventory_assets(game_dir: Path) -> dict:
    """Every asset file in the folder attributed, plus the folder-wide kinds.

    Computed fresh, not from the scan - an audit that reports yesterday's folder is
    worse than none.
    """
    files, subdirs = asset_resolver.folder_listing(game_dir)
    inv = asset_resolver.inventory(game_dir.name, files, table_names(files))
    for entry in inv.values():
        entry["present"] = bool(entry["files"])
    subdir_set = {name.lower() for name in subdirs}
    formats = [fmt for fmt, folder in (("serum", "serum"), ("vni", "vni"))
               if folder in subdir_set]
    inv["pup_pack"] = {"present": "pupvideos" in subdir_set}
    inv["alt_color"] = {"present": bool(formats), "formats": formats}
    inv["alt_sound"] = {"present": (game_dir / "pinmame" / "altsound").is_dir()}
    inv["music"] = {"present": "music" in subdir_set}
    return inv


def game_resource(row: dict, game_id: str) -> dict[str, Any]:
    """One game as a client reads it, from the row a scan produced."""
    prefix = f"/api/v1/games/{game_id}"
    return {
        "id": game_id,
        # Correlation with VPSdb, VPinPlay and the like - not this table's identity.
        # The effective id, not the discovered one: `alt_vpsid` is somebody saying the
        # match was wrong, and every other field here is already the value in force -
        # `name` is the alt title the moment one is set. `discovered` below is what an
        # undo reverts to, and is the only place the superseded id belongs.
        "vps_id": row.get("alt_vpsid", "") or row.get("vpsid", ""),
        "name": row.get("name", ""),
        "manufacturer": row.get("manufacturer", ""),
        "year": str(row.get("year") or ""),
        "type": row.get("type", ""),
        "themes": row.get("themes") or [],
        "authors": row.get("authors") or [],
        "rom": row.get("rom", ""),
        "version": row.get("version", ""),
        # How many tables this game offers, so a client can tell a row that collapses
        # six from one that collapses one. `rom` and `version` above are read off the
        # default table; this is what says whether there was a choice to make.
        "table_count": int(row.get("table_count") or 0),
        "rating": row.get("rating", 0),
        "collections": row.get("collections") or [],
        "folder": str(row.get("game_dir", "") or ""),
        "overrides": {
            "alt_title": row.get("alt_title", ""),
            "alt_vps_id": row.get("alt_vpsid", ""),
            "frontend_dof_event": row.get("frontend_dof_event", ""),
        },
        # Surfacing it, never resolving through it: `tests/invariants/test_parked_override`
        # asserts the difference, and this file is on its allowlist for that reason.
        "parked_vps_id": parked_match(row),
        "discovered": {
            "name": row.get("found_name", ""),
            "vps_id": row.get("vpsid", ""),
        },
        # Assets, not media: these are what the game needs to play as intended.
        # Media is the artwork VPinFE shows while browsing - see docs/conventions.md.
        # Summary from the scan; the detail endpoint recomputes and attributes files.
        "assets": asset_summary(row),
        "user": row.get("user") or {},
        "links": {
            "self": prefix,
            "tables": f"{prefix}/tables",
            "media": f"{prefix}/media",
            "archive": f"{prefix}/archive",
            "launch": f"{prefix}/launch",
            "rating": f"{prefix}/rating",
        },
    }
