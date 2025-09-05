import os
import configparser
import logging
import asyncio
from nicegui import ui, events, run
from pathlib import Path
import json
from typing import List, Dict, Optional, Callable
from common.vpxparser import VPXParser
from clioptions import buildMetaData, vpxPatches
from queue import Queue
from common.vpxcollections import VPXCollections

# Resolve project root and important paths explicitly
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VPSDB_JSON_PATH = PROJECT_ROOT / 'vpsdb.json'
VPINFE_INI_PATH = PROJECT_ROOT / 'vpinfe.ini'
COLLECTIONS_INI_PATH = PROJECT_ROOT / 'collections.ini'

# Load vpinfe.ini once to avoid repeated parsing
from common.iniconfig import IniConfig
_INI_CFG = IniConfig(str(VPINFE_INI_PATH))

#_vpsdb_cache: List[Dict] | None = None
_vpsdb_cache: Optional[List[Dict]] = None
# Ensure only one Missing Tables dialog at a time
_missing_tables_dialog: Optional[ui.dialog] = None


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

    meta_path = table_folder / 'meta.ini'
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

def parse_meta_ini(meta_path):
    import os
    import configparser

    config = configparser.ConfigParser()
    config.optionxform = str  # preserve case
    try:
        config.read(meta_path, encoding="utf-8")
        vpsdb = config["VPSdb"] if "VPSdb" in config else {}
        vpxfile = config["VPXFile"] if "VPXFile" in config else {}

        def get_field(field):
            value = vpxfile.get(field, "")
            if not value:
                value = vpsdb.get(field, "")
            return value

        data = {
            "filename": get_field("filename"),
            "id": get_field("id"),
            "name": get_field("name"),
            "manufacturer": get_field("manufacturer"),
            "year": get_field("year"),
            "type": get_field("type"),
            "rom": get_field("rom"),
            "version": get_field("version"),
            "detectnfozzy": get_field("detectnfozzy"),
            "detectfleep": get_field("detectfleep"),
            "detectssf": get_field("detectssf"),
            "detectlut": get_field("detectlut"),
            "detectscorebit": get_field("detectscorebit"),
            "detectfastflips": get_field("detectfastflips"),
            "detectflex": get_field("detectflex"),
            "patch_applied": get_field("patch_applied")
        }
        data["table_path"] = os.path.dirname(meta_path)
        return data
    except Exception as e:
        logger.error(f"Error reading {meta_path}: {e}")
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
        if "meta.ini" in files:
            meta_path = os.path.join(root, "meta.ini")
            data = parse_meta_ini(meta_path)
            if data:
                data["table_path"] = root
                rows.append(data)
    return rows

def scan_missing_tables():
    """
    A 'missing table' here = any directory under ~/tables that does NOT contain meta.ini.
    Optionally, we can filter to only those containing at least one .vpx file. I’ll do that,
    since it’s usually what you want.
    """
    base = Path(get_tables_path())
    missing = []

    if not base.exists():
        return missing

    for root, dirs, files in os.walk(base):
        files_set = set(files)
        if 'meta.ini' in files_set:
            continue
        # consider this a table dir if there is at least one .vpx file
        if any(f.lower().endswith('.vpx') for f in files):
            missing.append({
                'folder': os.path.basename(root),
                'path': root,
            })
    return missing


def load_metadata_from_ini():
    return scan_tables()

def create_tab():
    """Tab Tables (ui.tab)."""
    return ui.tab('Tables',icon='list').props('icon-color=primary')

def render_panel(tab):
    with ui.tab_panel(tab):
        # Hide Quasar's built-in numeric overlay inside linear progress bars (prevents 0..1 decimals)
        ui.add_head_html('<style>.q-linear-progress__info{display:none!important}</style>')
        # Preload collections list for quick pull-down per row
        try:
            _collections_mgr = VPXCollections(str(COLLECTIONS_INI_PATH))
            _all_collections = list(_collections_mgr.get_collections_name())
        except Exception:
            _all_collections = []
        # Define columns for the table
        columns = [
            {'name': 'filename', 'label': 'Filename', 'field': 'filename', 'sortable': True},
            {'name': 'id', 'label': 'VPS ID', 'field': 'id', 'sortable': True},
            {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
            {'name': 'manufacturer', 'label': 'Manufacturer', 'field': 'manufacturer', 'sortable': True},
            {'name': 'year', 'label': 'Year', 'field': 'year', 'sortable': True},
            {'name': 'rom', 'label': 'ROM', 'field': 'rom', 'sortable': True},
            {'name': 'version', 'label': 'Version', 'field': 'version', 'sortable': True},
            {'name': 'detectnfozzy', 'label': 'NFOZZY', 'field': 'detectnfozzy', 'sortable': True},
            {'name': 'detectfleep','label': 'Fleep','field': 'detectfleep', 'sortable': True},
            {'name': 'detectssf','label': 'SSF','field': 'detectssf', 'sortable': True},
            {'name': 'detectlut','label': 'LUT','field': 'detectlut', 'sortable': True},
            {'name': 'detectscorebit','label': 'Scorebit','field': 'detectscorebit', 'sortable': True},
            {'name': 'detectfastflips','label': 'FastFlips','field': 'detectfastflips', 'sortable': True},
            {'name': 'detectflex','label': 'FlexDMD','field': 'detectflex', 'sortable': True},
            {'name': 'patch_applied', 'label': 'Patch ?', 'field': 'patch_applied', 'sortable': True},
            {'name': 'collections', 'label': 'Collections', 'field': 'id', 'sortable': False}
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
                table.rows = []
                table.update()
                await asyncio.sleep(0)  # yield to UI loop
                table.rows = table_rows
                table.update()
                title_label.set_content(f"## Installed Tables ({len(table_rows)})")
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
        progress_q: Queue[tuple[int, int, str]] = Queue()
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
            if updated and progressbar.value >= 1.0:
                progress_timer.active = False
        progress_timer = ui.timer(0.1, pump_progress, active=False)
        def progress_cb(current: int, total: int, message: str):
            progress_q.put((current, total, message))
        async def call_build_metadata():
            nonlocal RUNNING
            if RUNNING:
                return
            RUNNING = True
            build_btn.disable()
            try:
                progressbar.value = 0
                progressbar.visible = True
                status_label.text = "Preparing…"
                status_label.visible = True
                await asyncio.sleep(0.05)
                progress_timer.active = True
                do_download = bool(download_media.value)
                result = await run.io_bound(
                    buildMetaData,
                    downloadMedia=do_download,
                    progress_cb=progress_cb,
                )
                status_label.text = "Completed"
                progressbar.value = 100
                ui.notify(
                    (
                        f'Media & Metadata build complete. '
                        f'{result["found"]} scanned, {result.get("not_found", 0)} not found in VPSdb'
                    ) if do_download else (
                        f'Metadata build complete. '
                        f'{result["found"]} scanned, {result.get("not_found", 0)} not found in VPSdb'
                    ),
                    type='positive'
                )
            except Exception as e:
                ui.notify(f'Error: {e}', type='negative')
            finally:
                await asyncio.sleep(0.2)
                progress_timer.active = False
                progressbar.visible = False
                status_label.visible = False
                build_btn.enable()
                RUNNING = False

        # --- UI Layout ---
        title_label = ui.markdown("Installed Tables")
        with ui.row().classes("q-my-md"):
            scan_btn = ui.button("Scan Tables", on_click=perform_scan).props("color=primary")
            missing_button = ui.button("Undetected Tables").props("color=red")
            with ui.row().classes("items-center gap-2"):
                build_btn = ui.button("Build Metadata", on_click=call_build_metadata).props("icon=build color=primary")
                download_media = ui.switch("Download Media Automatically", value=False)
                patch_btn = ui.button("Apply VPX Patches").props("icon=construction color=secondary")
                collections_btn = ui.button("Collections").props("icon=collections_bookmark color=secondary outline")

                def open_manage_collections():
                    c = VPXCollections(str(COLLECTIONS_INI_PATH))

                    def refresh_list():
                        names = list(c.get_collections_name())
                        list_container.clear()
                        if not names:
                            with list_container:
                                ui.label('No collections yet. Create one below.').classes('text-sm text-grey')
                            return
                        for name in sorted(names):
                            with list_container, ui.row().classes('justify-between items-center w-full q-py-xs'):
                                ui.label(name).classes('font-medium')
                                with ui.row().classes('gap-2'):
                                    def do_rename(n=name):
                                        d2 = ui.dialog().props('max-width=480px')
                                        with d2, ui.card().classes('w-[420px]'):
                                            ui.label(f'Rename "{n}"').classes('text-lg font-bold')
                                            new_input = ui.input('New name').props('dense clearable').classes('w-full')
                                            with ui.row().classes('justify-end gap-2 q-mt-sm'):
                                                ui.button('Cancel', on_click=d2.close)
                                                def confirm_rename():
                                                    newn = (new_input.value or '').strip()
                                                    if not newn:
                                                        ui.notify('Type a new name', type='warning'); return
                                                    if newn in c.get_collections_name():
                                                        ui.notify('Collection already exists', type='warning'); return
                                                    try:
                                                        ids = c.get_vpsids(n)
                                                        c.add_collection(newn, ids)
                                                        c.delete_collection(n)
                                                        c.save()
                                                        ui.notify('Renamed', type='positive')
                                                        d2.close()
                                                        refresh_list()
                                                    except Exception as ex:
                                                        ui.notify(f'Failed: {ex}', type='negative')
                                                ui.button('Rename', on_click=confirm_rename).props('color=primary')
                                        d2.open()
                                    ui.button('Rename', on_click=do_rename).props('outline')

                                    def do_delete(n=name):
                                        try:
                                            c.delete_collection(n)
                                            c.save()
                                            ui.notify('Deleted', type='positive')
                                            refresh_list()
                                        except Exception as ex:
                                            ui.notify(f'Failed: {ex}', type='negative')
                                    ui.button('Delete', on_click=do_delete).props('color=negative outline')

                    d = ui.dialog().props('max-width=760px')
                    with d, ui.card().classes('w-[700px]'):
                        ui.label('Collections').classes('text-lg font-bold')
                        ui.separator()
                        list_container = ui.column().classes('w-full')
                        refresh_list()
                        ui.separator().classes('q-my-sm')
                        with ui.row().classes('items-center gap-2'):
                            new_name = ui.input('Create new collection').props('dense clearable').classes('flex-1')
                            def create():
                                name = (new_name.value or '').strip()
                                if not name:
                                    ui.notify('Type a name', type='warning'); return
                                if name in c.get_collections_name():
                                    ui.notify('Collection already exists', type='warning'); return
                                try:
                                    c.add_collection(name)
                                    c.save()
                                    ui.notify('Created', type='positive')
                                    new_name.value = ''
                                    refresh_list()
                                except Exception as ex:
                                    ui.notify(f'Failed: {ex}', type='negative')
                            ui.button('Create', on_click=create).props('color=primary')
                        with ui.row().classes('justify-end q-mt-sm'):
                            ui.button('Close', on_click=d.close)
                    d.open()

                collections_btn.on('click', open_manage_collections)
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
        progressbar
        status_label
        ui.label("Click on the table to see more details and manage")
        table = (
            ui.table(columns=columns, rows=[], row_key='filename', pagination={'rowsPerPage': 25})
              .props('rows-per-page-options="[25,50,100]" sort-by="name" sort-order="asc"')
              .on('row-click', on_row_click)
              .classes("w-full cursor-pointer")
        )
        # (removed previous dialog-based quick collections handler)
        # Quick collections menu per row
        if _all_collections:
            def _escape_html(s: str) -> str:
                return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", "&#39;")
            items_html = ''.join(
                f"<q-item clickable v-close-popup @click.stop=\"$emit('toggle-collection', {{row: props.row, name: '{_escape_html(n)}'}})\"><q-item-section>{_escape_html(n)}</q-item-section></q-item>"
                for n in _all_collections
            )
            table.add_slot('body-cell-collections', f'''
              <q-td :props="props" @click.stop>
                <q-btn size="sm" flat dense icon="playlist_add" round @click.stop>
                  <q-menu>
                    <q-list style="min-width: 200px">
                      {items_html}
                    </q-list>
                  </q-menu>
                </q-btn>
              </q-td>
            ''')

            def _toggle_collection(e):
                payload = e.args if isinstance(e.args, dict) else (e.args[0] if isinstance(e.args, (list, tuple)) and e.args else {})
                row = payload.get('row') or {}
                name = (payload.get('name') or '').strip()
                vps_id = (row.get('id') or '').strip()
                if not vps_id:
                    ui.notify('This table has no VPS ID. Associate it first.', type='warning')
                    return
                if not name:
                    ui.notify('Invalid collection name', type='warning')
                    return
                try:
                    c = VPXCollections(str(COLLECTIONS_INI_PATH))
                    current = set(c.get_vpsids(name))
                    if vps_id in current:
                        c.remove_vpsid(name, vps_id)
                        c.save()
                        ui.notify(f'Removed from "{name}"', type='positive')
                    else:
                        c.add_vpsid(name, vps_id)
                        c.save()
                        ui.notify(f'Added to "{name}"', type='positive')
                except Exception as ex:
                    ui.notify(f'Failed to update collection: {ex}', type='negative')

            table.on('toggle-collection', _toggle_collection)

        # Trigger an initial scan once after render so data shows on first open
        def _trigger_initial_scan():
            try:
                asyncio.create_task(perform_scan(silent=True))
            finally:
                initial_timer.active = False  
        initial_timer = ui.timer(0.2, _trigger_initial_scan)

def open_table_dialog(row_data: dict):
    dlg = ui.dialog().props('max-width=1080px')
    with dlg, ui.card().classes('w-[860px] max-w-[90vw]'):
        title = row_data.get('filename') or row_data.get('name') or 'Table'
        ui.label(f'Table Info: {title}').classes('text-lg font-bold')

        # Details grid
        with ui.expansion('Table Details', value=True).classes('q-mt-md'):
            with ui.column().classes('gap-1'):
                for k, v in row_data.items():
                    ui.label(f'{k}: {v}')

        ui.separator().classes('q-my-md')
        ui.label('Addons').classes('text-base font-medium')

        table_path = Path(row_data.get('table_path', ''))
        rom_name = (row_data.get('rom') or '').strip()

        # 1) Pupvideos uploader (multiple files allowed)
        with ui.row().classes('items-center gap-3 q-mt-sm'):
            ui.label('Install Pupvideos')
            def on_pup_upload(e):
                # e contains: e.name, e.content (bytes)
                dest = table_path / 'pupvideos' / e.name
                save_upload_bytes(dest, e.content)
                ui.notify(f'Pupvideos: {e.name} saved on {dest}', type='positive')
            ui.upload(on_upload=on_pup_upload, multiple=True).props('label=Select files')

        # 2) Altcolor uploader (only .cRZ; requires ROM)
        with ui.row().classes('items-center gap-3 q-mt-sm'):
            ui.label('Install Altcolor')
            def on_altcolor_upload(e):
                if not rom_name:
                    ui.notify('ROM not found or undefined. Please, update meta.ini before trying to install Altcolor.', type='warning')
                    return
                ext = Path(e.name).suffix
                if ext not in ACCEPT_CRZ:
                    ui.notify('Only .cRZ file extension accepted for Altcolor.', type='negative')
                    return
                dest = table_path / 'pinmame' / 'altcolor' / rom_name / e.name
                save_upload_bytes(dest, e.content)
                ui.notify(f'Altcolor: {e.name} saved on {dest}', type='positive')
            ui.upload(on_upload=on_altcolor_upload, multiple=False).props('label=Select .cRZ')

        # 3) AltSound uploader (any files under rom folder; requires ROM)
        with ui.row().classes('items-center gap-3 q-mt-sm'):
            ui.label('Install AltSound')
            def on_altsound_upload(e):
                if not rom_name:
                    ui.notify('ROM not found or undefined. Please, update meta.ini before trying to install AltSound.', type='warning')
                    return
                dest = table_path / 'pinmame' / 'altsound' / rom_name / e.name
                save_upload_bytes(dest, e.content)
                ui.notify(f'AltSound: {e.name} saved on {dest}', type='positive')
            ui.upload(on_upload=on_altsound_upload, multiple=True).props('label=Select files or directory')

        # 4) Collections (add current table to a collection)
        with ui.row().classes('items-center gap-3 q-mt-sm'):
            ui.label('Collections')

            def open_add_to_collection_dialog():
                vps_id = (row_data.get('id') or '').strip()
                if not vps_id:
                    ui.notify('This table has no VPS ID. Associate it first.', type='warning')
                    return

                c = VPXCollections(str(COLLECTIONS_INI_PATH))
                existing = list(c.get_collections_name())

                d = ui.dialog().props('max-width=1080px')
                with d, ui.card().classes('w-[580px]'):
                    ui.label('Add to Collection').classes('text-lg font-bold')
                    ui.separator()
                    with ui.column().classes('w-full gap-2'):
                        with ui.row():
                            ui.label("Collections")
                        if existing:
                            coll_select = (
                                ui.select(
                                    {name: name for name in existing},
                                    label='Existing collections',
                                    value=None,
                                )
                                .props('filled clearable dense options-dense use-chips')
                                .classes('w-full')
                            )
                            ui.label('Pick one, or create a new one below.').classes('text-xs text-grey')
                        else:
                            coll_select = None
                            ui.label('No collections yet. Create one below.').classes('text-xs text-grey')

                        new_name = (
                            ui.input('New collection name')
                              .props('filled clearable dense')
                              .classes('w-full')
                        )
                    with ui.row().classes('justify-end gap-2 q-mt-md'):
                        def do_add():
                            name = ''
                            if new_name.value and str(new_name.value).strip():
                                name = str(new_name.value).strip()
                                if name not in c.get_collections_name():
                                    try:
                                        c.add_collection(name)
                                        c.save()
                                    except Exception as ex:
                                        ui.notify(f'Failed creating collection: {ex}', type='negative')
                                        return
                            elif coll_select and coll_select.value:
                                name = str(coll_select.value)
                            else:
                                ui.notify('Choose a collection or type a new name.', type='warning')
                                return

                            try:
                                c.add_vpsid(name, vps_id)
                                c.save()
                                ui.notify(f'Added to collection "{name}"', type='positive')
                                d.close()
                            except Exception as ex:
                                ui.notify(f'Failed adding to collection: {ex}', type='negative')
                        ui.button('Cancel', on_click=d.close)
                        ui.button('Add', on_click=do_add).props('color=primary')
                d.open()

            ui.button('Add to Collection', on_click=open_add_to_collection_dialog).props('icon=playlist_add color=primary')

            def open_remove_from_collection_dialog():
                vps_id = (row_data.get('id') or '').strip()
                if not vps_id:
                    ui.notify('This table has no VPS ID. Associate it first.', type='warning')
                    return

                c = VPXCollections(str(COLLECTIONS_INI_PATH))
                # find collections that currently contain this vps_id
                members: List[str] = []
                for name in c.get_collections_name():
                    try:
                        if vps_id in c.get_vpsids(name):
                            members.append(name)
                    except Exception:
                        pass

                d = ui.dialog().props('max-width=1080px')
                with d, ui.card().classes('w-[800px]'):
                    ui.label('Remove from Collection').classes('text-lg font-bold')
                    ui.separator()
                    if not members:
                        ui.label('This table is not in any collection.').classes('text-sm text-grey')
                    else:
                        sel = (
                            ui.select(
                                {name: name for name in members},
                                label='Collections containing this table',
                                value=[],
                                multiple=True,
                            )
                            .props('filled clearable dense options-dense use-chips')
                            .classes('w-full')
                        )
                        with ui.row().classes('justify-end gap-2 q-mt-md'):
                            ui.button('Cancel', on_click=d.close)
                            def do_remove():
                                selected = sel.value or []
                                if isinstance(selected, str):
                                    selected = [selected]
                                if not selected:
                                    ui.notify('Choose at least one collection.', type='warning')
                                    return
                                try:
                                    for name in selected:
                                        c.remove_vpsid(name, vps_id)
                                    c.save()
                                    ui.notify('Removed from selected collections', type='positive')
                                    d.close()
                                except Exception as ex:
                                    ui.notify(f'Failed removing: {ex}', type='negative')
                            ui.button('Remove', on_click=do_remove).props('color=negative')
                    if not members:
                        with ui.row().classes('justify-end q-mt-md'):
                            ui.button('Close', on_click=d.close)
                d.open()

            ui.button('Remove from Collection', on_click=open_remove_from_collection_dialog).props('icon=playlist_remove color=negative outline')

        with ui.row().classes('justify-end q-mt-md'):
            ui.button('Close', on_click=dlg.close)
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
