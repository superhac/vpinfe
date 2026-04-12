from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from common.table_scanner import scan_table_summaries
from common.table_scanner import scan_tables_root
from common.table_scanner import normalize_scan_depth
from common.vpxcollections import VPXCollections


logger = logging.getLogger("vpinfe.table_catalog")


_CATALOG_LOCK = threading.Lock()
_TABLE_ROWS_CACHE: Optional[List[Dict[str, Any]]] = None
_MISSING_ROWS_CACHE: Optional[List[Dict[str, Any]]] = None
_CATALOG_SCAN_CONDITION = threading.Condition()
_CATALOG_SCAN_IN_PROGRESS = False


def get_cached_table_rows() -> Optional[List[Dict[str, Any]]]:
    with _CATALOG_LOCK:
        return _TABLE_ROWS_CACHE


def get_cached_missing_rows() -> Optional[List[Dict[str, Any]]]:
    with _CATALOG_LOCK:
        return _MISSING_ROWS_CACHE


def set_cached_catalog(table_rows: List[Dict[str, Any]], missing_rows: List[Dict[str, Any]]) -> None:
    with _CATALOG_LOCK:
        global _TABLE_ROWS_CACHE, _MISSING_ROWS_CACHE
        _TABLE_ROWS_CACHE = table_rows
        _MISSING_ROWS_CACHE = missing_rows
    logger.debug(
        "Catalog cache set: table_rows=%d missing_rows=%d",
        len(table_rows),
        len(missing_rows),
    )


def clear_cached_catalog() -> None:
    with _CATALOG_LOCK:
        global _TABLE_ROWS_CACHE, _MISSING_ROWS_CACHE
        prev_tables = 0 if _TABLE_ROWS_CACHE is None else len(_TABLE_ROWS_CACHE)
        prev_missing = 0 if _MISSING_ROWS_CACHE is None else len(_MISSING_ROWS_CACHE)
        _TABLE_ROWS_CACHE = None
        _MISSING_ROWS_CACHE = None
    logger.debug(
        "Catalog cache cleared: previous_table_rows=%d previous_missing_rows=%d",
        prev_tables,
        prev_missing,
    )


def build_vpsid_collections_map(collections_path: str) -> Dict[str, List[str]]:
    """Build a map of VPS ID -> collection names for non-filter collections."""
    vpsid_to_collections: Dict[str, List[str]] = {}
    try:
        collections = VPXCollections(collections_path)
        for collection_name in collections.get_collections_name():
            if collections.is_filter_based(collection_name):
                continue
            try:
                for vpsid in collections.get_vpsids(collection_name):
                    if vpsid not in vpsid_to_collections:
                        vpsid_to_collections[vpsid] = []
                    vpsid_to_collections[vpsid].append(collection_name)
            except Exception:
                pass
    except Exception:
        pass
    return vpsid_to_collections


def sync_catalog_collections(collections_path: str) -> None:
    """Update cached table rows with collection memberships from disk."""
    with _CATALOG_LOCK:
        table_rows = _TABLE_ROWS_CACHE

    if table_rows is None:
        logger.debug("Catalog collection sync skipped: table cache is empty")
        return

    vpsid_collections_map = build_vpsid_collections_map(collections_path)
    for row in table_rows:
        row['collections'] = vpsid_collections_map.get(row.get('id', ''), [])

    logger.debug(
        "Catalog collection sync complete: rows=%d mapped_vpsids=%d",
        len(table_rows),
        len(vpsid_collections_map),
    )


def ensure_catalog_loaded(
    tables_path: str,
    collections_path: str,
    scan_depth: str = 'shallow',
    force_refresh: bool = False,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return catalog rows, populating the shared cache on demand.

    When a scan is already in progress, concurrent callers wait for the active
    scan to finish and then reuse the populated cache.
    """
    global _CATALOG_SCAN_IN_PROGRESS

    with _CATALOG_LOCK:
        cached_table_rows = _TABLE_ROWS_CACHE
        cached_missing_rows = _MISSING_ROWS_CACHE

    if not force_refresh and cached_table_rows is not None and cached_missing_rows is not None:
        return cached_table_rows, cached_missing_rows

    if not os.path.exists(tables_path):
        set_cached_catalog([], [])
        return [], []

    with _CATALOG_SCAN_CONDITION:
        if _CATALOG_SCAN_IN_PROGRESS:
            while _CATALOG_SCAN_IN_PROGRESS:
                _CATALOG_SCAN_CONDITION.wait()
            with _CATALOG_LOCK:
                cached_table_rows = _TABLE_ROWS_CACHE
                cached_missing_rows = _MISSING_ROWS_CACHE
            if cached_table_rows is not None and cached_missing_rows is not None:
                return cached_table_rows, cached_missing_rows
        _CATALOG_SCAN_IN_PROGRESS = True

    try:
        result = scan_installed_and_missing_tables(
            tables_path,
            build_vpsid_collections_map(collections_path),
            scan_depth=scan_depth,
        )
        set_cached_catalog(*result)
        return result
    finally:
        with _CATALOG_SCAN_CONDITION:
            _CATALOG_SCAN_IN_PROGRESS = False
            _CATALOG_SCAN_CONDITION.notify_all()


def format_table_display_name(name: str, manufacturer: str = '', year: str = '') -> str:
    parts = [part for part in (str(manufacturer or '').strip(), str(year or '').strip()) if part]
    base = str(name or '').strip()
    return f"{base} ({' '.join(parts)})" if parts else base


def build_mobile_display_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    display_rows: List[Dict[str, str]] = []
    for row in rows:
        table_dir_name = row.get('table_dir_name') or row.get('filename') or ''
        if not table_dir_name:
            continue
        name = str(row.get('name') or table_dir_name).strip()
        if not name:
            continue
        manufacturer = row.get('manufacturer', '')
        year = row.get('year', '')
        display_name = format_table_display_name(name, manufacturer, year)
        display_rows.append({
            'display_name': display_name,
            'table_dir_name': table_dir_name,
        })
    return display_rows


def get_mobile_display_rows(tables_path: str, scan_depth: str = 'shallow') -> List[Dict[str, str]]:
    cached_rows = get_cached_table_rows()
    if cached_rows:
        logger.debug("Mobile display rows from catalog cache: rows=%d", len(cached_rows))
        return build_mobile_display_rows(cached_rows)
    logger.debug("Mobile display rows from scanner summaries: path=%s depth=%s", tables_path, scan_depth)
    return build_mobile_display_rows(
        scan_table_summaries(
            tables_path,
            scan_depth=normalize_scan_depth(scan_depth),
        )
    )


def normalize_table_rating(value) -> int:
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        normalized = 0
    return max(0, min(5, normalized))


def parse_table_info(info_path: str, dir_contents=None, pinmame_contents=None) -> Dict[str, Any]:
    try:
        with open(info_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        table_dir = os.path.dirname(info_path)
        table_name = os.path.basename(table_dir)

        info = raw.get('Info', {})
        vpx = raw.get('VPXFile', {})
        user = raw.get('User', {})
        vpinfe = raw.get('VPinFE', {})

        def get(*paths, default=""):
            for section, key in paths:
                src = {'Info': info, 'VPXFile': vpx, 'User': user, 'VPinFE': vpinfe, 'root': raw}.get(section)
                if src and key in src and src[key] not in ('', None):
                    return src[key]
            return default

        if dir_contents is None:
            try:
                dir_contents = set(os.listdir(table_dir))
            except Exception:
                dir_contents = set()
        if pinmame_contents is None:
            try:
                pinmame_dir = os.path.join(table_dir, 'pinmame')
                pinmame_contents = set(os.listdir(pinmame_dir)) if 'pinmame' in dir_contents else set()
            except Exception:
                pinmame_contents = set()

        return {
            'name': (get(('VPinFE', 'alttitle'), ('Info', 'Title'), ('root', 'name'), default=table_name) or '').strip(),
            'filename': get(('VPXFile', 'filename'), default=f'{table_name}.vpx'),
            'vpsid': get(('Info', 'VPSId'), ('root', 'id')),
            'id': get(('VPinFE', 'altvpsid'), ('Info', 'VPSId'), ('root', 'id')),
            'ipdb_id': get(('Info', 'IPDBId')),
            'manufacturer': get(('Info', 'Manufacturer'), ('VPXFile', 'manufacturer')),
            'year': get(('Info', 'Year'), ('VPXFile', 'year')),
            'type': get(('Info', 'Type'), ('VPXFile', 'type')),
            'themes': get(('Info', 'Themes'), default=[]),
            'authors': get(('Info', 'Authors'), default=[]),
            'rom': get(('VPXFile', 'rom'), ('Info', 'Rom')),
            'version': get(('VPXFile', 'version')),
            'filehash': get(('VPXFile', 'filehash')),
            'vbshash': get(('VPXFile', 'vbsHash')),
            'detectnfozzy': get(('VPXFile', 'detectnfozzy')),
            'detectfleep': get(('VPXFile', 'detectfleep')),
            'detectssf': get(('VPXFile', 'detectssf')),
            'detectlut': get(('VPXFile', 'detectlut')),
            'detectscorebit': get(('VPXFile', 'detectscorebit')),
            'detectfastflips': get(('VPXFile', 'detectfastflips')),
            'detectflex': get(('VPXFile', 'detectflex')),
            'patch_applied': get(('VPXFile', 'patch_applied'), default=False),
            'table_path': table_dir,
            'pup_pack_exists': 'pupvideos' in dir_contents,
            'serum_exists': 'serum' in dir_contents,
            'vni_exists': 'vni' in dir_contents,
            'alt_sound_exists': 'altsound' in pinmame_contents,
            'delete_nvram_on_close': vpinfe.get('deletedNVRamOnClose', False),
            'altlauncher': (vpinfe.get('altlauncher', '') or '').strip(),
            'alttitle': (vpinfe.get('alttitle', '') or '').strip(),
            'altvpsid': (vpinfe.get('altvpsid', '') or '').strip(),
            'frontend_dof_event': (user.get('FrontendDOFEvent', '') or '').strip(),
            'rating': normalize_table_rating(user.get('Rating', 0)),
        }
    except Exception as e:
        logger.error('Error reading %s: %s', info_path, e)
        return {}


def scan_installed_and_missing_tables(
    tables_path: str,
    vpsid_collections_map: Optional[Dict[str, List[str]]] = None,
    scan_depth: str = 'shallow',
) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    if not os.path.exists(tables_path):
        return [], []

    vpsid_collections_map = vpsid_collections_map or {}
    rows: List[Dict[str, Any]] = []
    entries, missing = scan_tables_root(
        tables_path,
        scan_depth=normalize_scan_depth(scan_depth),
    )

    for entry in entries:
        data = parse_table_info(
            entry.info_path,
            dir_contents=entry.dir_contents,
            pinmame_contents=entry.pinmame_contents,
        )
        if data:
            data['table_path'] = entry.table_dir
            data['collections'] = vpsid_collections_map.get(data.get('id', ''), [])
            rows.append(data)

    return rows, missing