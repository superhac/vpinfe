from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from common.table_repository import get_missing_tables, get_table_rows


@dataclass
class TableIndex:
    rows: List[Dict] = field(default_factory=list)
    missing_rows: List[Dict] = field(default_factory=list)
    by_path: Dict[str, Dict] = field(default_factory=dict)
    by_dir: Dict[str, Dict] = field(default_factory=dict)
    by_vpsid: Dict[str, Dict] = field(default_factory=dict)
    searchable: List[tuple[str, Dict]] = field(default_factory=list)


_index = TableIndex()
_loaded = False
_missing_loaded = False


def _normalize_path(path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return str(path)


def _build_index(rows: List[Dict], missing_rows: Optional[List[Dict]] = None) -> TableIndex:
    by_path = {}
    by_dir = {}
    by_vpsid = {}
    searchable = []

    for row in rows:
        table_path = row.get("table_path", "")
        normalized_path = _normalize_path(table_path)
        if normalized_path:
            by_path[normalized_path] = row
            by_dir[Path(normalized_path).name] = row

        vpsid = row.get("id") or row.get("vpsid")
        if vpsid:
            by_vpsid[str(vpsid)] = row

        search_blob = " ".join(
            str(row.get(key, "") or "")
            for key in ("name", "filename", "manufacturer", "year", "rom")
        ).lower()
        searchable.append((search_blob, row))

    return TableIndex(
        rows=rows,
        missing_rows=list(missing_rows if missing_rows is not None else _index.missing_rows),
        by_path=by_path,
        by_dir=by_dir,
        by_vpsid=by_vpsid,
        searchable=searchable,
    )


def set_rows(rows: List[Dict]) -> List[Dict]:
    global _index, _loaded
    _index = _build_index(list(rows))
    _loaded = True
    return _index.rows


def set_missing_rows(rows: List[Dict]) -> List[Dict]:
    global _index, _missing_loaded
    _index.missing_rows = list(rows)
    _missing_loaded = True
    return _index.missing_rows


def set_table_data(rows: List[Dict], missing_rows: List[Dict]) -> tuple[List[Dict], List[Dict]]:
    global _index, _loaded, _missing_loaded
    _index = _build_index(list(rows), list(missing_rows))
    _loaded = True
    _missing_loaded = True
    return _index.rows, _index.missing_rows


def invalidate() -> None:
    global _index, _loaded, _missing_loaded
    _index = TableIndex()
    _loaded = False
    _missing_loaded = False


def get_rows() -> Optional[List[Dict]]:
    return _index.rows if _loaded else None


def get_missing_rows() -> Optional[List[Dict]]:
    return _index.missing_rows if _missing_loaded else None


def scan_rows(reload: bool = False) -> List[Dict]:
    if reload or not _loaded:
        return set_rows(get_table_rows(reload=reload))
    return _index.rows


def scan_missing_rows(reload: bool = False) -> List[Dict]:
    if reload or not _missing_loaded:
        return set_missing_rows(get_missing_tables(reload=reload))
    return _index.missing_rows


def scan_table_data(reload: bool = False) -> tuple[List[Dict], List[Dict]]:
    rows = get_table_rows(reload=reload)
    missing_rows = get_missing_tables(reload=False)
    return set_table_data(rows, missing_rows)


def find_by_path(table_path: str) -> Optional[Dict]:
    return _index.by_path.get(_normalize_path(table_path))


def find_by_dir(table_dir: str) -> Optional[Dict]:
    return _index.by_dir.get(table_dir)


def find_by_vpsid(vpsid: str) -> Optional[Dict]:
    return _index.by_vpsid.get(str(vpsid))


def search_rows(term: str, *, limit: int = 20, rows: Optional[List[Dict]] = None) -> List[Dict]:
    term = (term or "").strip().lower()
    if not term:
        return []
    if rows is not None:
        searchable = [
            (" ".join(str(row.get(key, "") or "") for key in ("name", "filename", "manufacturer", "year", "rom")).lower(), row)
            for row in rows
        ]
    else:
        scan_rows(reload=False)
        searchable = _index.searchable
    return [row for blob, row in searchable if term in blob][:limit]


def update_row_by_path(table_path: str, updates: Dict) -> Optional[Dict]:
    row = find_by_path(table_path)
    if row is None:
        return None
    row.update(updates)
    set_rows(_index.rows)
    return row


def sync_collection_memberships(vpsid_collections_map: Dict[str, List[str]]) -> None:
    if not _loaded:
        return
    for row in _index.rows:
        vpsid = row.get("id", "")
        row["collections"] = vpsid_collections_map.get(vpsid, [])
    set_rows(_index.rows)


def add_collection_membership(vpsid: str, collection_name: str) -> None:
    row = find_by_vpsid(vpsid)
    if row is None:
        return
    row.setdefault("collections", [])
    if collection_name not in row["collections"]:
        row["collections"].append(collection_name)
