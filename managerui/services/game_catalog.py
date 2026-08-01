from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from common.tables.metaconfig import VPINFE_SECTION
from managerui.services import game_index_service


def scan_mobile_games(reload: bool = False) -> List[Dict]:
    """Return the compact table shape used by the mobile transfer page."""
    tables = []
    for row in game_index_service.scan_rows(reload=reload):
        table_path = row.get("table_path", "")
        tables.append({
            "name": row.get("name", ""),
            "manufacturer": row.get("manufacturer", ""),
            "year": str(row.get("year", "") or ""),
            "table_dir_name": Path(table_path).name if table_path else "",
            "table_path": table_path,
            "vpinfe_id": row.get("vpinfe_id", ""),
        })
    return tables


def build_mobile_game_rows(tables: List[Dict]) -> List[Dict]:
    """Build mobile page display rows from scanned tables."""
    rows = []
    for game in tables:
        parts = [part for part in [game.get("manufacturer"), game.get("year")] if part]
        name = game.get("name", "")
        display = f"{name} ({' '.join(parts)})" if parts else name
        rows.append({
            "display_name": display,
            "table_dir_name": game.get("table_dir_name", ""),
            "vpinfe_id": game.get("vpinfe_id", ""),
        })
    return rows


def scan_launchable_games(games_path: str | None = None) -> List[Dict]:
    """Return launchable table rows from the shared table index."""
    tables = []
    for row in game_index_service.scan_rows(reload=False):
        table_path = row.get("table_path", "")
        filename = row.get("filename", "")
        if not table_path or not filename:
            continue
        vpx_path = str(Path(table_path) / filename)
        name = row.get("name", "")
        manufacturer = row.get("manufacturer", "")
        year = row.get("year", "")

        display_name = name
        if manufacturer and year:
            display_name = f"{name} ({manufacturer} {year})"
        elif manufacturer:
            display_name = f"{name} ({manufacturer})"
        elif year:
            display_name = f"{name} ({year})"

        tables.append({
            "name": name,
            "display_name": display_name,
            "vpx_path": vpx_path,
            "table_path": table_path,
            "vpsid": row.get("vpsid", ""),
            "vpinfe_id": row.get("vpinfe_id", ""),
            "manufacturer": manufacturer,
            "year": str(year) if year else "",
            "type": row.get("type", ""),
            "theme": row.get("theme") or row.get("themes", ""),
            "rating": row.get("rating", 0),
            "meta": {
                VPINFE_SECTION: {
                    "alt_launcher": row.get("alt_launcher", ""),
                    "plugin_profile": row.get("plugin_profile", ""),
                }
            },
        })

    tables.sort(key=lambda game: game["name"].lower())
    return tables
