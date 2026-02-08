import os
import configparser
import logging
import asyncio
import zipfile
import io
from nicegui import ui, events, run, context
from pathlib import Path
import json
from typing import List, Dict, Optional, Callable
from common.vpxparser import VPXParser
from common.vpxcollections import VPXCollections
from clioptions import buildMetaData, vpxPatches
from queue import Queue
from platformdirs import user_config_dir

# Resolve project root and important paths explicitly
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VPSDB_JSON_PATH = PROJECT_ROOT / 'vpsdb.json'
CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
VPINFE_INI_PATH = CONFIG_DIR / 'vpinfe.ini'
COLLECTIONS_PATH = CONFIG_DIR / 'collections.ini'

# Load vpinfe.ini once to avoid repeated parsing
from common.iniconfig import IniConfig
_INI_CFG = IniConfig(str(VPINFE_INI_PATH))

#_vpsdb_cache: List[Dict] | None = None
_vpsdb_cache: Optional[List[Dict]] = None

def ensure_vpsdb_downloaded() -> bool:
    """
    Ensures vpsdb.json exists and is up-to-date.
    Downloads it if missing or outdated.
    Returns True if vpsdb is available, False otherwise.
    """
    global _vpsdb_cache
    from common.vpsdb import VPSdb
    try:
        # This will automatically download if missing or outdated
        vps = VPSdb(_INI_CFG.config['Settings']['tablerootdir'], _INI_CFG)
        # Clear cache so it reloads fresh data
        _vpsdb_cache = None
        return VPSDB_JSON_PATH.exists()
    except Exception as e:
        logger.error(f'Failed to ensure vpsdb: {e}')
        return VPSDB_JSON_PATH.exists()
# Ensure only one Missing Tables dialog at a time
_missing_tables_dialog: Optional[ui.dialog] = None
# Cache for scanned tables data (persists across page visits)
_tables_cache: Optional[List[Dict]] = None
_missing_cache: Optional[List[Dict]] = None


def get_vpsid_collections_map() -> Dict[str, List[str]]:
    """Build a map of VPS ID -> list of collection names (only vpsid type collections)."""
    vpsid_to_collections: Dict[str, List[str]] = {}
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        for collection_name in collections.get_collections_name():
            # Only consider vpsid type collections
            if collections.is_filter_based(collection_name):
                continue
            try:
                vpsids = collections.get_vpsids(collection_name)
                for vpsid in vpsids:
                    if vpsid not in vpsid_to_collections:
                        vpsid_to_collections[vpsid] = []
                    vpsid_to_collections[vpsid].append(collection_name)
            except Exception:
                pass
    except Exception:
        pass
    return vpsid_to_collections


def get_vpsid_collections() -> List[str]:
    """Get list of all vpsid-type collection names."""
    result = []
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        for collection_name in collections.get_collections_name():
            if not collections.is_filter_based(collection_name):
                result.append(collection_name)
    except Exception:
        pass
    return result


def add_table_to_collection(vpsid: str, collection_name: str) -> bool:
    """Add a table (by VPS ID) to a collection. Returns True on success."""
    global _tables_cache
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        collections.add_vpsid(collection_name, vpsid)
        collections.save()
        # Update the cache so the table list reflects the change
        if _tables_cache is not None:
            for row in _tables_cache:
                if row.get('id') == vpsid:
                    if 'collections' not in row:
                        row['collections'] = []
                    if collection_name not in row['collections']:
                        row['collections'].append(collection_name)
                    break
        return True
    except Exception as e:
        logger.error(f"Failed to add table to collection: {e}")
        return False


def sync_collections_to_cache():
    """Sync the tables cache with current collection memberships from disk.

    Call this after modifying collections outside of add_table_to_collection(),
    such as when removing tables from collections or deleting/renaming collections.
    """
    global _tables_cache
    if _tables_cache is None:
        return

    # Rebuild the VPS ID to collections map from disk
    vpsid_collections_map = get_vpsid_collections_map()

    # Update each cached row with current collection memberships
    for row in _tables_cache:
        vpsid = row.get('id', '')
        row['collections'] = vpsid_collections_map.get(vpsid, [])


def update_vpinfe_setting(table_path: str, key: str, value) -> bool:
    """Update a VPinFE setting in the table's .info file.

    Args:
        table_path: Path to the table directory
        key: The setting key (e.g., 'deletedNVRamOnClose')
        value: The value to set

    Returns:
        True on success, False on failure
    """
    try:
        table_dir = Path(table_path)
        info_file = table_dir / f"{table_dir.name}.info"

        if not info_file.exists():
            logger.error(f"Info file not found: {info_file}")
            return False

        # Read current data
        with open(info_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Ensure VPinFE section exists
        if 'VPinFE' not in data:
            data['VPinFE'] = {}

        # Update the setting
        data['VPinFE'][key] = value

        # Write back
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

        return True
    except Exception as e:
        logger.error(f"Failed to update VPinFE setting: {e}")
        return False


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
ACCEPT_VNI = ['.vni', '.VNI', '.pal', '.PAL']  # vni accepted extensions (case-insensitive)

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

    meta_path = table_folder / f"{table_folder.name}.info"
    meta = MetaConfig(str(meta_path))
    meta.writeConfigMeta(finalini)

    if download_media:
        from common.vpsdb import VPSdb      # your VPSdb wrapper that has downloadMediaForTable
        vps = VPSdb(_INI_CFG.config['Settings']['tablerootdir'], _INI_CFG)
        # Build a lightweight Table-like object with all attributes needed by downloadMediaForTable
        class _LightTable:
            def __init__(self, folder: Path, vpx: Path):
                self.tableDirName = folder.name
                self.fullPathTable = str(folder)
                self.fullPathVPXfile = str(vpx)
                # Media paths - set to None so downloadMediaForTable uses defaults
                self.BGImagePath = None
                self.DMDImagePath = None
                self.TableImagePath = None
                self.WheelImagePath = None
                self.CabImagePath = None
                self.realDMDImagePath = None
                self.realDMDColorImagePath = None
                self.FlyerImagePath = None
        pseudo_table = _LightTable(table_folder, vpx_file)
        vps.downloadMediaForTable(pseudo_table, vps_entry.get('id'), metaConfig=meta)


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
        vpinfe = raw.get("VPinFE", {})

        def get(*paths, default=""):
            """
            paths = [("VPXFile","rom"), ("Info","Rom"), ...]
            """
            for section, key in paths:
                src = {"Info": info, "VPXFile": vpx, "User": user, "VPinFE": vpinfe, "root": raw}.get(section)
                if src and key in src and src[key] not in ("", None):
                    return src[key]
            return default

        data = {
            # Display / identity (strip whitespace from name)
            "name": (get(("Info", "Title"), ("root", "name"), default=table_name) or "").strip(),
            "filename": get(("VPXFile", "filename"), default=f"{table_name}.vpx"),
            "id": get(("Info", "VPSId"), ("root", "id")),
            "ipdb_id": get(("Info", "IPDBId")),

            # Metadata
            "manufacturer": get(("Info", "Manufacturer"), ("VPXFile", "manufacturer")),
            "year": get(("Info", "Year"), ("VPXFile", "year")),
            "type": get(("Info", "Type"), ("VPXFile", "type")),
            "themes": get(("Info", "Themes"), default=[]),
            "authors": get(("Info", "Authors"), default=[]),
            "rom": get(("VPXFile", "rom"), ("Info", "Rom")),
            "version": get(("VPXFile", "version")),
            "filehash": get(("VPXFile", "filehash")),
            "vbshash": get(("VPXFile", "vbsHash")),

            # Detection flags (keys match JSON: detectNfozzy, detectFleep, detectSSF, etc.)
            "detectnfozzy": get(("VPXFile", "detectNfozzy")),
            "detectfleep": get(("VPXFile", "detectFleep")),
            "detectssf": get(("VPXFile", "detectSSF")),
            "detectlut": get(("VPXFile", "detectLUT")),
            "detectscorebit": get(("VPXFile", "detectScorebit")),
            "detectfastflips": get(("VPXFile", "detectFastflips")),
            "detectflex": get(("VPXFile", "detectFlex")),

            # Patching
            "patch_applied": get(("VPXFile", "patch_applied"), default=False),

            # Internal
            "table_path": table_dir,

            # Addon detection (check for directories)
            "pup_pack_exists": (Path(table_dir) / "pupvideos").is_dir(),
            "serum_exists": (Path(table_dir) / "serum").is_dir(),
            "vni_exists": (Path(table_dir) / "vni").is_dir(),
            "alt_sound_exists": (Path(table_dir) / "pinmame" / "altsound").is_dir(),

            # VPinFE settings
            "delete_nvram_on_close": vpinfe.get("deletedNVRamOnClose", False),
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

    # Build VPS ID to collections map
    vpsid_collections_map = get_vpsid_collections_map()

    for root, _, files in os.walk(tables_path):
        current_dir = os.path.basename(root)
        info_file = f"{current_dir}.info"

        if info_file in files:
            # Verify at least one .vpx file exists in the directory
            has_vpx = any(f.lower().endswith('.vpx') for f in files)
            if not has_vpx:
                # .info exists but no .vpx file - skip this entry
                continue

            meta_path = os.path.join(root, info_file)
            data = parse_table_info(meta_path)
            if data:
                data["table_path"] = root
                # Add collections membership
                vpsid = data.get("id", "")
                data["collections"] = vpsid_collections_map.get(vpsid, [])
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
            {'name': 'manufacturer', 'label': 'Manufacturer', 'field': 'manufacturer', 'align': 'left', 'sortable': True},
            {'name': 'year', 'label': 'Year', 'field': 'year', 'align': 'left', 'sortable': True},
            {'name': 'rom', 'label': 'ROM', 'field': 'rom', 'align': 'left', 'sortable': True},
            {'name': 'version', 'label': 'Version', 'field': 'version', 'align': 'left', 'sortable': True},
            {'name': 'filename', 'label': 'Filename', 'field': 'filename', 'align': 'left', 'sortable': True},
        ]

        def on_row_click(e: events.GenericEventArguments):
            if len(e.args) > 1:
                clicked_row = e.args[1]
                # Look up the actual row from the cache to get the latest data
                # (the clicked row from Quasar is a copy that may be stale)
                table_path = clicked_row.get('table_path', '')
                row_data = clicked_row
                if _tables_cache is not None and table_path:
                    for cached_row in _tables_cache:
                        if cached_row.get('table_path') == table_path:
                            row_data = cached_row
                            break
                # Pass update_table_display as callback to refresh table when dialog closes
                open_table_dialog(row_data, on_close=lambda: update_table_display())
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
                # Ensure vpsdb.json is downloaded and up-to-date
                if not VPSDB_JSON_PATH.exists():
                    if not silent:
                        ui.notify('Downloading VPSdb...', type='info')
                    await run.io_bound(ensure_vpsdb_downloaded)

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

                # Refresh filter options and apply current filters
                try:
                    refresh_filter_options()
                    update_table_display()
                except NameError:
                    # Filters not yet created, just show all rows
                    table._props['rows'] = table_rows
                    table.update()
                    title_label.set_text(f"Installed Tables ({len(table_rows)})")

                # Force browser layout recalculation to ensure table rows display properly
                await asyncio.sleep(0.05)
                # Trigger a window resize event to force the table to recalculate its layout
                try:
                    ui.run_javascript('window.dispatchEvent(new Event("resize"));')
                except RuntimeError:
                    pass  # Ignore if not in a valid UI context
                missing_button.text = f"Unmatched Tables ({len(missing_rows)})"
                # Update button color: green if 0, red if > 0
                btn_color = "positive" if len(missing_rows) == 0 else "negative"
                missing_button._props['color'] = btn_color
                missing_button.update()

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

        # --- Metadata build logic ---
        RUNNING = False

        def open_build_metadata_dialog():
            """Show dialog with buildmeta options and progress display."""
            nonlocal RUNNING
            if RUNNING:
                return

            dlg = ui.dialog().props('persistent max-width=700px')

            # State for this dialog instance
            dialog_state = {
                'running': False,
                'log_messages': [],
                'progress_q': Queue(),
                'log_q': Queue(),
            }

            with dlg, ui.card().classes('w-[650px]').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                ui.label('Build Metadata').classes('text-xl font-bold text-white')
                ui.separator()

                # Options section (hidden during build)
                options_container = ui.column().classes('gap-4 q-my-md w-full')
                with options_container:
                    update_all_switch = ui.switch('Update All Tables', value=False).classes('text-sm')
                    ui.label('Reparse all tables, even if .info already exists').classes('text-xs text-grey q-ml-lg')

                    download_media_switch = ui.switch('Download Media', value=True).classes('text-sm')
                    ui.label('Automatically download table images and media from VPSdb').classes('text-xs text-grey q-ml-lg')

                # Progress section (shown during build)
                progress_container = ui.column().classes('w-full gap-2')
                progress_container.visible = False

                with progress_container:
                    progressbar = ui.linear_progress(value=0.0, show_value=False).classes('w-full')
                    status_label = ui.label("Preparing...").classes("text-sm text-white")

                    # Log output
                    log_container = ui.column().classes("w-full bg-gray-900 rounded p-3 overflow-auto").style("max-height: 250px; font-family: monospace; font-size: 11px;")

                # Buttons
                buttons_container = ui.row().classes('justify-end gap-2 q-mt-md w-full')
                with buttons_container:
                    cancel_btn = ui.button('Cancel', on_click=dlg.close)
                    start_btn = ui.button('Start Build', icon='build').props('color=primary')
                    close_btn = ui.button('Close', on_click=dlg.close).props('color=primary')
                    close_btn.visible = False

                def pump_progress():
                    updated = False
                    while not dialog_state['progress_q'].empty():
                        updated = True
                        current, total, message = dialog_state['progress_q'].get_nowait()
                        if total and total > 0:
                            frac = max(0.0, min(1.0, current / total))
                            percent = int(round(frac * 100))
                            progressbar.value = frac
                            status_label.text = f'{message} — {percent}%'
                        else:
                            progressbar.value = 0
                            status_label.text = message or ''

                    while not dialog_state['log_q'].empty():
                        log_msg = dialog_state['log_q'].get_nowait()
                        dialog_state['log_messages'].append(log_msg)
                        if len(dialog_state['log_messages']) > 100:
                            dialog_state['log_messages'].pop(0)
                        updated = True

                    if updated:
                        log_container.clear()
                        with log_container:
                            for msg in dialog_state['log_messages']:
                                ui.label(msg).classes("text-white text-xs whitespace-pre-wrap")

                progress_timer = ui.timer(0.1, pump_progress, active=False)

                def progress_cb(current: int, total: int, message: str):
                    dialog_state['progress_q'].put((current, total, message))

                def log_cb(message: str):
                    dialog_state['log_q'].put(message)

                async def do_build():
                    nonlocal RUNNING
                    if dialog_state['running']:
                        return
                    dialog_state['running'] = True
                    RUNNING = True

                    # Switch UI to progress mode
                    options_container.visible = False
                    progress_container.visible = True
                    start_btn.visible = False
                    cancel_btn.visible = False

                    dialog_state['log_messages'].clear()
                    log_container.clear()
                    progressbar.value = 0
                    status_label.text = "Preparing..."
                    progress_timer.active = True

                    try:
                        result = await run.io_bound(
                            buildMetaData,
                            downloadMedia=bool(download_media_switch.value),
                            updateAll=bool(update_all_switch.value),
                            progress_cb=progress_cb,
                            log_cb=log_cb,
                        )
                        status_label.text = "Completed!"
                        progressbar.value = 1.0

                        # Show completion message in log
                        msg = f'Build complete. {result["found"]} scanned, {result.get("not_found", 0)} not found in VPSdb'
                        dialog_state['log_messages'].append(f"✓ {msg}")
                        log_container.clear()
                        with log_container:
                            for m in dialog_state['log_messages']:
                                ui.label(m).classes("text-white text-xs whitespace-pre-wrap")

                        # Refresh table list after completion
                        await perform_scan(silent=True)
                    except Exception as e:
                        logger.exception('buildMetaData failed')
                        status_label.text = f"Error: {e}"
                        dialog_state['log_messages'].append(f"✗ Error: {e}")
                        log_container.clear()
                        with log_container:
                            for m in dialog_state['log_messages']:
                                ui.label(m).classes("text-white text-xs whitespace-pre-wrap")
                    finally:
                        progress_timer.active = False
                        close_btn.visible = True
                        dialog_state['running'] = False
                        RUNNING = False

                start_btn.on_click(lambda: asyncio.create_task(do_build()))

            dlg.open()

        # --- UI Layout ---
        # Header section with page title and action buttons
        with ui.card().classes('w-full mb-4').style('background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); border-radius: 12px;'):
            with ui.row().classes('w-full justify-between items-center p-4 gap-4'):
                ui.label('Tables Management').classes('text-2xl font-bold text-white').style('flex-shrink: 0;')
                with ui.row().classes('gap-3 items-center flex-wrap'):
                    scan_btn = ui.button("Scan Tables", icon="refresh", on_click=open_build_metadata_dialog).props("color=white text-color=primary rounded")
                    patch_btn = ui.button("Apply Patches", icon="construction").props("color=secondary rounded")
                    # Start with green if no cached missing, will update after scan
                    initial_missing_count = len(_missing_cache) if _missing_cache else 0
                    initial_color = "positive" if initial_missing_count == 0 else "negative"
                    missing_button = ui.button("Unmatched", icon="warning").props(f"color={initial_color} rounded")

                    def open_patch_dialog():
                        """Show dialog for applying VPX patches with progress display."""
                        nonlocal RUNNING
                        if RUNNING:
                            return

                        dlg = ui.dialog().props('persistent max-width=600px')

                        dialog_state = {
                            'running': False,
                            'progress_q': Queue(),
                            'client': context.client,  # Capture client while in UI context
                        }

                        with dlg, ui.card().classes('w-[550px]').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                            ui.label('Apply VPX Patches').classes('text-xl font-bold text-white')
                            ui.separator()

                            # Info section
                            info_container = ui.column().classes('gap-2 q-my-md w-full')
                            with info_container:
                                ui.label('This will apply standalone patches to all tables that support them.').classes('text-sm text-grey')

                            # Progress section (shown during patching)
                            progress_container = ui.column().classes('w-full gap-2')
                            progress_container.visible = False

                            with progress_container:
                                patch_progressbar = ui.linear_progress(value=0.0, show_value=False).classes('w-full')
                                patch_status_label = ui.label("Preparing...").classes("text-sm text-white")

                            # Buttons
                            buttons_container = ui.row().classes('justify-end gap-2 q-mt-md w-full')
                            with buttons_container:
                                cancel_btn = ui.button('Cancel', on_click=dlg.close)
                                start_btn = ui.button('Start Patching', icon='construction').props('color=primary')
                                close_btn = ui.button('Close', on_click=dlg.close).props('color=primary')
                                close_btn.visible = False

                            def pump_patch_progress():
                                while not dialog_state['progress_q'].empty():
                                    current, total, message = dialog_state['progress_q'].get_nowait()
                                    if total and total > 0:
                                        frac = max(0.0, min(1.0, current / total))
                                        percent = int(round(frac * 100))
                                        patch_progressbar.value = frac
                                        patch_status_label.text = f'{message} — {percent}%'
                                    else:
                                        patch_progressbar.value = 0
                                        patch_status_label.text = message or ''

                            patch_progress_timer = ui.timer(0.1, pump_patch_progress, active=False)

                            def patch_progress_cb(current: int, total: int, message: str):
                                dialog_state['progress_q'].put((current, total, message))

                            async def do_patch():
                                nonlocal RUNNING
                                if dialog_state['running']:
                                    return
                                dialog_state['running'] = True
                                RUNNING = True

                                # Use client captured when dialog was created
                                client = dialog_state['client']

                                # Switch UI to progress mode
                                with client:
                                    info_container.visible = False
                                    progress_container.visible = True
                                    start_btn.visible = False
                                    cancel_btn.visible = False

                                    patch_progressbar.value = 0
                                    patch_status_label.text = "Preparing..."
                                    patch_progress_timer.active = True

                                try:
                                    await run.io_bound(vpxPatches, progress_cb=patch_progress_cb)
                                    with client:
                                        patch_status_label.text = "Completed!"
                                        patch_progressbar.value = 1.0
                                        ui.notify('VPX patches applied', type='positive')

                                    # Refresh tables silently to reflect patch_applied flag
                                    await perform_scan(silent=True)
                                except Exception as e:
                                    logger.exception('vpxPatches failed')
                                    with client:
                                        patch_status_label.text = f"Error: {e}"
                                        ui.notify(f'Error: {e}', type='negative')
                                finally:
                                    with client:
                                        patch_progress_timer.active = False
                                        close_btn.visible = True
                                    dialog_state['running'] = False
                                    RUNNING = False

                            start_btn.on_click(lambda: asyncio.create_task(do_patch()))

                        dlg.open()

                    patch_btn.on_click(open_patch_dialog)

        # Use cached data if available, otherwise start with empty
        initial_rows = _tables_cache if _tables_cache is not None else []
        initial_missing = _missing_cache if _missing_cache is not None else []

        # --- Filter state and functions ---
        filter_state = {
            'search': '',
            'manufacturer': 'All',
            'year': 'All',
            'theme': 'All',
            'table_type': 'All',
            'has_pup_pack': False,
        }

        def get_filter_options_from_cache():
            """Extract unique filter values from cached tables."""
            tables = _tables_cache or []
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
            """Filter the cached tables based on current filter state."""
            tables = _tables_cache or []
            result = tables

            # Search filter (name or filename)
            search_term = filter_state['search'].lower().strip()
            if search_term:
                result = [
                    t for t in result
                    if search_term in (t.get('name') or '').lower()
                    or search_term in (t.get('filename') or '').lower()
                ]

            # Manufacturer filter
            if filter_state['manufacturer'] != 'All':
                result = [t for t in result if t.get('manufacturer') == filter_state['manufacturer']]

            # Year filter
            if filter_state['year'] != 'All':
                result = [t for t in result if str(t.get('year', '')) == filter_state['year']]

            # Theme filter
            if filter_state['theme'] != 'All':
                result = [
                    t for t in result
                    if filter_state['theme'] in (t.get('themes') or [])
                    or t.get('themes') == filter_state['theme']
                ]

            # Table type filter
            if filter_state['table_type'] != 'All':
                result = [t for t in result if t.get('type') == filter_state['table_type']]

            # PUP Pack filter
            if filter_state['has_pup_pack']:
                result = [t for t in result if t.get('pup_pack_exists', False)]

            # Sort by name
            result.sort(key=lambda r: (r.get('name') or '').lower())
            return result

        def update_table_display():
            """Update the table with filtered results."""
            filtered = apply_filters()
            table._props['rows'] = filtered
            table.update()
            # Update title with filtered count
            total = len(_tables_cache or [])
            shown = len(filtered)
            if shown == total:
                title_label.set_text(f"Installed Tables ({total})")
            else:
                title_label.set_text(f"Installed Tables ({shown} of {total})")

        def on_search_change(e: events.ValueChangeEventArguments):
            filter_state['search'] = e.value or ''
            update_table_display()

        def on_manufacturer_change(e: events.ValueChangeEventArguments):
            filter_state['manufacturer'] = e.value or 'All'
            update_table_display()

        def on_year_change(e: events.ValueChangeEventArguments):
            filter_state['year'] = e.value or 'All'
            update_table_display()

        def on_theme_change(e: events.ValueChangeEventArguments):
            filter_state['theme'] = e.value or 'All'
            update_table_display()

        def on_table_type_change(e: events.ValueChangeEventArguments):
            filter_state['table_type'] = e.value or 'All'
            update_table_display()

        def on_pup_pack_change(e: events.ValueChangeEventArguments):
            filter_state['has_pup_pack'] = e.value or False
            update_table_display()

        def clear_filters():
            filter_state['search'] = ''
            filter_state['manufacturer'] = 'All'
            filter_state['year'] = 'All'
            filter_state['theme'] = 'All'
            filter_state['table_type'] = 'All'
            filter_state['has_pup_pack'] = False
            search_input.value = ''
            manufacturer_select.value = 'All'
            year_select.value = 'All'
            theme_select.value = 'All'
            table_type_select.value = 'All'
            pup_pack_checkbox.value = False
            table._props['pagination']['page'] = 1
            update_table_display()

        def refresh_filter_options():
            """Update filter dropdowns with current cache values."""
            opts = get_filter_options_from_cache()
            manufacturer_select.options = opts['manufacturers']
            year_select.options = opts['years']
            theme_select.options = opts['themes']
            table_type_select.options = opts['table_types']
            manufacturer_select.update()
            year_select.update()
            theme_select.update()
            table_type_select.update()

        # Table title - centered above the filters
        title_label = ui.label("Installed Tables").classes('text-xl font-semibold text-center w-full py-2')

        # --- Search and Filter UI ---
        with ui.card().classes('w-full mb-4').style('border-radius: 8px; background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155;'):
            with ui.row().classes('w-full items-center gap-4 p-4 flex-wrap'):
                # Search input
                search_input = ui.input(placeholder='Search tables...').props('outlined dense clearable').classes('flex-grow').style('min-width: 200px;')
                search_input.on_value_change(on_search_change)

                # Filter dropdowns
                filter_opts = get_filter_options_from_cache()

                manufacturer_select = ui.select(
                    label='Manufacturer',
                    options=filter_opts['manufacturers'],
                    value='All'
                ).props('outlined dense').classes('w-40')
                manufacturer_select.on_value_change(on_manufacturer_change)

                year_select = ui.select(
                    label='Year',
                    options=filter_opts['years'],
                    value='All'
                ).props('outlined dense').classes('w-32')
                year_select.on_value_change(on_year_change)

                theme_select = ui.select(
                    label='Theme',
                    options=filter_opts['themes'],
                    value='All'
                ).props('outlined dense').classes('w-40')
                theme_select.on_value_change(on_theme_change)

                table_type_select = ui.select(
                    label='Type',
                    options=filter_opts['table_types'],
                    value='All'
                ).props('outlined dense').classes('w-28')
                table_type_select.on_value_change(on_table_type_change)

                # PUP Pack checkbox
                pup_pack_checkbox = ui.checkbox('PUP Pack', value=False).classes('text-white')
                pup_pack_checkbox.on_value_change(on_pup_pack_change)

                # Clear filters button
                ui.button(icon='clear_all', on_click=clear_filters).props('flat round').tooltip('Clear all filters')

        # Batch action bar for adding multiple tables to a collection at once
        batch_bar = ui.card().classes('w-full mb-2').style(
            'border-radius: 8px; background: linear-gradient(145deg, #1e3a5f 0%, #2d5a87 100%); '
            'border: 1px solid #3b82f6;'
        )
        batch_bar.visible = False
        with batch_bar:
            with ui.row().classes('w-full items-center gap-4 p-3'):
                batch_label = ui.label('0 tables selected').classes('text-white font-medium')
                batch_collection_select = ui.select(
                    label='Add to Collection',
                    options=get_vpsid_collections(),
                    value=None
                ).props('outlined dense dark').classes('w-48')
                batch_add_btn = ui.button('Add to Collection', icon='playlist_add').props('color=white text-color=primary')

        def on_selection_change(e):
            selected = e.selection
            if selected:
                batch_bar.visible = True
                count = len(selected)
                batch_label.set_text(f'{count} table{"s" if count != 1 else ""} selected')
            else:
                batch_bar.visible = False

        # Create a scrollable container for the table with proper height constraint
        table_container = ui.column().classes("w-full").style("flex: 1; overflow: hidden; display: flex;")

        with table_container:
            table = (
                ui.table(columns=columns, rows=initial_rows, row_key='filename', selection='multiple',
                         on_select=on_selection_change, pagination={'rowsPerPage': 25})
                  .props('rows-per-page-options="[25,50,100]" sort-by="name" sort-order="asc"')
                  .on('row-click', on_row_click)
                  .classes("w-full cursor-pointer")
                  .style("flex: 1; overflow: auto;")
            )
            # Add custom slot for name column to include IPDB, VPS links, and collections
            # Define colors for collections - will cycle through these
            collection_colors = ['purple-8', 'teal-8', 'pink-8', 'cyan-8', 'amber-8', 'lime-8', 'indigo-8', 'orange-8']
            table.add_slot('body-cell-name', '''
                <q-td :props="props">
                    <div style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span>{{ props.value }}</span>
                            <a v-if="props.row.ipdb_id"
                               :href="'https://www.ipdb.org/machine.cgi?id=' + props.row.ipdb_id"
                               target="_blank"
                               @click.stop
                               style="text-decoration: none;">
                                <q-badge color="yellow-8" text-color="black" label="IPDB" style="font-size: 10px; padding: 2px 6px; cursor: pointer;" />
                            </a>
                            <a v-if="props.row.id"
                               :href="'https://virtualpinballspreadsheet.github.io/?game=' + props.row.id"
                               target="_blank"
                               @click.stop
                               style="text-decoration: none;">
                                <q-badge color="blue-8" text-color="white" label="VPS" style="font-size: 10px; padding: 2px 6px; cursor: pointer;" />
                            </a>
                        </div>
                        <div v-if="props.row.collections && props.row.collections.length > 0" style="display: flex; flex-wrap: wrap; gap: 4px;">
                            <q-badge v-for="(col, index) in props.row.collections" :key="col"
                                     :color="['purple-8', 'teal-8', 'pink-8', 'cyan-8', 'amber-8', 'lime-8', 'indigo-8', 'orange-8'][index % 8]"
                                     text-color="white" :label="col" style="font-size: 9px; padding: 2px 6px;" />
                        </div>
                    </div>
                </q-td>
            ''')

        # Wire up batch add-to-collection button
        def on_batch_add():
            collection = batch_collection_select.value
            if not collection:
                ui.notify('Please select a collection', type='warning')
                return
            selected = table.selected
            if not selected:
                ui.notify('No tables selected', type='warning')
                return
            added = 0
            skipped = 0
            for row in selected:
                vpsid = row.get('id', '')
                if vpsid:
                    if add_table_to_collection(vpsid, collection):
                        added += 1
                else:
                    skipped += 1
            if added > 0:
                msg = f'Added {added} table{"s" if added != 1 else ""} to {collection}'
                if skipped > 0:
                    msg += f' ({skipped} skipped - no VPS ID)'
                ui.notify(msg, type='positive')
                table.selected.clear()
                table.update()
                batch_bar.visible = False
                batch_collection_select.value = None
                update_table_display()
            else:
                ui.notify('No tables could be added (missing VPS IDs)', type='warning')

        batch_add_btn.on_click(on_batch_add)

        # Update missing button if we have cached data
        if _missing_cache is not None:
            missing_button.text = f"Unmatched Tables ({len(_missing_cache)})"
            # Update button color: green if 0, red if > 0
            btn_color = "positive" if len(_missing_cache) == 0 else "negative"
            missing_button._props['color'] = btn_color
            missing_button.on('click', lambda: open_missing_tables_dialog(
                _missing_cache,
                on_close=lambda: asyncio.create_task(perform_scan(silent=True))
            ))

        # Function to refresh the table display
        async def refresh_table_on_startup():
            if _tables_cache is not None:
                # Refresh filter options and apply filters from cache
                refresh_filter_options()
                update_table_display()
            else:
                # No cache, run the scan
                await perform_scan(silent=True)
            # Trigger resize to ensure proper rendering
            try:
                ui.run_javascript('window.dispatchEvent(new Event("resize"));')
            except RuntimeError:
                pass

        # Use a one-shot timer to ensure table loads after UI is ready
        async def startup_refresh():
            await asyncio.sleep(0.2)  # Wait for UI to be ready
            await refresh_table_on_startup()

        ui.timer(0.1, lambda: asyncio.create_task(startup_refresh()), once=True)

def open_table_dialog(row_data: dict, on_close: Optional[Callable[[], None]] = None):
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

    dlg = ui.dialog()
    with dlg, ui.card().classes('table-dialog-card').style('width: 1000px; max-width: 85vw;'):
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
                # List fields that need special handling (join with comma)
                list_fields = [
                    ('authors', 'Authors', 'person'),
                    ('themes', 'Themes', 'style'),
                ]
                # Fields with long values that need full width
                long_fields = [
                    ('filehash', 'File Hash', 'tag'),
                    ('vbshash', 'VBS Hash', 'code'),
                ]

                with ui.grid(columns=2).classes('w-full gap-3'):
                    for key, label, icon in display_fields:
                        value = row_data.get(key, '')
                        if value:  # Only show non-empty fields
                            with ui.row().classes('detail-row items-center gap-2 w-full'):
                                ui.icon(icon, size='18px').classes('text-blue-400')
                                ui.label(label).classes('detail-label')
                                ui.label(str(value)).classes('detail-value')

                    # Render list fields (authors, themes) - join lists with comma
                    for key, label, icon in list_fields:
                        value = row_data.get(key, [])
                        if value:
                            display_value = ', '.join(value) if isinstance(value, list) else str(value)
                            with ui.row().classes('detail-row items-center gap-2 w-full'):
                                ui.icon(icon, size='18px').classes('text-blue-400')
                                ui.label(label).classes('detail-label')
                                ui.label(display_value).classes('detail-value')

                # Render hash fields side by side
                with ui.row().classes('w-full gap-3'):
                    for key, label, icon in long_fields:
                        value = row_data.get(key, '')
                        if value:
                            with ui.row().classes('detail-row items-center gap-2').style('flex: 1; flex-wrap: nowrap;'):
                                ui.icon(icon, size='18px').classes('text-blue-400').style('flex-shrink: 0;')
                                ui.label(label).style('color: #94a3b8; font-size: 0.85rem; flex-shrink: 0;')
                                ui.label(str(value)).classes('detail-value').style('font-family: monospace; font-size: 0.7rem;')

                # Detection flags row - show all detection flags with their status
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
                    with ui.row().classes('detail-row items-center gap-2 w-full mt-2'):
                        ui.icon('settings_suggest', size='18px').classes('text-blue-400')
                        ui.label('Features').classes('detail-label')
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

                # Detected Addons row
                addon_fields = [
                    ('pup_pack_exists', 'PUP Pack', 'video_library', 'purple'),
                    ('serum_exists', 'Serum', 'palette', 'orange'),
                    ('vni_exists', 'VNI', 'palette', 'cyan'),
                    ('alt_sound_exists', 'Alt Sound', 'music_note', 'green'),
                ]

                with ui.row().classes('detail-row items-center gap-2 w-full mt-2'):
                    ui.icon('extension', size='18px').classes('text-blue-400')
                    ui.label('Addons').classes('detail-label')
                    with ui.row().classes('gap-2 flex-wrap'):
                        for key, label, icon, color in addon_fields:
                            exists = row_data.get(key, False)
                            if exists:
                                with ui.row().classes('items-center gap-1'):
                                    ui.icon(icon, size='16px').classes(f'text-{color}-400')
                                    ui.badge(label, color='positive').props('rounded')
                            else:
                                ui.badge(label, color='grey').props('rounded outline')

            # Collections section - add table to collection
            vpsid = row_data.get('id', '')
            current_collections = row_data.get('collections', [])
            available_collections = get_vpsid_collections()

            if vpsid and available_collections:
                with ui.card().classes('w-full p-4').style('background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 8px;'):
                    ui.label('Collections').classes('text-lg font-semibold text-white mb-3')

                    # Show current collections
                    if current_collections:
                        with ui.row().classes('gap-2 flex-wrap mb-3'):
                            ui.label('Member of:').classes('text-sm text-gray-400')
                            for col_name in current_collections:
                                ui.badge(col_name, color='purple').props('rounded')

                    # Dropdown to add to collection
                    # Filter out collections the table is already in
                    collections_to_add = [c for c in available_collections if c not in current_collections]

                    if collections_to_add:
                        with ui.row().classes('items-center gap-3 w-full'):
                            collection_select = ui.select(
                                label='Add to Collection',
                                options=collections_to_add,
                                value=None
                            ).props('outlined dense').classes('flex-grow')

                            def on_add_to_collection():
                                selected = collection_select.value
                                if not selected:
                                    ui.notify('Please select a collection', type='warning')
                                    return
                                if add_table_to_collection(vpsid, selected):
                                    ui.notify(f'Added to {selected}', type='positive')
                                    # add_table_to_collection already updates the cache,
                                    # just update the dropdown options
                                    new_options = [c for c in collection_select.options if c != selected]
                                    collection_select.options = new_options
                                    collection_select.value = None
                                    collection_select.update()
                                else:
                                    ui.notify('Failed to add to collection', type='negative')

                            ui.button('Add', icon='add', on_click=on_add_to_collection).props('color=primary')
                    else:
                        ui.label('Table is in all available collections').classes('text-sm text-gray-400')

            # VPinFE Settings section
            with ui.card().classes('w-full p-4').style('background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 8px;'):
                ui.label('VPinFE Settings').classes('text-lg font-semibold text-white mb-3')

                table_path_str = row_data.get('table_path', '')
                delete_nvram_value = row_data.get('delete_nvram_on_close', False)

                with ui.row().classes('items-center gap-3'):
                    def on_delete_nvram_change(e):
                        new_value = e.value
                        if update_vpinfe_setting(table_path_str, 'deletedNVRamOnClose', new_value):
                            row_data['delete_nvram_on_close'] = new_value
                            # Also update the cache so the value persists across dialog opens
                            if _tables_cache is not None:
                                for cached_row in _tables_cache:
                                    if cached_row.get('table_path') == table_path_str:
                                        cached_row['delete_nvram_on_close'] = new_value
                                        break
                            ui.notify('Setting saved', type='positive')
                        else:
                            ui.notify('Failed to save setting', type='negative')
                            # Revert checkbox
                            e.sender.value = not new_value

                    nvram_checkbox = ui.checkbox('Delete NVRAM on close', value=delete_nvram_value)
                    nvram_checkbox.on_value_change(on_delete_nvram_change)
                    ui.label('Remove NVRAM file when table exits').classes('text-xs text-gray-400')

            # Addons section
            with ui.expansion('Install Addons', icon='extension').classes('w-full').style('background: rgba(15, 23, 42, 0.4); border-radius: 8px;'):
                table_path = Path(row_data.get('table_path', ''))
                rom_name = (row_data.get('rom') or '').strip()

                with ui.column().classes('gap-4 p-2'):
                    # Pupvideos uploader (zip file)
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('video_library', size='24px').classes('text-purple-400')
                            with ui.column().classes('gap-0'):
                                ui.label('PupVideos').classes('font-medium text-white')
                                ui.label('Upload .zip file to extract to pupvideos folder').classes('text-xs text-gray-400')
                        def on_pup_upload(e):
                            ext = Path(e.name).suffix.lower()
                            if ext != '.zip':
                                ui.notify('Only .zip files accepted', type='negative')
                                return
                            # Read content from SpooledTemporaryFile if needed
                            content = e.content.read() if hasattr(e.content, 'read') else e.content
                            try:
                                dest_dir = table_path / 'pupvideos'
                                ensure_dir(dest_dir)
                                with zipfile.ZipFile(io.BytesIO(content), 'r') as zf:
                                    zf.extractall(dest_dir)
                                ui.notify(f'Extracted {e.name} to pupvideos/', type='positive')
                            except zipfile.BadZipFile:
                                ui.notify('Invalid zip file', type='negative')
                            except Exception as ex:
                                ui.notify(f'Extract failed: {ex}', type='negative')
                        ui.upload(on_upload=on_pup_upload, multiple=False).props('flat color=primary label="Upload .zip"')

                    # Serum uploader
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('palette', size='24px').classes('text-orange-400')
                            with ui.column().classes('gap-0'):
                                ui.label('Serum').classes('font-medium text-white')
                                ui.label('Upload .cRZ color files (requires ROM)').classes('text-xs text-gray-400')
                        def on_altcolor_upload(e):
                            if not rom_name:
                                ui.notify('ROM not found. Update metadata first.', type='warning')
                                return
                            ext = Path(e.name).suffix
                            if ext not in ACCEPT_CRZ:
                                ui.notify('Only .cRZ files accepted', type='negative')
                                return
                            dest = table_path / 'serum' / rom_name / e.name
                            # Read content from SpooledTemporaryFile if needed
                            content = e.content.read() if hasattr(e.content, 'read') else e.content
                            save_upload_bytes(dest, content)
                            ui.notify(f'Saved: {e.name}', type='positive')
                        ui.upload(on_upload=on_altcolor_upload, multiple=False).props('flat color=primary label="Upload .cRZ"')

                    # VNI uploader
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('palette', size='24px').classes('text-cyan-400')
                            with ui.column().classes('gap-0'):
                                ui.label('VNI').classes('font-medium text-white')
                                ui.label('Upload .vni and .pal files (requires ROM)').classes('text-xs text-gray-400')
                        def on_vni_upload(e):
                            if not rom_name:
                                ui.notify('ROM not found. Update metadata first.', type='warning')
                                return
                            ext = Path(e.name).suffix
                            if ext not in ACCEPT_VNI:
                                ui.notify('Only .vni and .pal files accepted', type='negative')
                                return
                            dest = table_path / 'vni' / rom_name / e.name
                            # Read content from SpooledTemporaryFile when multiple=True
                            content = e.content.read() if hasattr(e.content, 'read') else e.content
                            save_upload_bytes(dest, content)
                            ui.notify(f'Saved: {e.name}', type='positive')
                        ui.upload(on_upload=on_vni_upload, multiple=True).props('flat color=primary label="Upload .vni/.pal"')

                    # AltSound uploader
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('music_note', size='24px').classes('text-green-400')
                            with ui.column().classes('gap-0'):
                                ui.label('Serum (AltSound)').classes('font-medium text-white')
                                ui.label('Upload sound pack files (requires ROM)').classes('text-xs text-gray-400')
                        def on_altsound_upload(e):
                            if not rom_name:
                                ui.notify('ROM not found. Update metadata first.', type='warning')
                                return
                            dest = table_path / 'pinmame' / 'altsound' / rom_name / e.name
                            # Read content from SpooledTemporaryFile if needed
                            content = e.content.read() if hasattr(e.content, 'read') else e.content
                            save_upload_bytes(dest, content)
                            ui.notify(f'Saved: {e.name}', type='positive')
                        ui.upload(on_upload=on_altsound_upload, multiple=True).props('flat color=primary label="Upload"')

        # Footer with close button
        with ui.row().classes('w-full justify-end p-4 pt-0'):
            def close_dialog():
                dlg.close()
                if on_close:
                    on_close()
            ui.button('Close', icon='close', on_click=close_dialog).props('flat color=grey')
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
    dlg = ui.dialog().props('max-width=1080px persistent')
    dialog_state = {'busy': False}

    with dlg, ui.card().classes('w-[960px] max-w-[95vw]').style('position: relative; overflow: hidden;'):
        ui.label(f"Match VPS ID → {missing_row['folder']}").classes('text-lg font-bold')
        ui.separator()

        # Disclaimer about what Associate button does
        with ui.row().classes('w-full items-start gap-2 q-pa-sm').style('background: rgba(59, 130, 246, 0.15); border-radius: 6px; border-left: 3px solid #3b82f6;'):
            ui.icon('info', size='sm').classes('text-blue-400')
            ui.label(
                'Clicking "Associate" will: rename the folder to "TABLE NAME (MANUFACTURER YEAR)" format, '
                'create a metadata file (.info), and download media images from vpinmediadb.'
            ).classes('text-sm text-gray-300')

        results_container = ui.column().classes('gap-1 w-full q-mt-sm').style('max-height: 55vh; overflow:auto;')

        # Loading overlay (hidden by default) - positioned over the entire card
        loading_overlay = ui.element('div').style(
            'position: absolute; top: 0; left: 0; right: 0; bottom: 0; '
            'background: rgba(15, 23, 42, 0.95); z-index: 1000; '
            'display: none; flex-direction: column; align-items: center; justify-content: center;'
        )
        with loading_overlay:
            with ui.column().classes('items-center justify-center gap-4 w-full'):
                ui.spinner('dots', size='xl', color='blue')
                loading_label = ui.label('Downloading media...').classes('text-white text-lg text-center')

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
                    with ui.row().classes('items-center w-full q-py-xs border-b gap-2').style('flex-wrap: nowrap;'):
                        ui.label(f"{name} — {manuf} — {year} (ID: {vid})").classes('text-sm').style('flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;')

                        async def _on_assoc(it=it, vid=vid):
                            if dialog_state['busy']:
                                return
                            dialog_state['busy'] = True

                            # Show loading overlay
                            loading_overlay.style(add='display: flex;', remove='display: none;')
                            loading_label.set_text('Renaming folder...')

                            try:
                                old_path = Path(missing_row['path'])
                                # Build new folder name: TABLE_NAME (MANUFACTURER YEAR)
                                new_name = it.get('name', '')
                                new_manuf = it.get('manufacturer') or it.get('mfg') or ''
                                new_year = it.get('year') or ''
                                if new_manuf and new_year:
                                    new_folder_name = f"{new_name} ({new_manuf} {new_year})"
                                elif new_manuf:
                                    new_folder_name = f"{new_name} ({new_manuf})"
                                elif new_year:
                                    new_folder_name = f"{new_name} ({new_year})"
                                else:
                                    new_folder_name = new_name
                                # Sanitize folder name (remove invalid characters)
                                new_folder_name = "".join(c for c in new_folder_name if c not in '<>:"/\\|?*')
                                new_path = old_path.parent / new_folder_name

                                # Rename folder if the name is different
                                if old_path != new_path:
                                    if new_path.exists():
                                        ui.notify(f"Cannot rename: folder '{new_folder_name}' already exists", type='negative')
                                        loading_overlay.style(add='display: none;', remove='display: flex;')
                                        dialog_state['busy'] = False
                                        return
                                    old_path.rename(new_path)
                                    folder_path = new_path
                                else:
                                    folder_path = old_path

                                # Update loading message and run download in background
                                loading_label.set_text('Creating metadata and downloading media...')
                                await run.io_bound(associate_vps_to_folder, folder_path, it, True)

                                ui.notify(f"Associated with VPS ID '{vid}' and downloaded media", type='positive')
                                dlg.close()
                                if callable(refresh_missing):
                                    refresh_missing()
                                if callable(refresh_installed):
                                    refresh_installed()
                            except Exception as ex:
                                logger.exception('Association failed')
                                ui.notify(f'Failed: {ex}', type='negative')
                                loading_overlay.style(add='display: none;', remove='display: flex;')
                                dialog_state['busy'] = False

                        ui.button('Associate', on_click=_on_assoc).props('color=primary').style('flex-shrink: 0;')

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
