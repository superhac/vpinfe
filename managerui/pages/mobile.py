import os
import json
import shutil
import tempfile
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from nicegui import ui, run
from platformdirs import user_config_dir

from common.iniconfig import IniConfig

CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
VPINFE_INI_PATH = CONFIG_DIR / 'vpinfe.ini'

_INI_CFG = None


def _get_ini_config():
    global _INI_CFG
    if _INI_CFG is None:
        _INI_CFG = IniConfig(str(VPINFE_INI_PATH))
    return _INI_CFG


def _get_tables_path() -> str:
    try:
        cfg = _get_ini_config()
        tableroot = cfg.config.get('Settings', 'tablerootdir', fallback='').strip()
        if tableroot:
            return os.path.expanduser(tableroot)
    except Exception:
        pass
    return os.path.expanduser('~/tables')


def _scan_tables():
    """Scan for tables with .info and .vpx files, return list of dicts."""
    tables_path = _get_tables_path()
    tables = []

    if not os.path.exists(tables_path):
        return tables

    for root, _, files in os.walk(tables_path):
        current_dir = os.path.basename(root)
        info_file = f"{current_dir}.info"

        if info_file in files:
            vpx_files = [f for f in files if f.lower().endswith('.vpx')]
            if not vpx_files:
                continue

            meta_path = os.path.join(root, info_file)
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)

                info = raw.get("Info", {})
                name = (info.get("Title") or current_dir).strip()
                manufacturer = info.get("Manufacturer", "")
                year = info.get("Year", "")

                tables.append({
                    'name': name,
                    'manufacturer': manufacturer,
                    'year': str(year) if year else '',
                    'table_dir_name': current_dir,
                    'table_path': root,
                })
            except Exception:
                pass

    tables.sort(key=lambda t: t['name'].lower())
    return tables


def _build_table_rows(tables):
    """Build display rows from scanned tables."""
    rows = []
    for t in tables:
        parts = [p for p in [t['manufacturer'], t['year']] if p]
        display = f"{t['name']} ({' '.join(parts)})" if parts else t['name']
        rows.append({
            'display_name': display,
            'table_dir_name': t['table_dir_name'],
        })
    return rows


def _http_request(url, data=b'', method='POST', timeout=300, retries=3):
    """Make an HTTP request matching VPinball's JS client behavior.
    Uses http.client directly to avoid urllib URL re-encoding issues.
    """
    import time
    import http.client
    from urllib.parse import urlparse
    parsed = urlparse(url)
    for attempt in range(retries):
        try:
            path_and_query = parsed.path
            if parsed.query:
                path_and_query += '?' + parsed.query
            print(f"[WebSend] {method} {url} (data={len(data)} bytes, attempt {attempt+1}/{retries})")
            print(f"[WebSend] Raw request line: {method} {path_and_query} HTTP/1.1")
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
            conn.request(method, path_and_query, body=data, headers={
                'Host': f'{parsed.hostname}:{parsed.port}',
                'Connection': 'close',
                'Content-Length': str(len(data)),
            })
            resp = conn.getresponse()
            body = resp.read()
            print(f"[WebSend] Response: {resp.status} {resp.reason}, body={body[:200]}")
            conn.close()
            if resp.status >= 400:
                print(f"[WebSend] HTTPError {resp.status} {resp.reason} for {url}")
                print(f"[WebSend] Response headers: {dict(resp.getheaders())}")
                print(f"[WebSend] Error body: {body.decode('utf-8', errors='replace')[:500]}")
                raise urllib.error.HTTPError(url, resp.status, resp.reason, dict(resp.getheaders()), None)
            return resp
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, OSError, http.client.RemoteDisconnected) as e:
            print(f"[WebSend] Connection error: {type(e).__name__}: {e}")
            if attempt < retries - 1:
                wait = 2 * (attempt + 1)
                print(f"[WebSend] Retrying in {wait}s... (attempt {attempt+2}/{retries})")
                time.sleep(wait)
            else:
                raise


def _send_table_to_device(host, port, table_dir_name, progress_cb=None):
    """Send all files in a table folder to the mobile device via its HTTP API.

    Protocol (Mongoose-based WebServer on mobile device):
      - POST /folder?q=<relative_dir>        -> create directory
      - POST /upload?q=<dir>&file=<name>&offset=<off>&length=<size>  -> upload file chunk
    """
    tables_path = _get_tables_path()
    table_path = os.path.join(tables_path, table_dir_name)
    base_url = f'http://{host}:{port}'

    if not os.path.isdir(table_path):
        raise FileNotFoundError(f"Table directory not found: {table_path}")

    # Collect all files first to calculate total count
    all_files = []
    for dirpath, dirnames, filenames in os.walk(table_path):
        rel_dir = os.path.relpath(dirpath, tables_path)
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            file_size = os.path.getsize(full_path)
            all_files.append((rel_dir, fname, full_path, file_size))

    total_files = len(all_files)
    if total_files == 0:
        return

    # Collect unique directories to create
    dirs_to_create = set()
    for dirpath, _, _ in os.walk(table_path):
        rel_dir = os.path.relpath(dirpath, tables_path)
        dirs_to_create.add(rel_dir)

    # Create directories (sorted so parents come first)
    # Match JS client: encodeURIComponent encodes everything including /
    for rel_dir in sorted(dirs_to_create):
        encoded_dir = urllib.parse.quote(rel_dir, safe='')
        url = f'{base_url}/folder?q={encoded_dir}'
        try:
            _http_request(url, data=b'', timeout=10)
            print(f"[WebSend] Created folder: {rel_dir}")
        except urllib.error.HTTPError as e:
            print(f"[WebSend] Folder create response {e.code} for {rel_dir}")

    # Upload each file in 512KB chunks (matches VPinball JS client: 1024 * 512)
    CHUNK_SIZE = 1024 * 512  # 512KB - same as official VPinball web client

    for i, (rel_dir, fname, full_path, file_size) in enumerate(all_files):
        if progress_cb:
            progress_cb(i, total_files, fname)

        # Match JS client URL format: /upload?offset=N&q=DIR&file=NAME&length=TOTAL
        encoded_dir = urllib.parse.quote(rel_dir, safe='')
        encoded_file = urllib.parse.quote(fname, safe='')

        print(f"[WebSend] Uploading ({i+1}/{total_files}): {rel_dir}/{fname} ({file_size} bytes)")
        if file_size == 0:
            url = f'{base_url}/upload?offset=0&q={encoded_dir}&file={encoded_file}&length=0'
            _http_request(url, data=b'', timeout=30)
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
                    print(f"[WebSend]   Chunk {chunk_num}/{total_chunks}: offset={offset}, chunk_size={len(chunk)}, file_size={file_size}")
                    url = f'{base_url}/upload?offset={offset}&q={encoded_dir}&file={encoded_file}&length={file_size}'
                    _http_request(url, data=chunk)
                    offset += len(chunk)

        print(f"[WebSend] Done ({i+1}/{total_files}): {rel_dir}/{fname}")

    # Tell the mobile device to reload its table list
    try:
        _http_request(f'{base_url}/command?cmd=refresh_tables', data=b'', timeout=10)
        print("[WebSend] Sent refresh_tables command to device")
    except Exception as e:
        print(f"[WebSend] Warning: refresh_tables command failed: {e}")

    if progress_cb:
        progress_cb(total_files, total_files, 'Complete')


def build(standalone=True):
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

        with ui.tabs().classes('w-full').props('dark') as tabs:
            websend_tab = ui.tab('Web Send')
            vpxz_tab = ui.tab('VPXZ Download')

        with ui.tab_panels(tabs, value=websend_tab).classes('w-full').props('dark'):

            # ── Web Send Tab ──
            with ui.tab_panel(websend_tab):
                _build_web_send_panel()

            # ── VPXZ Download Tab ──
            with ui.tab_panel(vpxz_tab):
                _build_vpxz_download_panel()


def _build_vpxz_download_panel():
    loading = ui.label('Loading tables...').classes('text-gray-400')
    table_container = ui.column().classes('w-full')

    async def load_tables():
        tables = await run.io_bound(_scan_tables)
        loading.set_visibility(False)
        rows = _build_table_rows(tables)

        columns = [
            {'name': 'display_name', 'label': 'Table', 'field': 'display_name', 'align': 'left', 'sortable': True},
        ]

        with table_container:
            tbl = ui.table(
                columns=columns,
                rows=rows,
                row_key='table_dir_name',
                pagination={'rowsPerPage': 25},
            ).classes('w-full').props('dark dense')

            tbl.add_slot('body-cell-display_name', '''
                <q-td :props="props">
                    <q-btn flat dense icon="download" color="blue" class="q-mr-sm"
                        @click.stop="$parent.$emit('download', props.row)" />
                    {{ props.row.display_name }}
                </q-td>
            ''')

            async def handle_download(e):
                name = e.args['table_dir_name']

                with ui.dialog() as dlg, ui.card().classes('bg-gray-800 p-6'):
                    with ui.row().classes('items-center gap-3'):
                        ui.spinner(size='lg')
                        ui.label(f'Preparing {name}.vpxz ...').classes('text-white')
                dlg.open()

                def create_zip():
                    tables_path = _get_tables_path()
                    tmp_dir = tempfile.mkdtemp()
                    zip_base = os.path.join(tmp_dir, name)
                    zip_path = shutil.make_archive(zip_base, 'zip', root_dir=tables_path, base_dir=name)
                    vpxz_path = zip_base + '.vpxz'
                    os.rename(zip_path, vpxz_path)
                    print(f"[Mobile] Created download archive: {vpxz_path}")
                    with open(vpxz_path, 'rb') as f:
                        data = f.read()
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    print(f"[Mobile] Cleaned up temp archive: {tmp_dir}")
                    return data

                zip_bytes = await run.io_bound(create_zip)
                dlg.close()
                ui.download(zip_bytes, f'{name}.vpxz')

            tbl.on('download', handle_download)

    ui.timer(0.1, load_tables, once=True)


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


def _build_web_send_panel():
    # Load saved connection settings from ini
    cfg = _get_ini_config()
    saved_ip = cfg.config.get('Mobile', 'deviceip', fallback='').strip()
    saved_port = cfg.config.get('Mobile', 'deviceport', fallback='2112').strip()

    def _save_ip(e):
        ip_val = e.value.strip() if e.value else ''
        cfg.config.set('Mobile', 'deviceip', ip_val)
        cfg.save()

    def _save_port(e):
        port_val = e.value.strip() if e.value else '2112'
        cfg.config.set('Mobile', 'deviceport', port_val)
        cfg.save()

    ui.label("This uses the the built in web server on the mobile version of vpx for Android and iOS. It allows you seamlessly transfer your tables onto your mobile device.  You must turn it on in the settings in VPX on your mobile device.  Also note this same location will show you your IP and PORT.  Thats what you put into the device configuration settings below.  The device must be kept on and VPX running when doing transfers. ").classes('text-gray-400 text-sm mb-4')

    # Connection settings
    with ui.card().classes('w-full bg-gray-800 p-4 mb-4'):
        ui.label('Device Connection').classes('text-white font-bold mb-2')
        with ui.row().classes('items-end gap-4 w-full'):
            ip_input = ui.input('IP Address', value=saved_ip, on_change=_save_ip).props('dark outlined dense').classes('flex-grow')
            port_input = ui.input('Port', value=saved_port, on_change=_save_port).props('dark outlined dense').style('max-width: 100px;')
            check_btn = ui.button('Check Device', icon='sync', on_click=lambda: check_device()) \
                .props('dense outline').classes('text-white')

    # Action bar: filter toggle + send selected
    with ui.row().classes('w-full items-center gap-4 mb-2'):
        filter_toggle = ui.button('Show Installed Only', icon='filter_list',
                                  on_click=lambda: toggle_filter()) \
            .props('dense outline').classes('text-white')
        send_selected_btn = ui.button('Send Selected', icon='send',
                                      on_click=lambda: batch_send()) \
            .props('dense').classes('text-white bg-green-800')

    loading = ui.label('Loading tables...').classes('text-gray-400')
    table_container = ui.column().classes('w-full')

    # Shared state for the table reference and device folders
    panel_state = {
        'tbl': None, 'rows': [], 'device_folders': set(),
        'filter_installed': False,
    }

    def _apply_filter():
        if not panel_state['tbl']:
            return
        if panel_state['filter_installed']:
            filtered = [dict(r) for r in panel_state['rows'] if r.get('installed')]
        else:
            filtered = [dict(r) for r in panel_state['rows']]
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
        host = ip_input.value.strip()
        port = port_input.value.strip()
        if not host or not port:
            ui.notify('Please enter IP and Port', type='warning')
            return
        try:
            folders = await run.io_bound(lambda: _fetch_device_folders(host, port))
            panel_state['device_folders'] = folders
            # Update rows with installed status
            for row in panel_state['rows']:
                row['installed'] = row['table_dir_name'] in folders
            _apply_filter()
            installed_count = sum(1 for r in panel_state['rows'] if r.get('installed'))
            ui.notify(f'Found {installed_count} of {len(panel_state["rows"])} tables on device', type='info')
        except Exception as e:
            ui.notify(f'Could not connect: {e}', type='negative')

    async def _send_single_table(host, port, name):
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
                _send_table_to_device(host, port, name, progress_cb=progress_cb)
                state['done'] = True
            except Exception as ex:
                state['error'] = str(ex)
                print(f"[WebSend] Error: {ex}")

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

        selected = list(panel_state['tbl'].selected)
        total = len(selected)
        success = 0
        for i, row in enumerate(selected):
            name = row['table_dir_name']
            ui.notify(f'Batch send: {i+1}/{total} - {name}', type='info')
            ok = await _send_single_table(host, port, name)
            if ok:
                success += 1
        ui.notify(f'Batch complete: {success}/{total} tables sent', type='positive')
        panel_state['tbl'].selected.clear()
        panel_state['tbl'].update()
        await check_device()

    async def load_tables():
        tables = await run.io_bound(_scan_tables)
        loading.set_visibility(False)
        rows = _build_table_rows(tables)
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
                rows=rows,
                row_key='table_dir_name',
                selection='multiple',
                pagination={'rowsPerPage': 25},
            ).classes('w-full').props('dark dense')
            panel_state['tbl'] = tbl

            tbl.add_slot('body-cell-display_name', '''
                <q-td :props="props">
                    <q-btn flat dense icon="send" color="green" class="q-mr-sm"
                        @click.stop="$parent.$emit('websend', props.row)" />
                    <q-icon v-if="props.row.installed" name="check_circle" color="light-green" class="q-mr-xs" />
                    <span :style="props.row.installed ? 'color: #81c784;' : ''">
                        {{ props.row.display_name }}
                    </span>
                </q-td>
            ''')

            async def handle_send(e):
                name = e.args['table_dir_name']
                host = ip_input.value.strip()
                port = port_input.value.strip()

                if not host or not port:
                    ui.notify('Please enter IP and Port', type='warning')
                    return

                ok = await _send_single_table(host, port, name)
                if ok:
                    ui.notify(f'Transfer complete! All files sent to {host}:{port}', type='positive')
                    await check_device()

            tbl.on('websend', handle_send)

        # Auto-check device after tables load if IP is configured
        if saved_ip:
            await check_device()

    ui.timer(0.1, load_tables, once=True)
