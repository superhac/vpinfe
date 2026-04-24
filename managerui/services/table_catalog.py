from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from common.table_repository import get_table_rows

from managerui.paths import get_tables_path
from managerui.services.table_service import normalize_table_rating


def scan_mobile_tables(reload: bool = False) -> List[Dict]:
    """Return the compact table shape used by the mobile transfer page."""
    tables = []
    for row in get_table_rows(reload=reload):
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
    """Scan table folders for entries with both .info metadata and a .vpx file."""
    root_path = Path(tables_path or get_tables_path()).expanduser()
    tables = []

    if not root_path.exists():
        return tables

    for root_name, _, files in os.walk(root_path):
        root = Path(root_name)
        current_dir = root.name
        info_file = f"{current_dir}.info"

        if info_file not in files:
            continue

        vpx_files = [filename for filename in files if filename.lower().endswith(".vpx")]
        if not vpx_files:
            continue

        meta_path = root / info_file
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        info = raw.get("Info", {})
        user = raw.get("User", {})
        vpinfe = raw.get("VPinFE", {})
        name = (info.get("Title") or current_dir).strip()
        manufacturer = info.get("Manufacturer", "")
        year = info.get("Year", "")

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
            "vpx_path": str(root / vpx_files[0]),
            "table_path": str(root),
            "vpsid": info.get("VPSId", ""),
            "manufacturer": manufacturer,
            "year": str(year) if year else "",
            "type": info.get("Type", ""),
            "theme": info.get("Theme", ""),
            "rating": normalize_table_rating(user.get("Rating", 0)),
            "meta": {"VPinFE": vpinfe},
        })

    tables.sort(key=lambda table: table["name"].lower())
    return tables
