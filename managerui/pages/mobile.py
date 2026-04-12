import asyncio
import os
import json
import logging
import shutil
import tempfile
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from nicegui import ui, run, context, app
from platformdirs import user_config_dir
from typing import Callable, Optional

from common.iniconfig import IniConfig, get_tables_root_from_config
from common.table_catalog import get_mobile_display_rows
from common.table_scanner import get_scan_depth_from_config
from .scroll_state import capture_scroll_state as capture_page_scroll_state
from .scroll_state import restore_scroll_state as restore_page_scroll_state
from .scroll_state import default_scroll_state


logger = logging.getLogger("vpinfe.manager.mobile")

CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
VPINFE_INI_PATH = CONFIG_DIR / 'vpinfe.ini'

_INI_CFG = None
_mobile_page_client = None
_mobile_active_tab = 'websend'
_mobile_tabs_ref = None
_mobile_render_id = 0
_mobile_base_rows_cache: Optional[list[dict]] = None
_mobile_scroll_states = {
    'websend': default_scroll_state(),
    'vpxz': default_scroll_state(),
}
_mobile_pagination_states = {
    'websend': {'page': 1, 'rowsPerPage': 100},
    'vpxz': {'page': 1, 'rowsPerPage': 100},
}

_MOBILE_TAB_CONFIG = {
    'websend': {
        'selector': '.mobile-websend-table .q-table__middle',
    },
    'vpxz': {
        'selector': '.mobile-vpxz-table .q-table__middle',
    },
}


def _extract_pagination(payload) -> dict:
    """Robustly extract the pagination dict from a NiceGUI event args payload."""
    if isinstance(payload, dict):
        if 'pagination' in payload:
            return payload['pagination']
        if 'page' in payload or 'rowsPerPage' in payload:
            return payload
    if isinstance(payload, (list, tuple)):
        for item in payload:
            pg = _extract_pagination(item)
            if pg:
                return pg
    return {}


def _normalize_pagination_state(value) -> dict:
    if isinstance(value, dict):
        try:
            page = value.get('page', 1)
            page = max(1, int(page) if page is not None else 1)
        except Exception:
            page = 1
        try:
            rows_per_page = value.get('rowsPerPage', 100)
            rows_per_page = int(rows_per_page) if rows_per_page is not None else 100
            rows_per_page = rows_per_page if rows_per_page >= 0 else 100
        except Exception:
            rows_per_page = 100
        return {'page': page, 'rowsPerPage': rows_per_page}
    try:
        rows_per_page = int(value) if value is not None else 100
        rows_per_page = rows_per_page if rows_per_page >= 0 else 100
    except Exception:
        rows_per_page = 100
    return {'page': 1, 'rowsPerPage': rows_per_page}


def _save_mobile_pagination_state(tab_key: str, pagination: dict) -> None:
    normalized = _normalize_pagination_state(pagination)
    _mobile_pagination_states[tab_key] = normalized
    try:
        stored = dict(app.storage.user.get('mobile_pagination_states', {}) or {})
        stored[tab_key] = {'rowsPerPage': normalized['rowsPerPage']}
        app.storage.user['mobile_pagination_states'] = stored
    except Exception as e:
        logger.error(f"Error saving mobile pagination state for {tab_key}: {e}")


def _normalize_tab_key(value: object) -> str:
    raw = str(value or '').strip()
    lowered = raw.lower()
    if lowered in _MOBILE_TAB_CONFIG:
        return lowered
    if lowered in {'web send', 'websend'}:
        return 'websend'
    if lowered in {'vpxz download', 'vpxz'}:
        return 'vpxz'
    return 'websend'


async def _capture_tab_scroll_state(tab_key: str) -> None:
    global _mobile_scroll_states, _mobile_page_client
    cfg = _MOBILE_TAB_CONFIG.get(tab_key)
    if not cfg:
        return
    _mobile_scroll_states[tab_key] = await capture_page_scroll_state(
        _mobile_page_client,
        cfg['selector'],
    )


def _restore_tab_scroll_state(tab_key: str) -> None:
    cfg = _MOBILE_TAB_CONFIG.get(tab_key)
    if not cfg:
        return
    restore_page_scroll_state(
        _mobile_page_client,
        _mobile_scroll_states.get(tab_key, default_scroll_state()),
        cfg['selector'],
    )


async def capture_scroll_state() -> None:
    global _mobile_active_tab, _mobile_tabs_ref
    current_tab = _mobile_active_tab
    try:
        if _mobile_tabs_ref is not None:
            current_tab = _mobile_tabs_ref.value
    except Exception:
        pass
    tab_key = _normalize_tab_key(current_tab)
    _mobile_active_tab = tab_key
    try:
        app.storage.user['mobile_active_tab'] = tab_key
    except Exception:
        pass
    await _capture_tab_scroll_state(tab_key)


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _get_ini_config():
    global _INI_CFG
    if _INI_CFG is None:
        _INI_CFG = IniConfig(str(VPINFE_INI_PATH))
    return _INI_CFG


def _get_tables_path() -> str:
    cfg = _get_ini_config()
    return get_tables_root_from_config(cfg.config)


def _build_table_rows(tables):
    """Build display rows from scanned tables."""
    rows = []
    for t in tables:
        table_dir_name = t.get('table_dir_name') or t.get('filename') or ''
        if not table_dir_name:
            continue
        name = (t.get('name') or table_dir_name).strip()
        if not name:
            continue
        manufacturer = str(t.get('manufacturer', '') or '').strip()
        year = str(t.get('year', '') or '').strip()
        parts = [p for p in [manufacturer, year] if p]
        display = f"{name} ({' '.join(parts)})" if parts else name
        rows.append({
            'display_name': display,
            'table_dir_name': table_dir_name,
        })
    return rows


def _clone_mobile_rows(rows: list[dict]) -> list[dict]:
    return [dict(row) for row in rows]


def invalidate_mobile_rows_cache() -> None:
    global _mobile_base_rows_cache
    logger.debug(
        "Invalidating mobile rows cache: had_rows=%s",
        0 if _mobile_base_rows_cache is None else len(_mobile_base_rows_cache),
    )
    _mobile_base_rows_cache = None


def _get_mobile_base_rows():
    """Return mobile display rows built from tables cache or common scanner summaries."""
    global _mobile_base_rows_cache
    if _mobile_base_rows_cache is not None:
        logger.debug("Mobile rows cache hit: rows=%d", len(_mobile_base_rows_cache))
        return _clone_mobile_rows(_mobile_base_rows_cache)

    cfg = _get_ini_config()
    rows = get_mobile_display_rows(
        _get_tables_path(),
        scan_depth=get_scan_depth_from_config(cfg.config),
    )
    _mobile_base_rows_cache = _clone_mobile_rows(rows)
    logger.debug("Mobile rows cache miss: populated rows=%d", len(rows))
    return rows


async def _ensure_mobile_rows_loaded(
    state: dict,
    loading_container,
    loading_label,
    is_page_active: Callable[[], bool],
    render_rows: Callable[[list], None],
    error_context: str,
) -> None:
    global _mobile_base_rows_cache
    if state['loaded'] or state['loading']:
        return

    state['loading'] = True
    try:
        if _mobile_base_rows_cache is None:
            logger.info("Loading tables...")
            rows = await run.io_bound(_get_mobile_base_rows)
        else:
            rows = _get_mobile_base_rows()
        if not is_page_active():
            return
        loading_container.set_visibility(False)
        render_rows(rows)
        state['loaded'] = True
    except Exception as e:
        logger.exception('%s load failed', error_context)
        loading_label.set_text(f'Could not load tables: {e}')
    finally:
        state['loading'] = False


def _http_request(url, data=b'', method='POST', timeout=300, retries=3, conn=None):
    """Make an HTTP request matching VPinball's JS client behavior.
    Uses http.client directly to avoid urllib URL re-encoding issues.
    Pass a persistent conn (http.client.HTTPConnection) to reuse the TCP connection.
    """
    import time
    import http.client
    from urllib.parse import urlparse
    parsed = urlparse(url)
    own_conn = conn is None
    for attempt in range(retries):
        try:
            path_and_query = parsed.path
            if parsed.query:
                path_and_query += '?' + parsed.query
            if own_conn:
                conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
            conn.request(method, path_and_query, body=data, headers={
                'Host': f'{parsed.hostname}:{parsed.port}',
                'Connection': 'keep-alive',
                'Content-Length': str(len(data)),
            })
            resp = conn.getresponse()
            body = resp.read()
            if own_conn:
                conn.close()
            if resp.status >= 400:
                raise urllib.error.HTTPError(url, resp.status, resp.reason, dict(resp.getheaders()), None)
            return conn
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, OSError, http.client.RemoteDisconnected) as e:
            logger.warning("Connection error on attempt %s: %s: %s", attempt + 1, type(e).__name__, e)
            if not own_conn:
                # Reconnect the persistent connection
                try:
                    conn.close()
                except Exception:
                    pass
                conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
            if attempt < retries - 1:
                wait = 2 * (attempt + 1)
                logger.info("Retrying in %ss...", wait)
                time.sleep(wait)
            else:
                raise


def _send_table_to_device(
    host,
    port,
    table_dir_name,
    progress_cb=None,
    chunk_size=1048576,
    exclude_ini=True,
    copy_masked_tableini_as_default=False,
    masked_tableini_mask='',
):
    """Send all files in a table folder to the mobile device via its HTTP API.

    Protocol (Mongoose-based WebServer on mobile device):
      - POST /folder?q=<relative_dir>        -> create directory
      - POST /upload?q=<dir>&file=<name>&offset=<off>&length=<size>  -> upload file chunk
    """
    import http.client
    exclude_ini = _to_bool(exclude_ini)
    copy_masked_tableini_as_default = _to_bool(copy_masked_tableini_as_default)

    tables_path = _get_tables_path()
    table_path = os.path.join(tables_path, table_dir_name)
    base_url = f'http://{host}:{port}'

    if not os.path.isdir(table_path):
        raise FileNotFoundError(f"Table directory not found: {table_path}")

    masked_ini_name_for_copy = ''
    default_ini_name_for_copy = ''
    masked_ini_exists_for_copy = False
    primary_vpx_base_name = ''
    if copy_masked_tableini_as_default:
        mask = str(masked_tableini_mask or '').strip()
        if mask.lower().endswith('.ini'):
            mask = mask[:-4]
        mask = mask.strip().strip('.')
        if mask:
            try:
                root_entries = os.listdir(table_path)
            except Exception:
                root_entries = []
            root_vpx_files = sorted([f for f in root_entries if f.lower().endswith('.vpx')])
            if root_vpx_files:
                base_name = os.path.splitext(root_vpx_files[0])[0]
                primary_vpx_base_name = base_name
                expected_masked_ini_name = f'{base_name}.{mask}.ini'
                default_ini_name_for_copy = f'{base_name}.ini'
                entries_by_lower = {entry.lower(): entry for entry in root_entries}
                masked_ini_name_for_copy = entries_by_lower.get(
                    expected_masked_ini_name.lower(),
                    expected_masked_ini_name,
                )
                masked_ini_exists_for_copy = os.path.isfile(
                    os.path.join(table_path, masked_ini_name_for_copy)
                )
    else:
        # When the mobile rename-mask option is disabled, prefer the default
        # table ini and avoid sending masked table ini variants.
        try:
            root_entries = os.listdir(table_path)
        except Exception:
            root_entries = []
        root_vpx_files = sorted([f for f in root_entries if f.lower().endswith('.vpx')])
        if root_vpx_files:
            primary_vpx_base_name = os.path.splitext(root_vpx_files[0])[0]

    # Collect all files first to calculate total count
    all_files = []
    for dirpath, dirnames, filenames in os.walk(table_path):
        rel_dir = os.path.relpath(dirpath, tables_path)

        # For efficient lookup of corresponding .vpx files
        filenames_lower_set = {f.lower() for f in filenames}

        for fname in filenames:
            # When "Rename mask to default tableini" is enabled, don't send the
            # original masked ini; we optionally upload it only as the default ini name.
            if (
                masked_ini_name_for_copy
                and dirpath == table_path
                and fname.lower() == masked_ini_name_for_copy.lower()
            ):
                continue
            if (
                copy_masked_tableini_as_default
                and masked_ini_exists_for_copy
                and default_ini_name_for_copy
                and dirpath == table_path
                and fname.lower() == default_ini_name_for_copy.lower()
            ):
                # In mask-copy mode, when masked ini exists, suppress local default ini.
                # We'll inject masked content under default ini name below.
                continue

            # Exclude .ini files that have a matching .vpx file in the same directory
            if exclude_ini and fname.lower().endswith('.ini'):
                # Get the base name of the .ini file (without extension)
                base_name = os.path.splitext(fname)[0]
                # Check if a corresponding .vpx file exists in the same directory
                if f'{base_name.lower()}.vpx' in filenames_lower_set:
                    continue  # This is a table-specific .ini file, so exclude it
                # Also exclude suffix variants like:
                #   "Table Name.ini-win.ini"
                #   "Table Name.ini-lin.ini"
                # when "Table Name.vpx" exists in the same folder.
                base_lower = base_name.lower()
                marker = '.ini-'
                marker_pos = base_lower.find(marker)
                if marker_pos > 0:
                    vpx_base = base_name[:marker_pos]
                    if f'{vpx_base.lower()}.vpx' in filenames_lower_set:
                        continue

            full_path = os.path.join(dirpath, fname)
            file_size = os.path.getsize(full_path)
            all_files.append((rel_dir, fname, full_path, file_size))

    # Safety rule: when both options are OFF, transfer all .ini files as-is.
    if not exclude_ini and not copy_masked_tableini_as_default:
        existing_keys = {(rel_dir, fname.lower()) for rel_dir, fname, _, _ in all_files}
        for dirpath, _, filenames in os.walk(table_path):
            rel_dir = os.path.relpath(dirpath, tables_path)
            for fname in filenames:
                if not fname.lower().endswith('.ini'):
                    continue
                key = (rel_dir, fname.lower())
                if key in existing_keys:
                    continue
                full_path = os.path.join(dirpath, fname)
                file_size = os.path.getsize(full_path)
                all_files.append((rel_dir, fname, full_path, file_size))
                existing_keys.add(key)

    if copy_masked_tableini_as_default:
        if masked_ini_name_for_copy and default_ini_name_for_copy:
            masked_ini_path = os.path.join(table_path, masked_ini_name_for_copy)
            rel_root_dir = os.path.relpath(table_path, tables_path)

            default_already_in_file_list = any(
                rel_dir == rel_root_dir and fname.lower() == default_ini_name_for_copy.lower()
                for rel_dir, fname, _, _ in all_files
            )

            if os.path.isfile(masked_ini_path) and not default_already_in_file_list:
                all_files.append((
                    rel_root_dir,
                    default_ini_name_for_copy,
                    masked_ini_path,
                    os.path.getsize(masked_ini_path),
                ))
                logger.info(
                    "WebSend: using masked tableini '%s' as '%s' for transfer",
                    masked_ini_name_for_copy,
                    default_ini_name_for_copy,
                )

    total_files = len(all_files)
    if total_files == 0:
        return

    # Single persistent connection for the entire transfer
    conn = http.client.HTTPConnection(host, int(port), timeout=300)

    try:
        # Collect unique directories to create
        dirs_to_create = set()
        for dirpath, _, _ in os.walk(table_path):
            rel_dir = os.path.relpath(dirpath, tables_path)
            dirs_to_create.add(rel_dir)

        # Create directories (sorted so parents come first)
        for rel_dir in sorted(dirs_to_create):
            encoded_dir = urllib.parse.quote(rel_dir.replace(os.sep, '/'), safe='/')
            url = f'{base_url}/folder?q={encoded_dir}'
            try:
                conn = _http_request(url, data=b'', timeout=10, conn=conn)
            except urllib.error.HTTPError:
                pass

        CHUNK_SIZE = int(chunk_size)

        for i, (rel_dir, fname, full_path, file_size) in enumerate(all_files):
            if progress_cb:
                progress_cb(i, total_files, fname)

            encoded_dir = urllib.parse.quote(rel_dir.replace(os.sep, '/'), safe='/')
            encoded_file = urllib.parse.quote(fname, safe='')

            if file_size == 0:
                url = f'{base_url}/upload?offset=0&q={encoded_dir}&file={encoded_file}&length=0'
                conn = _http_request(url, data=b'', timeout=30, conn=conn)
            else:
                with open(full_path, 'rb') as f:
                    offset = 0
                    chunk_num = 0
                    total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
                    while offset < file_size:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        chunk_num += 1
                        url = f'{base_url}/upload?offset={offset}&q={encoded_dir}&file={encoded_file}&length={file_size}'
                        conn = _http_request(url, data=chunk, conn=conn)
                        offset += len(chunk)

        # Tell the mobile device to reload its table list
        try:
            conn = _http_request(f'{base_url}/command?cmd=refresh_tables', data=b'', timeout=10, conn=conn)
        except Exception:
            pass
    finally:
        conn.close()

    if progress_cb:
        progress_cb(total_files, total_files, 'Complete')


def _delete_table_from_device(host, port, table_dir_name):
    """Delete a table directory from the mobile device via POST /delete?q=<path>."""
    base_url = f'http://{host}:{port}'
    encoded_dir = urllib.parse.quote(table_dir_name, safe='')
    url = f'{base_url}/delete?q={encoded_dir}'
    _http_request(url, data=b'', timeout=30)
    # Tell the mobile device to reload its table list
    try:
        _http_request(f'{base_url}/command?cmd=refresh_tables', data=b'', timeout=10)
    except Exception:
        pass


def build(standalone=True):
    global _mobile_page_client, _mobile_active_tab, _mobile_render_id, _mobile_tabs_ref
    try:
        _mobile_page_client = context.client
    except Exception:
        _mobile_page_client = None

    _mobile_render_id += 1
    current_render_id = _mobile_render_id

    def is_page_active() -> bool:
        return _mobile_render_id == current_render_id

    ui.dark_mode(value=True)

    if standalone:
        ui.add_head_html('''
        <style>
            body {
                margin: 0 !important;
                padding: 0 !important;
                background-color: #111827 !important;
            }
        </style>
        ''')

    with ui.column().classes('w-full items-center p-4'):
        ui.label('VPinFE Mobile').classes('text-2xl font-bold text-white mb-4')

        try:
            stored_tab = app.storage.user.get('mobile_active_tab', 'websend')
        except Exception:
            stored_tab = 'websend'
        initial_tab = _normalize_tab_key(stored_tab)
        _mobile_active_tab = initial_tab

        try:
            stored_pag = app.storage.user.get('mobile_pagination_states', {})
            if isinstance(stored_pag, dict):
                for _tab_key in ('websend', 'vpxz'):
                    _val = stored_pag.get(_tab_key)
                    if _val is not None:
                        persisted = _normalize_pagination_state(_val)
                        _mobile_pagination_states[_tab_key] = {
                            **_mobile_pagination_states[_tab_key],
                            'rowsPerPage': persisted['rowsPerPage'],
                        }
        except Exception as e:
            logger.error(f"Error loading mobile pagination state: {e}")

        with ui.tabs(value=initial_tab).classes('w-full').props('dark') as tabs:
            websend_tab = ui.tab('Web Send').props('name=websend')
            vpxz_tab = ui.tab('VPXZ Download').props('name=vpxz')
        _mobile_tabs_ref = tabs

        async def _handle_tab_change(new_value) -> None:
            global _mobile_active_tab
            if not is_page_active():
                return
            new_tab = _normalize_tab_key(new_value)
            old_tab = _normalize_tab_key(_mobile_active_tab)
            if new_tab == old_tab:
                return
            await _capture_tab_scroll_state(old_tab)
            _mobile_active_tab = new_tab
            try:
                app.storage.user['mobile_active_tab'] = new_tab
            except Exception:
                pass
            if new_tab == 'websend':
                await ensure_websend_loaded()
            elif new_tab == 'vpxz':
                await ensure_vpxz_loaded()
            if is_page_active():
                _restore_tab_scroll_state(new_tab)

        tabs.on_value_change(lambda e: asyncio.create_task(_handle_tab_change(e.value)))

        with ui.tab_panels(tabs, value=initial_tab).classes('w-full').props('dark'):

            # ── Web Send Tab ──
            with ui.tab_panel('websend'):
                ensure_websend_loaded = _build_web_send_panel(is_page_active, dict(_mobile_pagination_states['websend']))

            # ── VPXZ Download Tab ──
            with ui.tab_panel('vpxz'):
                ensure_vpxz_loaded = _build_vpxz_download_panel(is_page_active, dict(_mobile_pagination_states['vpxz']))

        async def _load_initial_tab() -> None:
            if not is_page_active():
                return
            if initial_tab == 'websend':
                await ensure_websend_loaded()
                if is_page_active():
                    await ensure_vpxz_loaded()
            else:
                await ensure_vpxz_loaded()
                if is_page_active():
                    await ensure_websend_loaded()
            if is_page_active():
                _restore_tab_scroll_state(initial_tab)

        ui.timer(0.1, lambda: asyncio.create_task(_load_initial_tab()) if is_page_active() else None, once=True)


def _build_vpxz_download_panel(is_page_active: Callable[[], bool] = lambda: True, initial_pagination: dict | None = None):
    table_container = ui.column().classes('w-full')
    pagination_state = _normalize_pagination_state(initial_pagination)

    def _render_table(rows):
        columns = [
            {'name': 'display_name', 'label': 'Table', 'field': 'display_name', 'align': 'left', 'sortable': True},
        ]
        with table_container:
            tbl = ui.table(
                columns=columns,
                rows=rows,
                row_key='table_dir_name',
                pagination=dict(pagination_state),
            ).classes('w-full mobile-vpxz-table').props('dark dense rows-per-page-label="Rows per page" :rows-per-page-options="[100, 200, 500, 0]"')

            def on_vpxz_pagination_change(e):
                merged = dict(tbl._props.get('pagination', {}))
                merged.update(_extract_pagination(e.args))
                normalized = _normalize_pagination_state(merged)
                tbl._props['pagination'] = dict(normalized)
                _save_mobile_pagination_state('vpxz', normalized)

            tbl.on('update:pagination', on_vpxz_pagination_change)

            tbl.add_slot('body-cell-display_name', '''
                <q-td :props="props">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <q-btn flat dense icon="download" color="blue" class="q-mr-sm"
                            @click.stop="$parent.$emit('download', props.row)" />
                        {{ props.row.display_name }}
                    </div>
                </q-td>
            ''')

            async def handle_download(e):
                name = e.args['table_dir_name']
                with ui.dialog() as dlg, ui.card().classes('bg-gray-800 p-6'):
                    with ui.row().classes('items-center gap-3'):
                        ui.spinner('dots', size='48px', color='blue')
                        ui.label(f'Preparing {name}.vpxz ...').classes('text-white')
                dlg.open()

                def create_zip():
                    tables_path = _get_tables_path()
                    tmp_dir = tempfile.mkdtemp()
                    zip_base = os.path.join(tmp_dir, name)
                    zip_path = shutil.make_archive(zip_base, 'zip', root_dir=tables_path, base_dir=name)
                    vpxz_path = zip_base + '.vpxz'
                    os.rename(zip_path, vpxz_path)
                    logger.info("Created download archive: %s", vpxz_path)
                    with open(vpxz_path, 'rb') as f:
                        data = f.read()
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    return data

                zip_bytes = await run.io_bound(create_zip)
                dlg.close()
                ui.download(zip_bytes, f'{name}.vpxz')

            tbl.on('download', handle_download)

    state = {'loaded': False, 'loading': False}
    loading_container = ui.row().classes('items-center gap-2 text-gray-400')
    with loading_container:
        ui.spinner('dots', size='24px', color='blue')
        loading = ui.label('Loading tables...').classes('text-gray-400')

    async def ensure_loaded():
        await _ensure_mobile_rows_loaded(
            state,
            loading_container,
            loading,
            is_page_active,
            _render_table,
            'Mobile VPXZ',
        )

    return ensure_loaded


def _fetch_device_folders(host, port):
    """Fetch the list of top-level folder names from the mobile device via GET /files."""
    url = f'http://{host}:{port}/files'
    req = urllib.request.Request(url, method='GET')
    req.add_header('Connection', 'close')
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode('utf-8'))
    resp.close()
    # Return set of directory names
    return {entry['name'] for entry in data if entry.get('isDir', False)}


def _build_web_send_panel(is_page_active: Callable[[], bool] = lambda: True, initial_pagination: dict | None = None):
    # Load saved connection settings from ini
    cfg = _get_ini_config()
    pagination_state = _normalize_pagination_state(initial_pagination)
    saved_ip = cfg.config.get('Mobile', 'deviceip', fallback='').strip()
    saved_port = cfg.config.get('Mobile', 'deviceport', fallback='2112').strip()
    saved_chunk = cfg.config.get('Mobile', 'chunksize', fallback='1048576').strip()
    saved_rename_mask = cfg.config.get('Mobile', 'renamemasktodefaultini', fallback='false').strip().lower() == 'true'
    saved_rename_mask_value = cfg.config.get('Mobile', 'renamemasktodefaultinimask', fallback='').strip()

    def _save_ip(e):
        ip_val = e.value.strip() if e.value else ''
        cfg.config.set('Mobile', 'deviceip', ip_val)
        cfg.save()

    def _save_port(e):
        port_val = e.value.strip() if e.value else '2112'
        cfg.config.set('Mobile', 'deviceport', port_val)
        cfg.save()

    def _save_chunk(e):
        chunk_val = e.value.strip() if e.value else '1048576'
        cfg.config.set('Mobile', 'chunksize', chunk_val)
        cfg.save()

    def _save_rename_mask_enabled(e):
        enabled_val = bool(e.value)
        cfg.config.set('Mobile', 'renamemasktodefaultini', str(enabled_val).lower())
        cfg.save()

    def _save_rename_mask_value(e):
        mask_val = e.value.strip() if e.value else ''
        cfg.config.set('Mobile', 'renamemasktodefaultinimask', mask_val)
        cfg.save()

    ui.label("This uses the the built in web server on the mobile version of vpx for Android and iOS. It allows you seamlessly transfer your tables onto your mobile device.  You must turn it on in the settings in VPX on your mobile device.  Also note this same location will show you your IP and PORT.  Thats what you put into the device configuration settings below.  The device must be kept on and VPX running when doing transfers. ").classes('text-gray-400 text-sm mb-4')

    # Connection settings
    with ui.card().classes('w-full bg-gray-800 p-4 mb-4'):
        ui.label('Device Connection').classes('text-white font-bold mb-2')
        with ui.row().classes('items-end gap-4 w-full'):
            ip_input = ui.input('IP Address', value=saved_ip, on_change=_save_ip).props('dark outlined dense').classes('flex-grow')
            port_input = ui.input('Port', value=saved_port, on_change=_save_port).props('dark outlined dense').style('max-width: 100px;')
            chunk_input = ui.input('Chunk Size (bytes)', value=saved_chunk, on_change=_save_chunk).props('dark outlined dense').style('max-width: 160px;')
            check_btn = ui.button('Check Device', icon='sync', on_click=lambda: check_device()) \
                .props('dense outline').classes('text-white')

    # Send Options
    with ui.card().classes('w-full bg-gray-800 p-4 mb-4'):
        ui.label('Send Options').classes('text-white font-bold mb-2')
        exclude_ini_checkbox = ui.checkbox('Exclude {VPX_FILENAME}.ini files', value=True).props('dark')
        ui.label("Prevents sending the table-specific configuration file, e.g. 'tablename.ini'.").classes('text-gray-400 text-xs ml-8 -mt-2')
        with ui.row().classes('w-full items-end gap-3'):
            masked_ini_copy_checkbox = ui.checkbox(
                'Enable Rename Mask To Default INI',
                value=saved_rename_mask,
                on_change=_save_rename_mask_enabled,
            ).props('dark')
            masked_ini_input = ui.input(
                'Rename Mask',
                value=saved_rename_mask_value,
                on_change=_save_rename_mask_value,
            ).props('dark outlined dense').style('min-width: 180px; max-width: 280px;')
        ui.label(
            'If mask exists, sends {VPX_FILENAME}.{MASK}.ini as {VPX_FILENAME}.ini when default ini is missing.'
        ).classes('text-gray-400 text-xs ml-8 -mt-2')

    # Action bar: filter toggle + send selected
    with ui.row().classes('w-full items-center gap-4 mb-2'):
        filter_toggle = ui.button('Show Installed Only', icon='filter_list',
                                  on_click=lambda: toggle_filter()) \
            .props('dense outline').classes('text-white')
        send_selected_btn = ui.button('Send Selected', icon='send',
                                      on_click=lambda: batch_send()) \
            .props('dense').classes('text-white bg-green-800')

    loading_container = ui.row().classes('items-center gap-2 text-gray-400')
    with loading_container:
        ui.spinner('dots', size='24px', color='blue')
        loading = ui.label('Loading tables...').classes('text-gray-400')
    table_container = ui.column().classes('w-full')
    state = {'loaded': False, 'loading': False}

    # Shared state for the table reference and device folders
    panel_state = {
        'tbl': None, 'rows': [], 'device_folders': set(),
        'filter_installed': False,
    }

    def _apply_filter():
        if not panel_state['tbl']:
            return
        if panel_state['filter_installed']:
            filtered = [r for r in panel_state['rows'] if r.get('installed')]
        else:
            filtered = panel_state['rows']
        panel_state['tbl'].rows = filtered
        panel_state['tbl'].selected.clear()
        panel_state['tbl'].update()

    def toggle_filter():
        panel_state['filter_installed'] = not panel_state['filter_installed']
        if panel_state['filter_installed']:
            filter_toggle.props(add='color=blue')
            filter_toggle._text = 'Show All'
            filter_toggle.update()
        else:
            filter_toggle.props(remove='color=blue')
            filter_toggle._text = 'Show Installed Only'
            filter_toggle.update()
        _apply_filter()

    async def check_device():
        if not is_page_active():
            return
        host = ip_input.value.strip()
        port = port_input.value.strip()
        if not host or not port:
            ui.notify('Please enter IP and Port', type='warning')
            return
        try:
            folders = await run.io_bound(lambda: _fetch_device_folders(host, port))
            if not is_page_active():
                return
            panel_state['device_folders'] = folders
            # Update rows with installed status
            for row in panel_state['rows']:
                row['installed'] = row['table_dir_name'] in folders
            _apply_filter()
            installed_count = sum(1 for r in panel_state['rows'] if r.get('installed'))
            ui.notify(f'Found {installed_count} of {len(panel_state["rows"])} tables on device', type='info')
        except Exception as e:
            ui.notify(f'Could not connect: {e}', type='negative')

    async def _send_single_table(host, port, name, exclude_ini, masked_ini_copy_enabled, masked_ini_mask):
        """Send a single table with progress dialog. Returns True on success."""
        # Progress dialog
        with ui.dialog() as dlg, ui.card().classes('bg-gray-800 p-6').style('min-width: 400px;'):
            with ui.column().classes('w-full gap-3'):
                ui.label(f'Sending {name}').classes('text-white font-bold text-lg')
                progress_bar = ui.linear_progress(value=0, show_value=False).classes('w-full')
                status_label = ui.label('Connecting...').classes('text-gray-400 text-sm')
                file_label = ui.label('').classes('text-gray-500 text-xs')
        dlg.props('persistent')
        dlg.open()

        state = {'current': 0, 'total': 0, 'file': '', 'done': False, 'error': None}

        def progress_cb(current, total, filename):
            state['current'] = current
            state['total'] = total
            state['file'] = filename

        def do_send():
            try:
                cs = int(chunk_input.value.strip() or '1048576')
                _send_table_to_device(
                    host,
                    port,
                    name,
                    progress_cb=progress_cb,
                    chunk_size=cs,
                    exclude_ini=exclude_ini,
                    copy_masked_tableini_as_default=masked_ini_copy_enabled,
                    masked_tableini_mask=masked_ini_mask,
                )
                state['done'] = True
            except Exception as ex:
                state['error'] = str(ex)
                logger.exception("WebSend error")

        async def update_progress():
            if state['error']:
                progress_bar.set_value(1)
                status_label.set_text(f"Error: {state['error']}")
                file_label.set_text('')
                progress_timer.deactivate()
                await run.io_bound(lambda: None)  # yield
                dlg.props(remove='persistent')
                return
            if state['total'] > 0:
                pct = state['current'] / state['total']
                progress_bar.set_value(pct)
                status_label.set_text(f"Uploading file {state['current']}/{state['total']}")
                file_label.set_text(state['file'])
            if state['done']:
                progress_timer.deactivate()
                dlg.close()

        progress_timer = ui.timer(0.3, update_progress)
        await run.io_bound(do_send)
        return state['error'] is None

    async def batch_send():
        if not panel_state['tbl'] or not panel_state['tbl'].selected:
            ui.notify('No tables selected', type='warning')
            return
        host = ip_input.value.strip()
        port = port_input.value.strip()
        if not host or not port:
            ui.notify('Please enter IP and Port', type='warning')
            return

        exclude_ini = exclude_ini_checkbox.value
        exclude_ini = _to_bool(exclude_ini)
        masked_ini_copy_enabled = _to_bool(masked_ini_copy_checkbox.value)
        masked_ini_mask = (masked_ini_input.value or '').strip()
        selected = list(panel_state['tbl'].selected)
        total = len(selected)
        success = 0
        for i, row in enumerate(selected):
            name = row['table_dir_name']
            ui.notify(f'Batch send: {i+1}/{total} - {name}', type='info')
            ok = await _send_single_table(
                host,
                port,
                name,
                exclude_ini=exclude_ini,
                masked_ini_copy_enabled=masked_ini_copy_enabled,
                masked_ini_mask=masked_ini_mask,
            )
            if ok:
                success += 1
        ui.notify(f'Batch complete: {success}/{total} tables sent', type='positive')
        panel_state['tbl'].selected.clear()
        panel_state['tbl'].update()
        await check_device()

    async def load_tables():
        def render_rows(rows):
            loading_container.set_visibility(False)
            rows_per_page = pagination_state.get('rowsPerPage', 100)
            current_page = pagination_state.get('page', 1)
            if rows_per_page == 0:
                initial_row_count = len(rows)
            else:
                initial_row_count = rows_per_page * current_page
            initial_rows = rows[:initial_row_count]
            # Add installed field
            for row in rows:
                row['installed'] = False
            panel_state['rows'] = rows

            columns = [
                {'name': 'display_name', 'label': 'Table', 'field': 'display_name', 'align': 'left', 'sortable': True},
            ]

            with table_container:
                tbl = ui.table(
                    columns=columns,
                    rows=initial_rows,
                    row_key='table_dir_name',
                    selection='multiple',
                    pagination=dict(pagination_state),
                ).classes('w-full mobile-websend-table').props('dark dense rows-per-page-label="Rows per page" :rows-per-page-options="[100, 200, 500, 0]"')
                panel_state['tbl'] = tbl

                def on_websend_pagination_change(e):
                    merged = dict(tbl._props.get('pagination', {}))
                    merged.update(_extract_pagination(e.args))
                    normalized = _normalize_pagination_state(merged)
                    tbl._props['pagination'] = dict(normalized)
                    _save_mobile_pagination_state('websend', normalized)

                tbl.on('update:pagination', on_websend_pagination_change)

                tbl.add_slot('body-cell-display_name', '''
                    <q-td :props="props">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <q-btn v-if="!props.row.installed" flat dense icon="send" color="green" class="q-mr-sm"
                                @click.stop="$parent.$emit('websend', props.row)" />
                            <q-btn v-if="props.row.installed" flat dense icon="delete" color="red" class="q-mr-sm"
                                @click.stop="$parent.$emit('webdelete', props.row)" />
                            <q-icon v-if="props.row.installed" name="check_circle" color="light-green" class="q-mr-xs" />
                            <span :style="props.row.installed ? 'color: #81c784;' : ''">
                                {{ props.row.display_name }}
                            </span>
                        </div>
                    </q-td>
                ''')

            async def handle_send(e):
                name = e.args['table_dir_name']
                host = ip_input.value.strip()
                port = port_input.value.strip()

                if not host or not port:
                    ui.notify('Please enter IP and Port', type='warning')
                    return

                exclude_ini = exclude_ini_checkbox.value
                exclude_ini = _to_bool(exclude_ini)
                masked_ini_copy_enabled = _to_bool(masked_ini_copy_checkbox.value)
                masked_ini_mask = (masked_ini_input.value or '').strip()
                ok = await _send_single_table(
                    host,
                    port,
                    name,
                    exclude_ini=exclude_ini,
                    masked_ini_copy_enabled=masked_ini_copy_enabled,
                    masked_ini_mask=masked_ini_mask,
                )
                if ok:
                    ui.notify(f'Transfer complete! All files sent to {host}:{port}', type='positive')
                    await check_device()

            tbl.on('websend', handle_send)

            async def handle_delete(e):
                name = e.args['table_dir_name']
                host = ip_input.value.strip()
                port = port_input.value.strip()

                if not host or not port:
                    ui.notify('Please enter IP and Port', type='warning')
                    return

                with ui.dialog() as dlg, ui.card().classes('bg-gray-800 p-6'):
                    ui.label(f'Delete "{name}" from device?').classes('text-white font-bold')
                    ui.label('This will permanently remove the table from the mobile device.').classes('text-gray-400 text-sm')
                    with ui.row().classes('w-full justify-end gap-2 mt-4'):
                        ui.button('Cancel', on_click=dlg.close).props('flat').classes('text-white')
                        ui.button('Delete', on_click=lambda: dlg.submit(True)).props('color=red')
                dlg.open()
                result = await dlg
                if not result:
                    return

                try:
                    await run.io_bound(lambda: _delete_table_from_device(host, port, name))
                    ui.notify(f'Deleted "{name}" from device', type='positive')
                    await check_device()
                except Exception as ex:
                    ui.notify(f'Delete failed: {ex}', type='negative')

            tbl.on('webdelete', handle_delete)

            async def hydrate_full_rows():
                await asyncio.sleep(0)
                if not is_page_active():
                    return
                _apply_filter()

            asyncio.create_task(hydrate_full_rows())

        await _ensure_mobile_rows_loaded(
            state,
            loading_container,
            loading,
            is_page_active,
            render_rows,
            'Mobile WebSend',
        )

    async def ensure_loaded() -> None:
        await load_tables()

    return ensure_loaded
