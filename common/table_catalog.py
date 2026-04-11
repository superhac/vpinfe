from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from common.table_scanner import scan_table_summaries
from common.table_scanner import scan_tables_root
from common.table_scanner import normalize_scan_depth


logger = logging.getLogger("vpinfe.table_catalog")


_CATALOG_LOCK = threading.Lock()
_TABLE_ROWS_CACHE: Optional[List[Dict[str, Any]]] = None
_MISSING_ROWS_CACHE: Optional[List[Dict[str, Any]]] = None


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


def clear_cached_catalog() -> None:
    with _CATALOG_LOCK:
        global _TABLE_ROWS_CACHE, _MISSING_ROWS_CACHE
        _TABLE_ROWS_CACHE = None
        _MISSING_ROWS_CACHE = None


def build_mobile_display_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    display_rows: List[Dict[str, str]] = []
    for row in rows:
        table_dir_name = row.get('table_dir_name') or row.get('filename') or ''
        if not table_dir_name:
            continue
        name = str(row.get('name') or table_dir_name).strip()
        if not name:
            continue
        manufacturer = str(row.get('manufacturer', '') or '').strip()
        year = str(row.get('year', '') or '').strip()
        parts = [part for part in (manufacturer, year) if part]
        display_name = f"{name} ({' '.join(parts)})" if parts else name
        display_rows.append({
            'display_name': display_name,
            'table_dir_name': table_dir_name,
        })
    return display_rows


def get_mobile_display_rows(tables_path: str, scan_depth: str = 'shallow') -> List[Dict[str, str]]:
    cached_rows = get_cached_table_rows()
    if cached_rows:
        return build_mobile_display_rows(cached_rows)
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