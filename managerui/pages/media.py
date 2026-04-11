import os
import logging
import asyncio
import shutil
import concurrent.futures
from urllib.parse import quote
from nicegui import ui, events, run, app, context
from pathlib import Path
import json
from typing import List, Dict, Optional, Any
from platformdirs import user_config_dir

# Resolve project root and important paths explicitly
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
VPINFE_INI_PATH = CONFIG_DIR / 'vpinfe.ini'

from common.iniconfig import IniConfig, get_tables_root_from_config
from common.metaconfig import MetaConfig
from common.table_scanner import get_scan_depth_from_config
from common.table_scanner import scan_tables_root
from .scroll_state import capture_scroll_state as capture_page_scroll_state
from .scroll_state import restore_scroll_state as restore_page_scroll_state
from .scroll_state import default_scroll_state
_INI_CFG = IniConfig(str(VPINFE_INI_PATH))

logger = logging.getLogger("vpinfe.manager.media")

# Cache for scanned media data (persists across page visits)
_media_cache: Optional[List[Dict]] = None
_thumb_route_registered = False
_media_pagination_state: Dict[str, Any] = {
    'page': 1,
    'rowsPerPage': 100,
    'sortBy': 'name',
    'descending': False,
}
_media_scroll_state: Dict[str, Any] = default_scroll_state()
_media_page_client: Any = None
_media_filter_state: Dict[str, Any] = {
    'search': '',
    'manufacturer': 'All',
    'year': 'All',
    'theme': 'All',
    'table_type': 'All',
    'missing_bg': False,
    'missing_dmd': False,
    'missing_table': False,
    'missing_fss': False,
    'missing_wheel': False,
    'missing_cab': False,
    'missing_realdmd': False,
    'missing_realdmd_color': False,
    'missing_flyer': False,
    'missing_table_video': False,
    'missing_bg_video': False,
    'missing_dmd_video': False,
    'missing_audio': False,
}


def _load_persisted_rows_per_page() -> int:
    try:
        stored = app.storage.user.get('media_pagination_state', {}) or {}
        value = stored.get('rowsPerPage', 100)
        value = int(value) if value is not None else 100
        result = value if value >= 0 else 100
        return result
    except Exception as e:
        logger.error(f"Error loading media_rows_per_page: {e}")
        return 100


def _save_persisted_rows_per_page(rows_per_page: int) -> None:
    try:
        stored = dict(app.storage.user.get('media_pagination_state', {}) or {})
        stored['rowsPerPage'] = rows_per_page
        app.storage.user['media_pagination_state'] = stored
    except Exception as e:
        logger.error(f"Error saving media_rows_per_page={rows_per_page}: {e}")


async def capture_scroll_state() -> None:
    global _media_scroll_state, _media_page_client
    _media_scroll_state = await capture_page_scroll_state(
        _media_page_client,
        '.media-main-table .q-table__middle',
    )


def get_scroll_state() -> Dict[str, Any]:
    return dict(_media_scroll_state)

CACHE_DIR = CONFIG_DIR / "cache"
THUMB_CACHE_ROOT = CACHE_DIR / "media_thumbs"
THUMB_SIZE = (512, 512)
THUMB_WARM_ROW_BATCH_SIZE = 25
THUMB_WARM_CHUNK_SIZE = 8


def invalidate_media_cache():
    """Reset the media cache so the next page visit triggers a fresh scan."""
    global _media_cache
    _media_cache = None
# Track whether we've registered the media files route
_media_route_registered = False

# Media types and their display info
MEDIA_TYPES = [
    ('bg', 'BG', 'bg.png'),
    ('dmd', 'DMD', 'dmd.png'),
    ('table', 'Table', 'table.png'),
    ('fss', 'FSS', 'fss.png'),
    ('wheel', 'Wheel', 'wheel.png'),
    ('cab', 'Cab', 'cab.png'),
    ('realdmd', 'Real DMD', 'realdmd.png'),
    ('realdmd_color', 'Real DMD Color', 'realdmd-color.png'),
    ('flyer', 'Flyer', 'flyer.png'),
    ('table_video', 'Table Video', 'table.mp4'),
    ('bg_video', 'BG Video', 'bg.mp4'),
    ('dmd_video', 'DMD Video', 'dmd.mp4'),
    ('audio', 'Audio', 'audio.mp3'),
]
MEDIA_KEY_TO_FILENAME = {key: fname for key, _, fname in MEDIA_TYPES}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}
IMAGE_MEDIA_KEYS = [
    key for key, _, filename in MEDIA_TYPES
    if Path(filename).suffix.lower() in IMAGE_EXTENSIONS
]


def _media_url(*parts: str) -> str:
    encoded = [quote(p.strip('/')) for p in parts if p]
    return '/' + '/'.join(encoded)


def _is_image_media_key(media_key: str) -> bool:
    filename = MEDIA_KEY_TO_FILENAME.get(media_key, '')
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def _source_media_path(table_path: str, media_key: str) -> Optional[str]:
    filename = MEDIA_KEY_TO_FILENAME.get(media_key)
    if not filename:
        return None
    medias_path = os.path.join(table_path, 'medias', filename)
    if os.path.exists(medias_path):
        return medias_path
    root_path = os.path.join(table_path, filename)
    if os.path.exists(root_path):
        return root_path
    return None


def _build_thumb_sig(source_path: str) -> str:
    st = os.stat(source_path)
    return f'{st.st_mtime_ns}_{st.st_size}'


def _thumb_file_path(table_dir: str, media_key: str, source_path: str) -> Path:
    return THUMB_CACHE_ROOT / table_dir / f'{media_key}_{_build_thumb_sig(source_path)}.png'


def _thumb_url(path: Path) -> str:
    rel = path.relative_to(THUMB_CACHE_ROOT).as_posix()
    return f'/media_thumbs/{rel}'


def _get_cached_thumb_url(table_dir: str, media_key: str, source_path: str, source_exists: bool = False) -> Optional[str]:
    if not _is_image_media_key(media_key):
        return None
    if not source_exists and not os.path.exists(source_path):
        return None
    try:
        path = _thumb_file_path(table_dir, media_key, source_path)
        if path.exists():
            os.utime(path, None)
            return _thumb_url(path)
    except Exception:
        return None
    return None


def _ensure_thumb(table_dir: str, media_key: str, source_path: str) -> Optional[str]:
    if not _is_image_media_key(media_key) or not os.path.exists(source_path):
        return None
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None

    try:
        path = _thumb_file_path(table_dir, media_key, source_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            os.utime(path, None)
            return _thumb_url(path)

        for old in path.parent.glob(f'{media_key}_*.png'):
            if old != path:
                old.unlink(missing_ok=True)
        for old in path.parent.glob(f'{media_key}_*.jpg'):
            if old != path:
                old.unlink(missing_ok=True)

        with Image.open(source_path) as img:
            img = ImageOps.exif_transpose(img)
            has_alpha = (
                img.mode in ('RGBA', 'LA')
                or (img.mode == 'P' and 'transparency' in img.info)
            )
            img = img.convert('RGBA' if has_alpha else 'RGB')
            img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
            img.save(path, format='PNG', optimize=True)
        os.utime(path, None)
        return _thumb_url(path)
    except Exception:
        return None


def get_tables_path() -> str:
    try:
        return get_tables_root_from_config(_INI_CFG.config)
    except Exception as e:
        logger.debug(f'Could not read tablerootdir from vpinfe.ini: {e}')
        return os.path.expanduser('~/tables')


def scan_media_tables(silent: bool = False):
    """Scan table directories and collect media file info."""
    tables_path = get_tables_path()
    if not os.path.exists(tables_path):
        logger.warning(f"Tables path does not exist: {tables_path}. Skipping scan.")
        if not silent:
            ui.notify("Tables path does not exist. Please verify your vpinfe.ini settings", type="negative")
        return []

    try:
        entries, _ = scan_tables_root(
            tables_path,
            scan_depth=get_scan_depth_from_config(_INI_CFG.config),
        )
    except Exception as exc:
        logger.error(f"Failed to scan tables directory: {exc}")
        return []

    def _process_table(entry):
        current_dir = entry.table_name
        root = entry.table_dir
        dir_contents = entry.dir_contents

        # Single listdir for medias/ subfolder
        medias_dir = os.path.join(root, "medias")
        try:
            medias_contents = set(os.listdir(medias_dir)) if "medias" in dir_contents else set()
        except Exception:
            medias_contents = set()

        meta_path = entry.info_path
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"Error reading {meta_path}: {e}")
            return None

        info = raw.get("Info", {})
        vpinfe = raw.get("VPinFE", {})

        name = ((vpinfe.get("alttitle") or info.get("Title") or current_dir) or "").strip()

        # Build media availability dict using in-memory listings
        media_info = {}
        thumb_info = {}
        for media_key, _, media_filename in MEDIA_TYPES:
            if media_filename in medias_contents:
                src_path = os.path.join(medias_dir, media_filename)
                media_info[media_key] = _media_url('media_tables', current_dir, 'medias', media_filename)
                thumb_info[media_key] = _get_cached_thumb_url(current_dir, media_key, src_path, source_exists=True)
            elif media_filename in dir_contents:
                src_path = os.path.join(root, media_filename)
                media_info[media_key] = _media_url('media_tables', current_dir, media_filename)
                thumb_info[media_key] = _get_cached_thumb_url(current_dir, media_key, src_path, source_exists=True)
            else:
                media_info[media_key] = None
                thumb_info[media_key] = None

        return {
            'name': name,
            'table_dir': current_dir,
            'table_path': root,
            'manufacturer': info.get("Manufacturer", ""),
            'year': info.get("Year", ""),
            'type': info.get("Type", ""),
            'themes': info.get("Themes", []),
            'media': media_info,
            'thumbs': thumb_info,
            'thumb_errors': {},
            # Flat fields for Quasar table rendering
            'has_bg': media_info.get('bg') is not None,
            'has_dmd': media_info.get('dmd') is not None,
            'has_table': media_info.get('table') is not None,
            'has_fss': media_info.get('fss') is not None,
            'has_wheel': media_info.get('wheel') is not None,
            'has_cab': media_info.get('cab') is not None,
            'has_realdmd': media_info.get('realdmd') is not None,
            'has_realdmd_color': media_info.get('realdmd_color') is not None,
            'has_flyer': media_info.get('flyer') is not None,
            'has_table_video': media_info.get('table_video') is not None,
            'has_bg_video': media_info.get('bg_video') is not None,
            'has_dmd_video': media_info.get('dmd_video') is not None,
            'has_audio': media_info.get('audio') is not None,
        }

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_process_table, entry): entry for entry in entries}
        for future in concurrent.futures.as_completed(futures):
            try:
                row = future.result()
            except Exception as exc:
                entry = futures[future]
                logger.warning(f"Error processing table {entry.table_name}: {exc}")
                continue
            if row:
                rows.append(row)

    return rows


def render_panel():
    global _media_route_registered, _thumb_route_registered, _media_pagination_state, _media_filter_state, _media_page_client

    try:
        page_client = context.client
        _media_page_client = page_client
    except RuntimeError:
        page_client = None
        _media_page_client = None

    _media_pagination_state = {
        **_media_pagination_state,
        'rowsPerPage': _load_persisted_rows_per_page(),
    }

    page_state = {
        'active': True,
        'scan_in_progress': False,
        'thumb_warm_in_progress': False,
        'pending_warm_rows': None,
    }

    if page_client is not None:
        page_client.on_disconnect(lambda: page_state.__setitem__('active', False))

    def is_page_active() -> bool:
        return page_state['active']

    def can_update_ui() -> bool:
        if not is_page_active():
            return False
        if page_client is None:
            return False
        return page_client.has_socket_connection

    # Register media files route once
    if not _media_route_registered:
        tables_path = get_tables_path()
        if os.path.exists(tables_path):
            app.add_media_files('/media_tables', tables_path)
            _media_route_registered = True
    if not _thumb_route_registered:
        THUMB_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        app.add_media_files('/media_thumbs', str(THUMB_CACHE_ROOT))
        _thumb_route_registered = True

    with ui.column().classes('w-full'):
        # Table styles (same as tables page for consistency)
        ui.add_head_html('''
        <style>
            .media-table .q-table {
                border-radius: 8px !important;
                overflow: hidden !important;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;
            }
            .media-table .q-table thead tr {
                background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%) !important;
            }
            .media-table .q-table thead tr th {
                background: transparent !important;
                color: #fff !important;
                font-weight: 600 !important;
                text-transform: uppercase !important;
                font-size: 0.75rem !important;
                letter-spacing: 0.05em !important;
                padding: 16px 12px !important;
            }
            .media-table .q-table tbody tr:nth-child(odd) {
                background-color: #1e293b !important;
            }
            .media-table .q-table tbody tr:nth-child(even) {
                background-color: #0f172a !important;
            }
            .media-table .q-table tbody tr td {
                color: #e2e8f0 !important;
                padding: 8px 12px !important;
                border-bottom: 1px solid #334155 !important;
            }
            .media-table .q-table tbody tr:hover {
                background-color: #334155 !important;
                transition: background-color 0.2s ease !important;
            }
            .media-table .q-table tbody tr:hover td {
                color: #fff !important;
            }
            .media-table .q-table__bottom {
                background-color: #1e293b !important;
                color: #94a3b8 !important;
                border-top: 1px solid #334155 !important;
            }
            .media-thumb-wrapper {
                width: 50px;
                height: 50px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto;
            }
            .media-thumb {
                width: 48px;
                height: 48px;
                object-fit: cover;
                border-radius: 4px;
                border: 1px solid #334155;
                cursor: pointer;
                display: block;
            }
            .media-missing {
                width: 50px;
                height: 50px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 4px;
                border: 1px dashed #475569;
                color: #475569;
                font-size: 10px;
                margin: 0 auto;
                cursor: pointer;
            }
        </style>
        ''')

        columns = [
            {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
            {'name': 'bg', 'label': 'BG', 'field': 'has_bg', 'align': 'center', 'sortable': True},
            {'name': 'dmd', 'label': 'DMD', 'field': 'has_dmd', 'align': 'center', 'sortable': True},
            {'name': 'table_img', 'label': 'Table', 'field': 'has_table', 'align': 'center', 'sortable': True},
            {'name': 'fss', 'label': 'FSS', 'field': 'has_fss', 'align': 'center', 'sortable': True},
            {'name': 'wheel', 'label': 'Wheel', 'field': 'has_wheel', 'align': 'center', 'sortable': True},
            {'name': 'cab', 'label': 'Cab', 'field': 'has_cab', 'align': 'center', 'sortable': True},
            {'name': 'flyer', 'label': 'Flyer', 'field': 'has_flyer', 'align': 'center', 'sortable': True},
            {'name': 'realdmd', 'label': 'Real DMD', 'field': 'has_realdmd', 'align': 'center', 'sortable': True},
            {'name': 'realdmd_color', 'label': 'Real DMD Color', 'field': 'has_realdmd_color', 'align': 'center', 'sortable': True},
            {'name': 'table_video', 'label': 'Table Video', 'field': 'has_table_video', 'align': 'center', 'sortable': True},
            {'name': 'bg_video', 'label': 'BG Video', 'field': 'has_bg_video', 'align': 'center', 'sortable': True},
            {'name': 'dmd_video', 'label': 'DMD Video', 'field': 'has_dmd_video', 'align': 'center', 'sortable': True},
            {'name': 'audio', 'label': 'Audio', 'field': 'has_audio', 'align': 'center', 'sortable': True},
        ]

        # --- Filter state and functions ---
        filter_state = dict(_media_filter_state)
        pagination_state = dict(_media_pagination_state)

        def get_filter_options_from_cache():
            tables = _media_cache or []
            manufacturers = set()
            years = set()
            themes = set()
            table_types = set()

            for t in tables:
                mfr = t.get('manufacturer', '')
                if mfr:
                    manufacturers.add(mfr)
                year = t.get('year', '')
                if year:
                    years.add(str(year))
                table_themes = t.get('themes', [])
                if isinstance(table_themes, list):
                    themes.update(table_themes)
                elif table_themes:
                    themes.add(table_themes)
                ttype = t.get('type', '')
                if ttype:
                    table_types.add(ttype)

            return {
                'manufacturers': ['All'] + sorted(manufacturers),
                'years': ['All'] + sorted(years),
                'themes': ['All'] + sorted(themes),
                'table_types': ['All'] + sorted(table_types),
            }

        def apply_filters():
            tables = _media_cache or []
            result = tables

            search_term = filter_state['search'].lower().strip()
            if search_term:
                result = [
                    t for t in result
                    if search_term in (t.get('name') or '').lower()
                ]

            if filter_state['manufacturer'] != 'All':
                result = [t for t in result if t.get('manufacturer') == filter_state['manufacturer']]

            if filter_state['year'] != 'All':
                result = [t for t in result if str(t.get('year', '')) == filter_state['year']]

            if filter_state['theme'] != 'All':
                result = [
                    t for t in result
                    if filter_state['theme'] in (t.get('themes') or [])
                    or t.get('themes') == filter_state['theme']
                ]

            if filter_state['table_type'] != 'All':
                result = [t for t in result if t.get('type') == filter_state['table_type']]

            # Missing media filters — show only tables missing the checked media types
            for media_key, _, _ in MEDIA_TYPES:
                if filter_state.get(f'missing_{media_key}'):
                    result = [t for t in result if t.get('media', {}).get(media_key) is None]

            result.sort(key=lambda r: (r.get('name') or '').lower())
            return result

        def _visible_rows(rows: List[Dict]) -> List[Dict]:
            try:
                page = int(pagination_state.get('page', 1) or 1)
                rows_per_page = int(pagination_state.get('rowsPerPage', 100))
            except Exception:
                page = 1
                rows_per_page = 100
            if rows_per_page < 0:
                rows_per_page = 100
            if rows_per_page == 0:
                return rows
            start = max(0, (page - 1) * rows_per_page)
            return rows[start:start + rows_per_page]

        def _store_pagination(pagination: Optional[Dict]) -> None:
            global _media_pagination_state
            if not isinstance(pagination, dict):
                return
            try:
                if 'page' in pagination:
                    pagination_state['page'] = max(1, int(pagination.get('page') or 1))
                if 'rowsPerPage' in pagination:
                    rows_per_page = int(pagination.get('rowsPerPage', 100))
                    pagination_state['rowsPerPage'] = rows_per_page if rows_per_page >= 0 else 100
            except Exception:
                pagination_state['page'] = max(1, int(pagination_state.get('page', 1) or 1))
                rows_per_page = int(pagination_state.get('rowsPerPage', 100) or 100)
                pagination_state['rowsPerPage'] = rows_per_page if rows_per_page >= 0 else 100

            if 'sortBy' in pagination:
                pagination_state['sortBy'] = pagination.get('sortBy')
            if 'descending' in pagination:
                pagination_state['descending'] = bool(pagination.get('descending'))

            _media_pagination_state = dict(pagination_state)
            _save_persisted_rows_per_page(_media_pagination_state['rowsPerPage'])

        async def warm_visible_thumbnails(rows: List[Dict]) -> None:
            try:
                if not is_page_active():
                    return
                if page_state.get('thumb_warm_in_progress'):
                    # Queue the latest request (e.g. user switched pages) and run it next.
                    page_state['pending_warm_rows'] = rows
                    return
                # On first page load, defer warm-up until the websocket connection is ready,
                # otherwise thumbnails can be built without any UI updates being sent.
                if page_client is not None and not page_client.has_socket_connection:
                    try:
                        await page_client.connected(timeout=3)
                    except Exception:
                        if is_page_active():
                            async def _retry():
                                await asyncio.sleep(0.5)
                                if is_page_active():
                                    await warm_visible_thumbnails(rows)
                            asyncio.create_task(_retry())
                        return
                visible = _visible_rows(rows)
                visible = visible[:THUMB_WARM_ROW_BATCH_SIZE]
                pending = []
                for row in visible:
                    media = row.get('media', {})
                    thumbs = row.setdefault('thumbs', {})
                    errors = row.setdefault('thumb_errors', {})
                    for media_key in IMAGE_MEDIA_KEYS:
                        if not media.get(media_key):
                            continue
                        if thumbs.get(media_key) or errors.get(media_key):
                            continue
                        source_path = _source_media_path(row.get('table_path', ''), media_key)
                        if source_path:
                            pending.append((row, media_key, source_path))

                if not pending:
                    return

                page_state['thumb_warm_in_progress'] = True
                sem = asyncio.Semaphore(4)
                current_pagination = dict(media_table._props.get('pagination', {}))

                async def _build_one(row: Dict, media_key: str, source_path: str):
                    changed = False
                    try:
                        async with sem:
                            thumb = await run.io_bound(_ensure_thumb, row.get('table_dir', ''), media_key, source_path)
                        if thumb:
                            if row['thumbs'].get(media_key) != thumb:
                                row['thumbs'][media_key] = thumb
                                changed = True
                            row.setdefault('thumb_errors', {}).pop(media_key, None)
                        else:
                            row.setdefault('thumb_errors', {})[media_key] = True
                    except Exception:
                        row.setdefault('thumb_errors', {})[media_key] = True
                    return changed

                for i in range(0, len(pending), THUMB_WARM_CHUNK_SIZE):
                    chunk = pending[i:i + THUMB_WARM_CHUNK_SIZE]
                    results = await asyncio.gather(*(_build_one(r, k, p) for r, k, p in chunk))
                    if any(results) and can_update_ui():
                        with page_client:
                            # Rebuild rows from cache (same path as revisit), but keep current pagination.
                            update_table_display(schedule_warm=False)
                            if current_pagination:
                                media_table.run_method('setPagination', current_pagination)
            finally:
                page_state['thumb_warm_in_progress'] = False
                pending_rows = page_state.get('pending_warm_rows')
                if pending_rows is not None and is_page_active():
                    page_state['pending_warm_rows'] = None
                    asyncio.create_task(warm_visible_thumbnails(pending_rows))

        def update_table_display(schedule_warm: bool = True):
            filtered = apply_filters()
            rows_per_page = int(pagination_state.get('rowsPerPage', 100) or 100)
            if rows_per_page < 0:
                rows_per_page = 100
            max_page = 1 if rows_per_page == 0 else max(1, (len(filtered) + rows_per_page - 1) // rows_per_page)
            pagination_state['page'] = min(max(1, int(pagination_state.get('page', 1) or 1)), max_page)
            media_table._props['pagination'] = dict(pagination_state)
            media_table._props['rows'] = filtered
            media_table.update()
            media_table.run_method('setPagination', dict(pagination_state))
            total = len(_media_cache or [])
            shown = len(filtered)
            if shown == total:
                count_label.set_text(f"Tables ({total})")
            else:
                count_label.set_text(f"Tables ({shown} of {total})")
            if schedule_warm and is_page_active():
                asyncio.create_task(warm_visible_thumbnails(filtered))

        def _extract_pagination(payload):
            """Normalize pagination payloads emitted by Quasar/NiceGUI."""
            if isinstance(payload, dict):
                if isinstance(payload.get('pagination'), dict):
                    return payload['pagination']
                if 'page' in payload or 'rowsPerPage' in payload:
                    return payload
            if isinstance(payload, (list, tuple)):
                for item in payload:
                    pg = _extract_pagination(item)
                    if pg:
                        return pg
            return None

        def on_search_change(e: events.ValueChangeEventArguments):
            filter_state['search'] = e.value or ''
            _media_filter_state['search'] = filter_state['search']
            update_table_display()

        def on_manufacturer_change(e: events.ValueChangeEventArguments):
            filter_state['manufacturer'] = e.value or 'All'
            _media_filter_state['manufacturer'] = filter_state['manufacturer']
            update_table_display()

        def on_year_change(e: events.ValueChangeEventArguments):
            filter_state['year'] = e.value or 'All'
            _media_filter_state['year'] = filter_state['year']
            update_table_display()

        def on_theme_change(e: events.ValueChangeEventArguments):
            filter_state['theme'] = e.value or 'All'
            _media_filter_state['theme'] = filter_state['theme']
            update_table_display()

        def on_table_type_change(e: events.ValueChangeEventArguments):
            filter_state['table_type'] = e.value or 'All'
            _media_filter_state['table_type'] = filter_state['table_type']
            update_table_display()

        def clear_filters():
            global _media_pagination_state, _media_filter_state
            filter_state['search'] = ''
            filter_state['manufacturer'] = 'All'
            filter_state['year'] = 'All'
            filter_state['theme'] = 'All'
            filter_state['table_type'] = 'All'
            search_input.value = ''
            manufacturer_select.value = 'All'
            year_select.value = 'All'
            theme_select.value = 'All'
            table_type_select.value = 'All'
            # Reset missing media checkboxes
            for media_key, _, _ in MEDIA_TYPES:
                filter_state[f'missing_{media_key}'] = False
            for cb in missing_checkboxes.values():
                cb.value = False
            _media_filter_state = dict(filter_state)
            pagination_state['page'] = 1
            _media_pagination_state = dict(pagination_state)
            media_table._props['pagination'] = dict(pagination_state)
            update_table_display()

        def refresh_filter_options():
            opts = get_filter_options_from_cache()
            manufacturer_select.options = opts['manufacturers']
            year_select.options = opts['years']
            theme_select.options = opts['themes']
            table_type_select.options = opts['table_types']
            manufacturer_select.update()
            year_select.update()
            theme_select.update()
            table_type_select.update()

        async def perform_scan(*_, silent: bool = False):
            global _media_cache
            if page_state['scan_in_progress']:
                return
            page_state['scan_in_progress'] = True
            logger.info("Scanning media...")
            # Capture client context before any io_bound calls (may not exist if called from timer)
            try:
                client = context.client
            except RuntimeError:
                client = None
            try:
                if can_update_ui():
                    with page_client:
                        scan_btn.disable()

                media_rows = await run.io_bound(scan_media_tables, silent)
                try:
                    media_rows.sort(key=lambda r: (r.get('name') or '').lower())
                except Exception:
                    pass

                _media_cache = media_rows

                if can_update_ui():
                    with page_client:
                        try:
                            refresh_filter_options()
                            update_table_display()
                        except NameError:
                            media_table._props['rows'] = media_rows
                            media_table.update()

                await asyncio.sleep(0.05)
                if can_update_ui():
                    with page_client:
                        try:
                            ui.run_javascript('window.dispatchEvent(new Event("resize"));')
                        except RuntimeError:
                            pass

                if not silent and client:
                    if can_update_ui():
                        with client:
                            ui.notify('Media scan complete!', type='positive')
            except Exception as e:
                logger.exception("Failed to scan media")
                if not silent and client:
                    if can_update_ui():
                        with client:
                            ui.notify(f"Error during scan: {e}", type='negative')
            finally:
                page_state['scan_in_progress'] = False
                if can_update_ui():
                    with page_client:
                        scan_btn.enable()

        # --- Media replacement logic ---

        def replace_media_file(table_path: str, table_dir: str, media_key: str, uploaded_path: str):
            """Copy uploaded file to medias/ subfolder with standard name, update .info."""
            target_filename = MEDIA_KEY_TO_FILENAME[media_key]
            medias_dir = os.path.join(table_path, "medias")
            os.makedirs(medias_dir, exist_ok=True)
            target_path = os.path.join(medias_dir, target_filename)

            # Copy the uploaded file (overwrite if exists)
            shutil.copy2(uploaded_path, target_path)

            # Update the .info file
            info_file = os.path.join(table_path, f"{table_dir}.info")
            if os.path.exists(info_file):
                mc = MetaConfig(info_file)
                mc.addMedia(media_key, "user", target_path, "")

            return target_path

        def update_cache_entry(table_dir: str, media_key: str, url_path: str, thumb_url: Optional[str] = None):
            """Update the in-memory cache for the replaced media."""
            if _media_cache is None:
                return
            for row in _media_cache:
                if row['table_dir'] == table_dir:
                    row['media'][media_key] = url_path
                    row.setdefault('thumbs', {})[media_key] = thumb_url
                    row.setdefault('thumb_errors', {}).pop(media_key, None)
                    row[f'has_{media_key}'] = url_path is not None
                    break

        def open_replace_dialog(table_dir: str, table_path: str, table_name: str, media_key: str, media_label: str):
            """Open a dialog to replace a media file for a table."""
            target_filename = MEDIA_KEY_TO_FILENAME[media_key]
            is_video = target_filename.endswith('.mp4')
            is_audio = target_filename.endswith('.mp3')
            media_type_label = 'Audio' if is_audio else ('Video' if is_video else 'Image')
            accept_type = '.mp3,audio/*' if is_audio else ('.mp4' if is_video else 'image/*')
            current_url = None
            # Find current media URL from cache
            if _media_cache:
                for row in _media_cache:
                    if row['table_dir'] == table_dir:
                        current_url = row['media'].get(media_key)
                        break

            with ui.dialog() as dlg, ui.card().style('min-width: 500px; background: #1e293b; border: 1px solid #334155;'):
                ui.label(f'Replace {media_label}').classes('text-xl font-bold text-white mb-2')
                ui.label(f'Table: {table_name}').classes('text-slate-400 mb-1')
                ui.label(f'Target: {target_filename}').classes('text-slate-500 text-sm mb-4')

                # Show current media if exists
                if current_url:
                    ui.label('Current:').classes('text-slate-400 text-sm')
                    if is_audio:
                        ui.html(f'<audio src="{current_url}" controls preload="metadata" style="width: 320px; max-width: 100%;"></audio>').classes('mb-4')
                    elif is_video:
                        ui.html(f'<video src="{current_url}" style="max-width: 240px; max-height: 240px; border-radius: 6px; border: 1px solid #334155;" autoplay loop muted></video>').classes('mb-4')
                    else:
                        ui.image(current_url).style('max-width: 240px; max-height: 240px; border-radius: 6px; border: 1px solid #334155;').classes('mb-4')
                else:
                    ui.label(f'No current {media_type_label.lower()}').classes('text-slate-500 italic mb-4')

                # File upload
                ui.label(f'Select new {media_type_label.lower()}:').classes('text-slate-400 text-sm mb-1')
                upload_state = {'path': None}

                async def handle_upload(e: events.UploadEventArguments):
                    # Save to a temp location first
                    tmp_dir = os.path.join(table_path, '.tmp_upload')
                    os.makedirs(tmp_dir, exist_ok=True)
                    tmp_path = os.path.join(tmp_dir, e.file.name)
                    with open(tmp_path, 'wb') as f:
                        f.write(await e.file.read())
                    upload_state['path'] = tmp_path
                    confirm_btn.enable()
                    ui.notify(f'File ready: {e.file.name}', type='info')

                ui.upload(
                    on_upload=handle_upload,
                    auto_upload=True,
                    max_files=1,
                ).props(f'accept="{accept_type}" flat bordered').classes('w-full mb-4').style('background: #0f172a; border: 1px dashed #475569;')

                with ui.row().classes('w-full justify-end gap-3 mt-2'):
                    ui.button('Cancel', on_click=dlg.close).props('flat').classes('text-slate-400')

                    async def do_replace():
                        if not upload_state['path']:
                            return
                        try:
                            src = upload_state['path']
                            target_path = await run.io_bound(replace_media_file, table_path, table_dir, media_key, src)

                            # Build the URL for the new media (now in medias/ subfolder)
                            new_url = _media_url('media_tables', table_dir, 'medias', target_filename)
                            new_thumb = await run.io_bound(_ensure_thumb, table_dir, media_key, target_path)
                            update_cache_entry(table_dir, media_key, new_url, new_thumb)
                            update_table_display()

                            # Cleanup temp
                            tmp_dir = os.path.join(table_path, '.tmp_upload')
                            if os.path.exists(tmp_dir):
                                shutil.rmtree(tmp_dir, ignore_errors=True)

                            ui.notify(f'{media_label} replaced!', type='positive')
                            dlg.close()
                        except Exception as ex:
                            logger.exception("Failed to replace media")
                            ui.notify(f'Error: {ex}', type='negative')

                    confirm_btn = ui.button('Replace', icon='save', on_click=do_replace).props('color=primary')
                    confirm_btn.disable()

            dlg.open()

        # --- UI Layout ---
        # Header section
        with ui.card().classes('w-full mb-4').style('background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); border-radius: 12px;'):
            with ui.row().classes('w-full justify-between items-center p-4 gap-4'):
                ui.label('Media Management').classes('text-2xl font-bold text-white').style('flex-shrink: 0;')
                with ui.row().classes('gap-3 items-center flex-wrap'):
                    scan_btn = ui.button("Scan Media", icon="refresh", on_click=lambda: asyncio.create_task(perform_scan())).props("color=white text-color=primary rounded")

        # Use cached data if available
        initial_rows = _media_cache if _media_cache is not None else []

        # Filter UI
        with ui.card().classes('w-full mb-4').style('border-radius: 8px; background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155;'):
            with ui.row().classes('w-full items-center gap-4 p-4 flex-wrap'):
                search_input = ui.input(placeholder='Search tables...', value=filter_state['search']).props('outlined dense clearable').classes('flex-grow').style('min-width: 200px;')
                search_input.on_value_change(on_search_change)

                filter_opts = get_filter_options_from_cache()

                manufacturer_select = ui.select(
                    label='Manufacturer',
                    options=filter_opts['manufacturers'],
                    value=filter_state['manufacturer']
                ).props('outlined dense').classes('w-40')
                manufacturer_select.on_value_change(on_manufacturer_change)

                year_select = ui.select(
                    label='Year',
                    options=filter_opts['years'],
                    value=filter_state['year']
                ).props('outlined dense').classes('w-32')
                year_select.on_value_change(on_year_change)

                theme_select = ui.select(
                    label='Theme',
                    options=filter_opts['themes'],
                    value=filter_state['theme']
                ).props('outlined dense').classes('w-40')
                theme_select.on_value_change(on_theme_change)

                table_type_select = ui.select(
                    label='Type',
                    options=filter_opts['table_types'],
                    value=filter_state['table_type']
                ).props('outlined dense').classes('w-28')
                table_type_select.on_value_change(on_table_type_change)

                ui.button(icon='clear_all', on_click=clear_filters).props('flat round').tooltip('Clear all filters')

        # Missing Media filter panel
        missing_checkboxes = {}
        with ui.card().classes('w-full mb-4').style('border-radius: 8px; background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155;'):
            with ui.row().classes('w-full items-center gap-4 p-4 flex-wrap'):
                ui.label('Missing Media:').classes('text-sm text-slate-400 font-semibold').style('flex-shrink: 0;')
                for media_key, media_label, _ in MEDIA_TYPES:
                    def make_handler(key):
                        def handler(e: events.ValueChangeEventArguments):
                            filter_state[f'missing_{key}'] = e.value
                            _media_filter_state[f'missing_{key}'] = e.value
                            media_table._props['pagination']['page'] = 1
                            update_table_display()
                        return handler
                    cb = ui.checkbox(media_label, value=filter_state.get(f'missing_{media_key}', False), on_change=make_handler(media_key)).classes('text-white')
                    missing_checkboxes[media_key] = cb

        # Table count label
        total = len(initial_rows)
        count_label = ui.label(f"Tables ({total})").classes('text-lg font-semibold text-slate-300 py-1 text-center w-full')

        # Table with image thumbnails
        table_container = ui.column().classes("w-full media-table").style("flex: 1; overflow: hidden; display: flex;")

        with table_container:
            media_table = (
                ui.table(columns=columns, rows=initial_rows, row_key='table_dir', pagination=dict(pagination_state))
                                    .props('rows-per-page-options="[100,200,500,0]" sort-by="name" sort-order="asc"')
                .classes("w-full media-main-table")
                  .style("flex: 1; overflow: auto;")
            )

            media_table.add_slot('body-cell-name', '''
                <q-td :props="props">
                    <div style="display: flex; align-items: center; min-height: 100%;">
                        <span>{{ props.value }}</span>
                    </div>
                </q-td>
            ''')

            # Lookup for media_key -> label
            MEDIA_KEY_TO_LABEL = {key: label for key, label, _ in MEDIA_TYPES}

            # Custom slot for each media type column to show thumbnail or missing indicator
            for media_key, media_label, media_filename in MEDIA_TYPES:
                col_name = media_key
                if media_key == 'table':
                    col_name = 'table_img'
                emit_expr = "$parent.$emit('media_click', [props.row.table_dir, props.row.table_path, props.row.name, '" + media_key + "'])"
                is_video = media_filename.endswith('.mp4')
                is_audio = media_filename.endswith('.mp3')

                if is_audio:
                    media_table.add_slot(f'body-cell-{col_name}', '''
                        <q-td :props="props">
                            <div v-if="props.row.media.''' + media_key + '''"
                                 @click.stop="''' + emit_expr + '''"
                                 style="cursor: pointer;">
                                <q-badge color="green-8" text-color="white" label="Audio"
                                         style="font-size: 10px; padding: 2px 8px;" />
                            </div>
                            <div v-else class="media-missing"
                                 @click.stop="''' + emit_expr + '''"
                                 style="cursor: pointer;">--</div>
                        </q-td>
                    ''')
                elif is_video:
                    media_table.add_slot(f'body-cell-{col_name}', '''
                        <q-td :props="props">
                            <div v-if="props.row.media.''' + media_key + '''" class="media-thumb-wrapper"
                                 @click.stop="''' + emit_expr + '''"
                                 style="cursor: pointer;">
                                <q-checkbox
                                    :model-value="true"
                                    dense
                                    disable
                                    color="positive"
                                />
                                <q-tooltip anchor="top middle" self="bottom middle" :offset="[0, 8]"
                                           class="bg-dark" style="padding: 4px;">
                                    <video :src="props.row.media.''' + media_key + '''"
                                           style="max-width: 240px; max-height: 240px; border-radius: 6px; border: 2px solid #3b82f6;"
                                           preload="none"
                                           autoplay loop muted />
                                </q-tooltip>
                            </div>
                            <div v-else class="media-missing"
                                 @click.stop="''' + emit_expr + '''"
                                 style="cursor: pointer;">--</div>
                        </q-td>
                    ''')
                else:
                    media_table.add_slot(f'body-cell-{col_name}', '''
                        <q-td :props="props">
                            <div v-if="props.row.media.''' + media_key + '''" class="media-thumb-wrapper"
                                 @click.stop="''' + emit_expr + '''"
                                 style="cursor: pointer;">
                                <img v-if="props.row.thumbs && props.row.thumbs.''' + media_key + '''"
                                     :src="props.row.thumbs.''' + media_key + '''"
                                     class="media-thumb"
                                     loading="lazy" />
                                <q-badge v-else color="blue-grey-7" text-color="white" label="IMG"
                                         style="font-size: 10px; padding: 2px 8px;" />
                                <q-tooltip anchor="top middle" self="bottom middle" :offset="[0, 8]"
                                           class="bg-dark" style="padding: 4px;">
                                    <img v-if="props.row.thumbs && props.row.thumbs.''' + media_key + '''"
                                         :src="props.row.thumbs.''' + media_key + '''"
                                         style="max-width: 480px; max-height: 480px; border-radius: 6px; border: 2px solid #3b82f6; object-fit: contain;" />
                                    <q-badge v-else color="blue-grey-7" text-color="white" label="Generating..."
                                             style="font-size: 10px; padding: 2px 8px;" />
                                </q-tooltip>
                            </div>
                            <div v-else class="media-missing"
                                 @click.stop="''' + emit_expr + '''"
                                 style="cursor: pointer;">--</div>
                        </q-td>
                    ''')

            # Handle media click events from slot templates
            def on_media_click(e):
                args = e.args
                table_dir = args[0]
                table_path = args[1]
                table_name = args[2]
                media_key = args[3]
                media_label = MEDIA_KEY_TO_LABEL.get(media_key, media_key)
                open_replace_dialog(
                    table_dir=table_dir,
                    table_path=table_path,
                    table_name=table_name,
                    media_key=media_key,
                    media_label=media_label,
                )
            media_table.on('media_click', on_media_click)

            media_table.add_slot('bottom', '''
                <div class="row full-width items-center q-pa-sm"
                     style="background-color: #1e293b; color: #94a3b8; border-top: 1px solid #334155;">
                    <span class="q-mr-sm" style="font-size: 0.85rem;">Rows per page:</span>
                    <q-select
                        :model-value="props.pagination.rowsPerPage"
                        :options="[{label:'100', value:100}, {label:'200', value:200}, {label:'500', value:500}, {label:'All', value:0}]"
                        @update:model-value="val => $parent.$emit('update:pagination', Object.assign({}, props.pagination, {rowsPerPage: val, page: 1}))"
                        dense
                        borderless
                        dark
                        emit-value
                        map-options
                        options-dense
                        popup-content-style="z-index: 10000;"
                        options-cover="false"
                        style="min-width: 50px; color: #e2e8f0;"
                    />
                    <q-space />
                    <q-btn flat round dense icon="first_page" :disable="props.isFirstPage" @click="props.firstPage" size="sm" color="grey-5" />
                    <q-btn flat round dense icon="chevron_left" :disable="props.isFirstPage" @click="props.prevPage" size="sm" color="grey-5" />
                    <span class="q-mx-sm" style="font-size: 0.85rem;">
                        Page {{ props.pagination.page }} of {{ props.pagesNumber }}
                    </span>
                    <q-btn flat round dense icon="chevron_right" :disable="props.isLastPage" @click="props.nextPage" size="sm" color="grey-5" />
                    <q-btn flat round dense icon="last_page" :disable="props.isLastPage" @click="props.lastPage" size="sm" color="grey-5" />
                </div>
            ''')

            def on_pagination_change(e):
                try:
                    pagination = _extract_pagination(e.args)
                    if pagination:
                        _store_pagination(pagination)
                        media_table._props['pagination'] = dict(pagination_state)
                        media_table.run_method('setPagination', dict(pagination_state))
                except Exception:
                    pass
                if is_page_active():
                    asyncio.create_task(warm_visible_thumbnails(apply_filters()))

            media_table.on('update:pagination', on_pagination_change)

        # Startup scan
        async def refresh_on_startup():
            if not is_page_active():
                return
            if _media_cache is not None:
                if can_update_ui():
                    refresh_filter_options()
                    update_table_display()
            else:
                await perform_scan(silent=True)
            if can_update_ui():
                restore_page_scroll_state(
                    page_client,
                    get_scroll_state(),
                    '.media-main-table .q-table__middle',
                )

        async def startup_refresh():
            await asyncio.sleep(0.2)
            if not is_page_active():
                return
            await refresh_on_startup()

        ui.timer(0.1, lambda: asyncio.create_task(startup_refresh()), once=True)
