from __future__ import annotations

import os
import json
import concurrent.futures
import threading
import logging
import time
from dataclasses import dataclass
from typing import List, Set, Tuple, Dict, Any


logger = logging.getLogger("vpinfe.common.table_scanner")


@dataclass
class TableScanEntry:
    table_name: str
    table_dir: str
    info_path: str
    dir_contents: Set[str]
    pinmame_contents: Set[str]


_SCAN_STATE_LOCK = threading.Lock()
_SCAN_CACHE: Dict[Tuple[str, str], Tuple[float | None, List[TableScanEntry], List[Dict[str, str]]]] = {}
_SCAN_INFLIGHT: Dict[Tuple[str, str], threading.Event] = {}
_SUMMARY_CACHE: Dict[Tuple[str, str], Tuple[float | None, List[Dict[str, str]]]] = {}
_SUMMARY_INFLIGHT: Dict[Tuple[str, str], threading.Event] = {}


def normalize_scan_depth(value: str | None) -> str:
    lowered = str(value or '').strip().lower()
    return 'recursive' if lowered == 'recursive' else 'shallow'


def get_scan_depth_from_config(config: Any) -> str:
    """Read table scan depth from config and return normalized value."""
    try:
        value = config.get('Settings', 'tablescandepth', fallback='shallow')
    except Exception:
        value = 'shallow'
    return normalize_scan_depth(value)


def clear_scan_caches(tables_path: str | None = None) -> None:
    """Clear scanner caches globally or for a specific tables root path."""
    with _SCAN_STATE_LOCK:
        if not tables_path:
            _SCAN_CACHE.clear()
            _SUMMARY_CACHE.clear()
            return

        normalized_path = os.path.abspath(os.path.expanduser(tables_path))
        for cache_key in [k for k in _SCAN_CACHE.keys() if k[0] == normalized_path]:
            _SCAN_CACHE.pop(cache_key, None)
        for cache_key in [k for k in _SUMMARY_CACHE.keys() if k[0] == normalized_path]:
            _SUMMARY_CACHE.pop(cache_key, None)


def _get_root_mtime(tables_path: str) -> float | None:
    try:
        return os.path.getmtime(tables_path) if os.path.exists(tables_path) else None
    except Exception:
        return None


def _scan_tables_root_uncached(tables_path: str, max_workers: int = 8, scan_depth: str = 'shallow') -> Tuple[List[TableScanEntry], List[Dict[str, str]]]:
    """Perform a direct scan without reading/writing shared cache state."""
    if not os.path.exists(tables_path):
        return [], []

    scan_depth = normalize_scan_depth(scan_depth)
    if scan_depth == 'recursive':
        top_entries: List[Tuple[str, str]] = []
        try:
            for root, dirs, _ in os.walk(tables_path):
                for dirname in dirs:
                    top_entries.append((dirname, os.path.join(root, dirname)))
        except Exception:
            return [], []
    else:
        try:
            top_entries = [
                (entry.name, entry.path)
                for entry in os.scandir(tables_path)
                if entry.is_dir(follow_symlinks=False)
            ]
        except Exception:
            return [], []

    entries: List[TableScanEntry] = []
    missing: List[Dict[str, str]] = []

    def _process_table(table_name: str, table_dir: str):
        info_file = f"{table_name}.info"
        try:
            dir_contents = set(os.listdir(table_dir))
        except Exception:
            return None, None

        has_vpx = any(name.lower().endswith('.vpx') for name in dir_contents)
        if not has_vpx:
            return None, None

        if info_file not in dir_contents:
            return None, {'folder': table_name, 'path': table_dir}

        pinmame_contents: Set[str] = set()
        if 'pinmame' in dir_contents:
            try:
                pinmame_contents = set(os.listdir(os.path.join(table_dir, 'pinmame')))
            except Exception:
                pinmame_contents = set()

        return TableScanEntry(
            table_name=table_name,
            table_dir=table_dir,
            info_path=os.path.join(table_dir, info_file),
            dir_contents=dir_contents,
            pinmame_contents=pinmame_contents,
        ), None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_process_table, name, path): (name, path)
            for name, path in top_entries
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                entry, miss = future.result()
            except Exception:
                continue
            if entry is not None:
                entries.append(entry)
            if miss is not None:
                missing.append(miss)

    return entries, missing


def scan_tables_root(tables_path: str, max_workers: int = 8, scan_depth: str = 'shallow') -> Tuple[List[TableScanEntry], List[Dict[str, str]]]:
    """Scan table directories under tables_path.

    Optimizations:
    - Uses os.scandir for a shallow top-level directory list by default.
    - Supports optional recursive directory walk for nested table layouts.
    - Reads each table directory once (os.listdir) in parallel.
    - Returns reusable metadata so callers can avoid duplicate disk calls.

    Returns:
    - entries: table directories that have both a .vpx and <dirname>.info
    - missing: table directories that have .vpx but are missing <dirname>.info
    """
    normalized_path = os.path.abspath(os.path.expanduser(tables_path))
    normalized_depth = normalize_scan_depth(scan_depth)
    cache_key = (normalized_path, normalized_depth)
    current_mtime = _get_root_mtime(normalized_path)

    while True:
        with _SCAN_STATE_LOCK:
            cached = _SCAN_CACHE.get(cache_key)
            if cached is not None:
                cached_mtime, cached_entries, cached_missing = cached
                if cached_mtime == current_mtime:
                    return list(cached_entries), list(cached_missing)

            in_flight = _SCAN_INFLIGHT.get(cache_key)
            if in_flight is None:
                in_flight = threading.Event()
                _SCAN_INFLIGHT[cache_key] = in_flight
                should_scan = True
            else:
                should_scan = False

        if should_scan:
            try:
                start_time = time.time()
                logger.info("Disk %s scan starting...", normalized_depth)
                entries, missing = _scan_tables_root_uncached(
                    normalized_path,
                    max_workers=max_workers,
                    scan_depth=normalized_depth,
                )
                elapsed = time.time() - start_time
                logger.info(
                    "Disk %s scan finished in %.2fs (%d tables, %d missing)",
                    normalized_depth,
                    elapsed,
                    len(entries),
                    len(missing),
                )
                with _SCAN_STATE_LOCK:
                    _SCAN_CACHE[cache_key] = (current_mtime, entries, missing)
                return list(entries), list(missing)
            finally:
                with _SCAN_STATE_LOCK:
                    event = _SCAN_INFLIGHT.pop(cache_key, None)
                    if event is not None:
                        event.set()
        else:
            in_flight.wait()


def scan_table_summaries(tables_path: str, max_workers: int = 8, scan_depth: str = 'shallow') -> List[Dict[str, str]]:
    """Return cached table summaries (name/manufacturer/year/path) for mobile-style list views.

    This coalesces concurrent requests per root path and caches by root mtime.
    """
    normalized_path = os.path.abspath(os.path.expanduser(tables_path))
    normalized_depth = normalize_scan_depth(scan_depth)
    cache_key = (normalized_path, normalized_depth)
    current_mtime = _get_root_mtime(normalized_path)

    while True:
        with _SCAN_STATE_LOCK:
            cached = _SUMMARY_CACHE.get(cache_key)
            if cached is not None:
                cached_mtime, cached_rows = cached
                if cached_mtime == current_mtime:
                    return [dict(row) for row in cached_rows]

            in_flight = _SUMMARY_INFLIGHT.get(cache_key)
            if in_flight is None:
                in_flight = threading.Event()
                _SUMMARY_INFLIGHT[cache_key] = in_flight
                should_scan = True
            else:
                should_scan = False

        if should_scan:
            try:
                entries, _ = scan_tables_root(
                    normalized_path,
                    max_workers=max_workers,
                    scan_depth=normalized_depth,
                )

                def _parse_entry(entry: TableScanEntry):
                    try:
                        with open(entry.info_path, 'r', encoding='utf-8') as f:
                            raw = json.load(f)
                        info = raw.get('Info', {})
                        name = (info.get('Title') or entry.table_name).strip()
                        manufacturer = info.get('Manufacturer', '')
                        year = info.get('Year', '')
                        return {
                            'name': name,
                            'manufacturer': manufacturer,
                            'year': str(year) if year else '',
                            'table_dir_name': entry.table_name,
                            'table_path': entry.table_dir,
                        }
                    except Exception:
                        return None

                rows: List[Dict[str, str]] = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futures = [pool.submit(_parse_entry, entry) for entry in entries]
                    for future in concurrent.futures.as_completed(futures):
                        row = future.result()
                        if row is not None:
                            rows.append(row)

                rows.sort(key=lambda row: (row.get('name') or '').lower())
                with _SCAN_STATE_LOCK:
                    _SUMMARY_CACHE[cache_key] = (current_mtime, rows)
                return [dict(row) for row in rows]
            finally:
                with _SCAN_STATE_LOCK:
                    event = _SUMMARY_INFLIGHT.pop(cache_key, None)
                    if event is not None:
                        event.set()
        else:
            in_flight.wait()
