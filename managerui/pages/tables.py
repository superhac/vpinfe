import os
import configparser
import logging
import asyncio
from nicegui import ui, events, run, context
from pathlib import Path
import json
from typing import List, Dict, Optional, Callable
from common.vpxparser import VPXParser
from clioptions import buildMetaData, vpxPatches
from queue import Queue
from platformdirs import user_config_dir

# Resolve project root and important paths explicitly
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VPSDB_JSON_PATH = PROJECT_ROOT / 'vpsdb.json'
CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
VPINFE_INI_PATH = CONFIG_DIR / 'vpinfe.ini'

# Load vpinfe.ini once to avoid repeated parsing
from common.iniconfig import IniConfig
_INI_CFG = IniConfig(str(VPINFE_INI_PATH))

#_vpsdb_cache: List[Dict] | None = None
_vpsdb_cache: Optional[List[Dict]] = None
# Ensure only one Missing Tables dialog at a time
_missing_tables_dialog: Optional[ui.dialog] = None
# Cache for scanned tables data (persists across page visits)
_tables_cache: Optional[List[Dict]] = None
_missing_cache: Optional[List[Dict]] = None


def load_vpsdb() -> List[Dict]:
    global _vpsdb_cache
    if _vpsdb_cache is not None:
        return _vpsdb_cache
    try:
        with open(VPSDB_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                _vpsdb_cache = data
            else:
                _vpsdb_cache = data.get('tables') or data.get('items') or []
    except Exception as e:
        logger.error(f'Failed to load vpsdb.json: {e}')
        _vpsdb_cache = []
    return _vpsdb_cache

def search_vpsdb(term: str, limit: int = 50) -> List[Dict]:
    term = (term or '').strip().lower()
    if not term:
        return []
    items = load_vpsdb()
    def _key(s): return (s or '').lower()
    results = []
    for it in items:
        name = _key(it.get('name'))
        if term in name:
            results.append(it)
        if len(results) >= limit:
            break
    return results

ACCEPT_CRZ = ['.crz', '.cRZ', '.CRZ']  # altcolor accepted extensions (case-insensitive)

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def save_upload_bytes(dest_file: Path, content: bytes) -> None:
    ensure_dir(dest_file.parent)
    with open(dest_file, 'wb') as f:
        f.write(content)


# --- helper to create meta.ini with a chosen VPS record for ONE folder ---

def associate_vps_to_folder(table_folder: Path, vps_entry: Dict, download_media: bool = False) -> None:
    """
    Creates meta.ini inside `table_folder` using the selected vps_entry and the VPX metadata.
    """
    from common.tableparser import TableParser  # if you want to reuse Table object for media step
    from common.iniconfig import IniConfig
    from common.metaconfig import MetaConfig
    # If your class names/paths differ, adjust the imports above.

    if not table_folder.exists():
        raise FileNotFoundError(f"Folder not found: {table_folder}")

    # Find a VPX file in the folder (pick the first, deterministic by sort)
    vpx_files = sorted([p for p in table_folder.glob('*.vpx')])
    if not vpx_files:
        # Also scan one-level deep (many layouts keep the .vpx inside the folder)
        vpx_files = sorted([p for p in table_folder.rglob('*.vpx') if p.parent == table_folder])
    if not vpx_files:
        raise FileNotFoundError(f"No .vpx found in {table_folder}")

    vpx_file = vpx_files[0]

    # Parse VPX data exactly as in buildMetaData
    parser = VPXParser()
    vpxdata = parser.singleFileExtract(str(vpx_file))

    finalini = {
        'vpsdata': vps_entry,
        'vpxdata': vpxdata,
    }

    meta_path = table_folder / f"{table_folder}.info"
    meta = MetaConfig(str(meta_path))
    meta.writeConfigMeta(finalini)

    if download_media:
        from common.vpsdb import VPSdb      # your VPSdb wrapper that has downloadMediaForTable
        vps = VPSdb(_INI_CFG.config['Settings']['tablerootdir'], _INI_CFG)
        # Build a lightweight Table-like object for the API you expect:
        # If your TableParser.Table has fields: tableDirName, fullPathTable, fullPathVPXfile
        class _LightTable:
            def __init__(self, folder: Path, vpx: Path):
                self.tableDirName = folder.name
                self.fullPathTable = str(folder)
                self.fullPathVPXfile = str(vpx)
        pseudo_table = _LightTable(table_folder, vpx_file)
        vps.downloadMediaForTable(pseudo_table, vps_entry.get('id'))


logger = logging.getLogger("tables")

def get_tables_path() -> str:
    """Resolve tables path from vpinfe.ini [Settings] tablerootdir, fallback to ~/tables."""
    try:
        tableroot = _INI_CFG.config.get('Settings', 'tablerootdir', fallback='').strip()
        if tableroot:
            return os.path.expanduser(tableroot)
    except Exception as e:
        logger.debug(f'Could not read tablerootdir from vpinfe.ini: {e}')
    return os.path.expanduser('~/tables')

def parse_table_info(info_path):
    import os
    import json

    try:
        with open(info_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        table_dir = os.path.dirname(info_path)
        table_name = os.path.basename(table_dir)

        info = raw.get("Info", {})
        vpx = raw.get("VPXFile", {})
        user = raw.get("User", {})

        def get(*paths, default=""):
            """
            paths = [("VPXFile","rom"), ("Info","Rom"), ...]
            """
            for section, key in paths:
                src = {"Info": info, "VPXFile": vpx, "User": user, "root": raw}.get(section)
                if src and key in src and src[key] not in ("", None):
                    return src[key]
            return default

        data = {
            # Display / identity
            "name": get(("Info", "Title"), ("root", "name"), default=table_name),
            "filename": get(("VPXFile", "filename"), default=f"{table_name}.vpx"),
            "id": get(("Info", "VPSId"), ("root", "id")),

            # Metadata
            "manufacturer": get(("Info", "Manufacturer"), ("VPXFile", "manufacturer")),
            "year": get(("Info", "Year"), ("VPXFile", "year")),
            "type": get(("Info", "Type"), ("VPXFile", "type")),
            "rom": get(("VPXFile", "rom"), ("Info", "Rom")),
            "version": get(("VPXFile", "version")),

            # Detection flags
            "detectnfozzy": get(("VPXFile", "detectnfozzy")),
            "detectfleep": get(("VPXFile", "detectfleep")),
            "detectssf": get(("VPXFile", "detectssf")),
            "detectlut": get(("VPXFile", "detectlut")),
            "detectscorebit": get(("VPXFile", "detectscorebit")),
            "detectfastflips": get(("VPXFile", "detectfastflips")),
            "detectflex": get(("VPXFile", "detectflex")),

            # Patching
            "patch_applied": get(("VPXFile", "patch_applied"), default=False),

            # Internal
            "table_path": table_dir,
        }

        return data

    except Exception as e:
        logger.error(f"Error reading {info_path}: {e}")
        return {}

def scan_tables(silent: bool = False):
    tables_path = get_tables_path()
    rows = []
    if not os.path.exists(tables_path):
        logger.warning(f"Tables path does not exist: {tables_path}. Skipping scan.")
        if not silent:
            ui.notify("Tables path does not exist. Please, verify your vpinfe.ini settings", type="negative")
        return []

    for root, _, files in os.walk(tables_path):
        current_dir = os.path.basename(root)
        info_file = f"{current_dir}.info"

        if info_file in files:
            meta_path = os.path.join(root, info_file)
            data = parse_table_info(meta_path)
            if data:
                data["table_path"] = root
                rows.append(data)

    return rows

def scan_missing_tables():
    """
    A 'missing table' = any directory under ~/tables that does NOT contain <current_dir>.info.
    Only directories with at least one .vpx file are considered.
    """
    base = Path(get_tables_path())
    missing = []

    if not base.exists():
        return missing

    for root, dirs, files in os.walk(base):
        files_set = set(files)
        current_dir = os.path.basename(root)
        info_filename = f"{current_dir}.info"

        # Skip directories that already have <current_dir>.info
        if info_filename in files_set:
            continue

        # Only consider directories with at least one .vpx file
        if any(f.lower().endswith('.vpx') for f in files):
            missing.append({
                'folder': current_dir,
                'path': root,
            })

    return missing


def load_metadata_from_ini():
    return scan_tables()

def render_panel(tab=None):
    with ui.column().classes('w-full'):
        # Hide Quasar's built-in numeric overlay inside linear progress bars (prevents 0..1 decimals)
        ui.add_head_html('<style>.q-linear-progress__info{display:none!important}</style>')
        # Style table header and alternate row colors - modern look
        ui.add_head_html('''
        <style>
            .q-table {
                border-radius: 8px !important;
                overflow: hidden !important;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;
            }
            .q-table thead tr {
                background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%) !important;
            }
            .q-table thead tr th {
                background: transparent !important;
                color: #fff !important;
                font-weight: 600 !important;
                text-transform: uppercase !important;
                font-size: 0.75rem !important;
                letter-spacing: 0.05em !important;
                padding: 16px 12px !important;
            }
            .q-table tbody tr:nth-child(odd) {
                background-color: #1e293b !important;
            }
            .q-table tbody tr:nth-child(even) {
                background-color: #0f172a !important;
            }
            .q-table tbody tr td {
                color: #e2e8f0 !important;
                padding: 12px !important;
                border-bottom: 1px solid #334155 !important;
            }
            .q-table tbody tr:hover {
                background-color: #334155 !important;
                transition: background-color 0.2s ease !important;
            }
            .q-table tbody tr:hover td {
                color: #fff !important;
            }
            .q-table__bottom {
                background-color: #1e293b !important;
                color: #94a3b8 !important;
                border-top: 1px solid #334155 !important;
            }
        </style>
        ''')
        # Define columns for the table
        columns = [
            {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
            {'name': 'filename', 'label': 'Filename', 'field': 'filename', 'align': 'left', 'sortable': True},
            {'name': 'manufacturer', 'label': 'Manufacturer', 'field': 'manufacturer', 'align': 'left', 'sortable': True},
            {'name': 'year', 'label': 'Year', 'field': 'year', 'align': 'left', 'sortable': True},
            {'name': 'id', 'label': 'VPS ID', 'field': 'id', 'align': 'left', 'sortable': True},
            {'name': 'rom', 'label': 'ROM', 'field': 'rom', 'align': 'left', 'sortable': True},
            {'name': 'version', 'label': 'Version', 'field': 'version', 'align': 'left', 'sortable': True},
            {'name': 'patch_applied', 'label': 'Standalone Patch', 'field': 'patch_applied', 'sortable': True, 'align': 'center'},
        ]

        def on_row_click(e: events.GenericEventArguments):
            if len(e.args) > 1:
                row_data = e.args[1]
                open_table_dialog(row_data)
            else:
                ui.notify("Error: Unexpected row click event format.", type="negative")

        async def perform_scan(*_, silent: bool = False):
            """Scans for tables asynchronously and updates the UI.
            If silent=True, suppress user notifications.
            """
            global _tables_cache, _missing_cache
            print("Scanning tables...")
            # Keep UX simple: disable the Scan button during work, no pre-notify
            try:
                scan_btn.disable()
            except Exception:
                pass
            try:
                # Run blocking I/O in a separate thread to avoid freezing the UI
                table_rows = await run.io_bound(scan_tables, silent)
                missing_rows = await run.io_bound(scan_missing_tables)

                # Update UI components (default sort by Name; force refresh by reassigning rows)
                try:
                    table_rows.sort(key=lambda r: (r.get('name') or '').lower())
                except Exception:
                    pass

                # Cache the results
                _tables_cache = table_rows
                _missing_cache = missing_rows

                table._props['rows'] = table_rows
                table.update()

                # Force browser layout recalculation to ensure table rows display properly
                await asyncio.sleep(0.05)
                # Trigger a window resize event to force the table to recalculate its layout
                try:
                    ui.run_javascript('window.dispatchEvent(new Event("resize"));')
                except RuntimeError:
                    pass  # Ignore if not in a valid UI context
                
                title_label.set_text(f"Installed Tables ({len(table_rows)})")
                missing_button.text = f"Unmatched Tables ({len(missing_rows)})"

                # Update the click handler for the missing tables button with the new data
                missing_button.on('click', None) # Remove old handler
                missing_button.on('click', lambda: open_missing_tables_dialog(
                    missing_rows,
                    on_close=lambda: asyncio.create_task(perform_scan(silent=True))
                ))

                if not silent:
                    ui.notify('Scan complete!', type='positive')
            except Exception as e:
                logger.exception("Failed to scan tables")
                if not silent:
                    ui.notify(f"Error during scan: {e}", type='negative')
            finally:
                try:
                    scan_btn.enable()
                except Exception:
                    pass

        # --- Metadata build logic (from media.py) ---
        RUNNING = False
        # Progress bar: value is 0..1; percent is shown only in status_label
        progressbar = ui.linear_progress(value=0.0)
        progressbar.visible = False
        status_label = ui.label("").classes("text-sm text-grey")
        status_label.visible = False

        # Console log output
        log_container = ui.column().classes("w-full bg-gray-900 rounded p-3 overflow-auto").style("max-height: 300px; font-family: monospace; font-size: 12px;")
        log_container.visible = False
        log_messages = []

        progress_q: Queue[tuple[int, int, str]] = Queue()
        log_q: Queue[str] = Queue()

        def pump_progress():
            updated = False
            while not progress_q.empty():
                updated = True
                current, total, message = progress_q.get_nowait()
                if total and total > 0:
                    frac = max(0.0, min(1.0, current / total))
                    percent = int(round(frac * 100))
                    progressbar.value = frac
                    status_label.text = f'{message} — {percent}%'
                else:
                    progressbar.value = 0
                    status_label.text = message or ''

            # Update log messages
            while not log_q.empty():
                log_msg = log_q.get_nowait()
                log_messages.append(log_msg)
                # Keep only last 100 messages to avoid memory issues
                if len(log_messages) > 100:
                    log_messages.pop(0)
                updated = True

            if updated:
                # Update log display
                log_container.clear()
                with log_container:
                    for msg in log_messages:
                        ui.label(msg).classes("text-white text-xs whitespace-pre-wrap")
                # Auto-scroll to bottom by using JavaScript
                try:
                    log_container.run_method('scrollTop', log_container.run_method('scrollHeight'))
                except:
                    pass

            if updated and progressbar.value >= 1.0:
                progress_timer.active = False

        progress_timer = ui.timer(0.1, pump_progress, active=False)

        def progress_cb(current: int, total: int, message: str):
            progress_q.put((current, total, message))

        def log_cb(message: str):
            """Callback for console log messages."""
            log_q.put(message)
        async def call_build_metadata(download_media_opt: bool = False, update_all_opt: bool = False):
            nonlocal RUNNING, log_messages
            if RUNNING:
                return
            RUNNING = True
            build_btn.disable()
            try:
                # Clear previous logs
                log_messages.clear()
                log_container.clear()

                progressbar.value = 0
                progressbar.visible = True
                status_label.text = "Preparing…"
                status_label.visible = True
                log_container.visible = True
                await asyncio.sleep(0.05)
                progress_timer.active = True
                result = await run.io_bound(
                    buildMetaData,
                    downloadMedia=download_media_opt,
                    updateAll=update_all_opt,
                    progress_cb=progress_cb,
                    log_cb=log_cb,
                )
                status_label.text = "Completed"
                progressbar.value = 1.0
                ui.notify(
                    (
                        f'Media & Metadata build complete. '
                        f'{result["found"]} scanned, {result.get("not_found", 0)} not found in VPSdb'
                    ) if download_media_opt else (
                        f'Metadata build complete. '
                        f'{result["found"]} scanned, {result.get("not_found", 0)} not found in VPSdb'
                    ),
                    type='positive'
                )
                # Refresh table list after completion
                await perform_scan(silent=True)
            except Exception as e:
                logger.exception('buildMetaData failed')
                ui.notify(f'Error: {e}', type='negative')
            finally:
                await asyncio.sleep(0.2)
                progress_timer.active = False
                progressbar.visible = False
                status_label.visible = False
                # Keep log visible so user can review
                build_btn.enable()
                RUNNING = False

        def open_build_metadata_dialog():
            """Show dialog with buildmeta options before executing."""
            dlg = ui.dialog().props('max-width=600px')
            with dlg, ui.card().classes('w-[550px]'):
                ui.label('Build Metadata Options').classes('text-lg font-bold')
                ui.separator()

                with ui.column().classes('gap-4 q-my-md'):
                    update_all_switch = ui.switch('Update All Tables', value=False).classes('text-sm')
                    ui.label('Reparse all tables, even if meta.ini already exists').classes('text-xs text-grey q-ml-lg')

                    download_media_switch = ui.switch('Download Media', value=True).classes('text-sm')
                    ui.label('Automatically download table images and media from VPSdb').classes('text-xs text-grey q-ml-lg')

                with ui.row().classes('justify-end gap-2 q-mt-md'):
                    ui.button('Cancel', on_click=dlg.close)
                    def do_build():
                        dlg.close()
                        asyncio.create_task(call_build_metadata(
                            download_media_opt=bool(download_media_switch.value),
                            update_all_opt=bool(update_all_switch.value)
                        ))
                    ui.button('Start Build', on_click=do_build).props('color=primary icon=build')
            dlg.open()

        # --- UI Layout ---
        # Header section with page title and action buttons
        with ui.card().classes('w-full mb-4').style('background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); border-radius: 12px;'):
            with ui.row().classes('w-full justify-between items-center p-4 gap-4'):
                ui.label('Tables Management').classes('text-2xl font-bold text-white').style('flex-shrink: 0;')
                with ui.row().classes('gap-3 items-center'):
                    scan_btn = ui.button("Scan Tables", icon="refresh", on_click=perform_scan).props("color=white text-color=primary rounded")
                    missing_button = ui.button("Unmatched", icon="warning").props("color=negative rounded")

        # Tools card section
        with ui.card().classes('w-full mb-4').style('border-radius: 8px; background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155;'):
            with ui.expansion('Tools', icon='build', value=False).classes('w-full'):
                with ui.row().classes('gap-4 p-2 items-center flex-wrap'):
                    build_btn = ui.button("Build Metadata", on_click=open_build_metadata_dialog, icon="build").props("color=primary outline rounded")
                    patch_btn = ui.button("Apply VPX Patches", icon="construction").props("color=secondary outline rounded")

                    async def call_apply_patches():
                        nonlocal RUNNING
                        if RUNNING:
                            return
                        RUNNING = True
                        patch_btn.disable()
                        try:
                            progressbar.value = 0
                            progressbar.visible = True
                            status_label.text = "Preparing…"
                            status_label.visible = True
                            await asyncio.sleep(0.05)
                            progress_timer.active = True
                            await run.io_bound(vpxPatches, progress_cb=progress_cb)
                            status_label.text = "Completed"
                            progressbar.value = 100
                            ui.notify('VPX patches applied', type='positive')
                            # refresh tables silently to reflect patch_applied flag
                            asyncio.create_task(perform_scan(silent=True))
                        except Exception as e:
                            ui.notify(f'Error: {e}', type='negative')
                        finally:
                            await asyncio.sleep(0.2)
                            progress_timer.active = False
                            progressbar.visible = False
                            status_label.visible = False
                            patch_btn.enable()
                            RUNNING = False
                    patch_btn.on_click(call_apply_patches)

        # Progress indicators
        progressbar
        status_label
        log_container

        # Use cached data if available, otherwise start with empty
        initial_rows = _tables_cache if _tables_cache is not None else []
        initial_missing = _missing_cache if _missing_cache is not None else []

        # Table title - centered above the table
        title_label = ui.label("Installed Tables").classes('text-xl font-semibold text-center w-full py-2')

        # Create a scrollable container for the table with proper height constraint
        table_container = ui.column().classes("w-full").style("flex: 1; overflow: hidden; display: flex;")

        with table_container:
            table = (
                ui.table(columns=columns, rows=initial_rows, row_key='filename', pagination={'rowsPerPage': 25})
                  .props('rows-per-page-options="[25,50,100]" sort-by="name" sort-order="asc"')
                  .on('row-click', on_row_click)
                  .classes("w-full cursor-pointer")
                  .style("flex: 1; overflow: auto;")
            )

        # Update title and missing button if we have cached data
        if _tables_cache is not None:
            title_label.set_text(f"Installed Tables ({len(_tables_cache)})")
        if _missing_cache is not None:
            missing_button.text = f"Unmatched Tables ({len(_missing_cache)})"
            missing_button.on('click', lambda: open_missing_tables_dialog(
                _missing_cache,
                on_close=lambda: asyncio.create_task(perform_scan(silent=True))
            ))

        # Function to refresh the table display after client is connected
        async def refresh_table_on_connect():
            await asyncio.sleep(0.2)  # Small delay to ensure client is ready
            with table_container:
                if _tables_cache is not None:
                    # Force refresh with cached data
                    table._props['rows'] = _tables_cache
                    table.update()
                else:
                    # No cache, run the scan
                    await perform_scan(silent=True)
                # Trigger resize to ensure proper rendering
                try:
                    ui.run_javascript('window.dispatchEvent(new Event("resize"));')
                except RuntimeError:
                    pass

        # Use client.on_connect to defer table refresh until client is connected
        try:
            context.client.on_connect(lambda: asyncio.create_task(refresh_table_on_connect()))
        except Exception:
            # Fallback: trigger scan if we don't have cached data
            if _tables_cache is None:
                asyncio.create_task(perform_scan(silent=True))

def open_table_dialog(row_data: dict):
    # Add dialog styles
    ui.add_head_html('''
    <style>
        .table-dialog-card {
            background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%) !important;
            border: 1px solid #334155 !important;
        }
        .table-dialog-header {
            background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
            margin: -16px -16px 0 -16px;
            padding: 16px 20px;
            border-radius: 4px 4px 0 0;
        }
        .detail-row {
            padding: 8px 12px;
            border-radius: 6px;
            background: rgba(30, 41, 59, 0.5);
        }
        .detail-row:hover {
            background: rgba(51, 65, 85, 0.5);
        }
        .detail-label {
            color: #94a3b8;
            font-size: 0.85rem;
            min-width: 120px;
        }
        .detail-value {
            color: #e2e8f0;
            font-weight: 500;
        }
        .addon-card {
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 12px 16px;
        }
    </style>
    ''')

    dlg = ui.dialog().props('max-width=900px')
    with dlg, ui.card().classes('w-[850px] max-w-[95vw] table-dialog-card'):
        table_name = row_data.get('name') or row_data.get('filename') or 'Table'

        # Header
        with ui.row().classes('table-dialog-header w-full items-center gap-3'):
            ui.icon('casino', size='32px').classes('text-white')
            with ui.column().classes('gap-0'):
                ui.label(table_name).classes('text-xl font-bold text-white')
                manufacturer = row_data.get('manufacturer', '')
                year = row_data.get('year', '')
                if manufacturer or year:
                    ui.label(f'{manufacturer} {year}'.strip()).classes('text-sm text-blue-200')

        # Main info section
        with ui.column().classes('w-full gap-4 p-4'):
            # Key details in a grid
            with ui.card().classes('w-full p-4').style('background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 8px;'):
                ui.label('Table Information').classes('text-lg font-semibold text-white mb-3')

                # Define which fields to show and their display names
                display_fields = [
                    ('filename', 'Filename', 'description'),
                    ('id', 'VPS ID', 'fingerprint'),
                    ('rom', 'ROM', 'memory'),
                    ('version', 'Version', 'tag'),
                    ('type', 'Type', 'category'),
                    ('table_path', 'Path', 'folder'),
                ]

                with ui.grid(columns=2).classes('w-full gap-3'):
                    for key, label, icon in display_fields:
                        value = row_data.get(key, '')
                        if value:  # Only show non-empty fields
                            with ui.row().classes('detail-row items-center gap-2 w-full'):
                                ui.icon(icon, size='18px').classes('text-blue-400')
                                ui.label(label).classes('detail-label')
                                ui.label(str(value)).classes('detail-value')

            # Detection flags section - show all detection flags with their status
            detect_fields = [
                ('detectnfozzy', 'nFozzy'),
                ('detectfleep', 'Fleep'),
                ('detectssf', 'SSF'),
                ('detectlut', 'LUT'),
                ('detectscorebit', 'Scorebit'),
                ('detectfastflips', 'FastFlips'),
                ('detectflex', 'Flex'),
            ]

            # Check if any detection fields have values (not empty string)
            has_detections = any(row_data.get(k, '') != '' for k, _ in detect_fields)

            if has_detections:
                with ui.card().classes('w-full p-4').style('background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 8px;'):
                    ui.label('Detected Features').classes('text-lg font-semibold text-white mb-3')
                    with ui.row().classes('gap-2 flex-wrap'):
                        for key, label in detect_fields:
                            value = row_data.get(key, '')
                            if value != '':  # Show if value exists
                                # Handle string "true"/"false" values
                                is_detected = str(value).lower() == 'true'
                                if is_detected:
                                    ui.badge(label, color='positive').props('rounded')
                                else:
                                    ui.badge(label, color='grey').props('rounded outline')

            # Patch status
            patch_applied = row_data.get('patch_applied', False)
            with ui.row().classes('items-center gap-2'):
                ui.icon('build' if patch_applied else 'build_circle', size='20px').classes('text-green-400' if patch_applied else 'text-gray-500')
                ui.label('Standalone Patch:').classes('text-gray-400')
                if patch_applied:
                    ui.badge('Applied', color='positive').props('rounded')
                else:
                    ui.badge('Not Applied', color='grey').props('rounded outline')

            # Addons section
            with ui.expansion('Install Addons', icon='extension').classes('w-full').style('background: rgba(15, 23, 42, 0.4); border-radius: 8px;'):
                table_path = Path(row_data.get('table_path', ''))
                rom_name = (row_data.get('rom') or '').strip()

                with ui.column().classes('gap-4 p-2'):
                    # Pupvideos uploader
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('video_library', size='24px').classes('text-purple-400')
                            with ui.column().classes('gap-0'):
                                ui.label('PupVideos').classes('font-medium text-white')
                                ui.label('Upload video files for PuP pack').classes('text-xs text-gray-400')
                        def on_pup_upload(e):
                            dest = table_path / 'pupvideos' / e.name
                            save_upload_bytes(dest, e.content)
                            ui.notify(f'Saved: {e.name}', type='positive')
                        ui.upload(on_upload=on_pup_upload, multiple=True).props('flat color=primary label="Upload"')

                    # Altcolor uploader
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('palette', size='24px').classes('text-orange-400')
                            with ui.column().classes('gap-0'):
                                ui.label('AltColor').classes('font-medium text-white')
                                ui.label('Upload .cRZ color files (requires ROM)').classes('text-xs text-gray-400')
                        def on_altcolor_upload(e):
                            if not rom_name:
                                ui.notify('ROM not found. Update metadata first.', type='warning')
                                return
                            ext = Path(e.name).suffix
                            if ext not in ACCEPT_CRZ:
                                ui.notify('Only .cRZ files accepted', type='negative')
                                return
                            dest = table_path / 'pinmame' / 'altcolor' / rom_name / e.name
                            save_upload_bytes(dest, e.content)
                            ui.notify(f'Saved: {e.name}', type='positive')
                        ui.upload(on_upload=on_altcolor_upload, multiple=False).props('flat color=primary label="Upload .cRZ"')

                    # AltSound uploader
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('music_note', size='24px').classes('text-green-400')
                            with ui.column().classes('gap-0'):
                                ui.label('AltSound').classes('font-medium text-white')
                                ui.label('Upload sound pack files (requires ROM)').classes('text-xs text-gray-400')
                        def on_altsound_upload(e):
                            if not rom_name:
                                ui.notify('ROM not found. Update metadata first.', type='warning')
                                return
                            dest = table_path / 'pinmame' / 'altsound' / rom_name / e.name
                            save_upload_bytes(dest, e.content)
                            ui.notify(f'Saved: {e.name}', type='positive')
                        ui.upload(on_upload=on_altsound_upload, multiple=True).props('flat color=primary label="Upload"')

        # Footer with close button
        with ui.row().classes('w-full justify-end p-4 pt-0'):
            ui.button('Close', icon='close', on_click=dlg.close).props('flat color=grey')
    dlg.open()

def open_missing_tables_dialog(missing_rows: list[dict], on_close: Optional[Callable[[], None]] = None):
    global _missing_tables_dialog
    # Close any previous dialog to avoid stacking
    try:
        if _missing_tables_dialog:
            _missing_tables_dialog.close()
    except Exception:
        pass
    dlg = ui.dialog().props('max-width=1080px')
    _missing_tables_dialog = dlg
    with dlg, ui.card().classes('w-[960px] max-w-[95vw]'):
        title = ui.label(f'Missing Tables ({len(missing_rows)})').classes('text-lg font-bold')
        ui.separator()

        container = ui.column().classes('w-full')

        def render(items: list[dict]):
            container.clear()
            title.set_text(f'Missing Tables ({len(items)})')
            if not items:
                with container:
                    ui.label('No tables without meta.ini.').classes('q-my-md')
                return
            for r in items:
                with container, ui.row().classes('justify-between items-center w-full q-py-xs border-b'):
                    ui.label(r['folder']).classes('font-medium')
                    ui.button(
                        'Match VPS ID',
                        on_click=lambda rr=r: open_match_vps_dialog(
                            rr,
                            refresh_missing=lambda: (ui.notify('Missing list updated', type='info'), render(scan_missing_tables())),
                            refresh_installed=None,
                        )
                    ).props('color=primary outline')

        render(missing_rows)

        with ui.row().classes('justify-end q-mt-md'):
            def _close():
                dlg.close()
                # clear global ref so a new one can be created next time
                global _missing_tables_dialog
                _missing_tables_dialog = None
                if callable(on_close):
                    on_close()
            ui.button('Close', on_click=_close)
    dlg.open()

def open_match_vps_dialog(
    missing_row: dict,
    refresh_missing: Optional[Callable[[], None]] = None,
    refresh_installed: Optional[Callable[[], None]] = None,
    ):
    """
    missing_row: {'folder': '<name>', 'path': '<abs path>'}
    refresh_missing: callback to refresh the missing list/count after success
    refresh_installed: callback to refresh the installed tables list after success
    """
    dlg = ui.dialog().props('max-width=1080px')
    with dlg, ui.card().classes('w-[960px] max-w-[95vw]'):
        ui.label(f"Match VPS ID → {missing_row['folder']}").classes('text-lg font-bold')
        ui.separator()

        results_container = ui.column().classes('gap-1 w-full').style('max-height: 55vh; overflow:auto;')

        def render_results(items: List[Dict]):
            results_container.clear()
            if not items:
                with results_container:
                    ui.label('Search by Table Name').classes('text-sm text-gray-500')
                return

            for it in items:
                name = it.get('name', '')
                manuf = it.get('manufacturer') or it.get('mfg') or ''
                year = it.get('year') or ''
                vid = it.get('id') or ''
                with results_container:
                    with ui.row().classes('justify-between items-center w-full q-py-xs border-b'):
                        ui.label(f"{name}  —  {manuf}  —  {year}  (ID: {vid})").classes('text-sm')
                        def _on_assoc(it=it):
                            try:
                                associate_vps_to_folder(Path(missing_row['path']), it, download_media=False)
                                ui.notify(f"meta.ini created for '{missing_row['folder']}'", type='positive')
                                dlg.close()
                                if callable(refresh_missing):
                                    refresh_missing()
                                if callable(refresh_installed):
                                    refresh_installed()
                            except Exception as ex:
                                logger.exception('Association failed')
                                ui.notify(f'Failed creating meta.ini: {ex}', type='negative')
                        ui.button('Associate', on_click=_on_assoc).props('color=primary')

        # Pre-fill the search with folder name for convenience
        initial_term = missing_row['folder']
        search_input = ui.input('Search VPS…', value=initial_term).classes('w-full')

        def on_search_change(e: events.ValueChangeEventArguments):
            term = e.value or ''
            render_results(search_vpsdb(term, limit=80))

        search_input.on_value_change(on_search_change)

        # Render initial results:
        render_results(search_vpsdb(initial_term, limit=80))

        with ui.row().classes('justify-end q-mt-md'):
            ui.button('Close', on_click=dlg.close)
    dlg.open()
