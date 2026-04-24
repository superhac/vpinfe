from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from managerui.services import table_index_service


def scan_mobile_tables(reload: bool = False) -> List[Dict]:
    """Return the compact table shape used by the mobile transfer page."""
    tables = []
    for row in table_index_service.scan_rows(reload=reload):
        table_path = row.get("table_path", "")
        tables.append({
            "name": row.get("name", ""),
            "manufacturer": row.get("manufacturer", ""),
            "year": str(row.get("year", "") or ""),
            "table_dir_name": Path(table_path).name if table_path else "",
            "table_path": table_path,
        })
    return tables


def build_mobile_table_rows(tables: List[Dict]) -> List[Dict]:
    """Build mobile page display rows from scanned tables."""
    rows = []
    for table in tables:
        parts = [part for part in [table.get("manufacturer"), table.get("year")] if part]
        name = table.get("name", "")
        display = f"{name} ({' '.join(parts)})" if parts else name
        rows.append({
            "display_name": display,
            "table_dir_name": table.get("table_dir_name", ""),
        })
    return rows


def scan_launchable_tables(tables_path: str | None = None) -> List[Dict]:
    """Return launchable table rows from the shared table index."""
    tables = []
    for row in table_index_service.scan_rows(reload=False):
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
            "vpsid": row.get("id") or row.get("vpsid", ""),
            "manufacturer": manufacturer,
            "year": str(year) if year else "",
            "type": row.get("type", ""),
            "theme": row.get("theme") or row.get("themes", ""),
            "rating": row.get("rating", 0),
            "meta": {"VPinFE": {"altlauncher": row.get("altlauncher", "")}},
        })

    tables.sort(key=lambda table: table["name"].lower())
    return tables
