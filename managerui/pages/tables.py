import os
import logging
import asyncio
from nicegui import ui, events, run, context
from pathlib import Path
import json
from typing import List, Dict, Optional, Callable
from queue import Queue
from managerui.filters import apply_table_filters, build_table_filter_options
from managerui.paths import VPINFE_INI_PATH, get_tables_path as resolve_tables_path
from managerui.pages.table_detail_dialog import open_table_dialog
from managerui.pages.table_import_dialog import open_import_table_dialog
from managerui.pages.table_match_dialog import open_match_vps_dialog, open_missing_tables_dialog
from managerui.services import table_service
from managerui.services import table_index_service
from managerui.services.media_service import invalidate_media_cache
from managerui.ui_helpers import debounced_input, dialog_card, load_page_style

VPSDB_JSON_PATH = table_service.VPSDB_JSON_PATH

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
    ok = table_service.ensure_vpsdb_downloaded()
    _vpsdb_cache = None
    return ok
# Ensure only one Missing Tables dialog at a time
_missing_tables_dialog: Optional[ui.dialog] = None
# Cache compatibility helpers. Ownership lives in table_index_service.
def _tables_cache() -> Optional[List[Dict]]:
    return table_index_service.get_rows()


def _missing_cache() -> Optional[List[Dict]]:
    return table_index_service.get_missing_rows()


def normalize_table_rating(value) -> int:
    """Normalize rating values to an integer in the range 0..5."""
    return table_service.normalize_table_rating(value)


def get_vpsid_collections_map() -> Dict[str, List[str]]:
    """Build a map of VPS ID -> list of collection names (only vpsid type collections)."""
    return table_service.get_vpsid_collections_map()


def get_vpsid_collections() -> List[str]:
    """Get list of all vpsid-type collection names."""
    return table_service.get_vpsid_collections()


def add_table_to_collection(vpsid: str, collection_name: str) -> bool:
    """Add a table (by VPS ID) to a collection. Returns True on success."""
    try:
        if not table_service.add_table_to_collection(vpsid, collection_name):
            return False
        table_index_service.add_collection_membership(vpsid, collection_name)
        return True
    except Exception as e:
        logger.error(f"Failed to add table to collection: {e}")
        return False


def sync_collections_to_cache():
    """Sync the tables cache with current collection memberships from disk.

    Call this after modifying collections outside of add_table_to_collection(),
    such as when removing tables from collections or deleting/renaming collections.
    """
    table_index_service.sync_collection_memberships(get_vpsid_collections_map())


def update_vpinfe_setting(table_path: str, key: str, value) -> bool:
    """Update a VPinFE setting in the table's .info file.

    Args:
        table_path: Path to the table directory
        key: The setting key (e.g., 'deletedNVRamOnClose')
        value: The value to set

    Returns:
        True on success, False on failure
    """
    return table_service.update_vpinfe_setting(table_path, key, value)


def update_user_setting(table_path: str, key: str, value) -> bool:
    """Update a User setting in the table's .info file."""
    return table_service.update_user_setting(table_path, key, value)


def load_vpsdb() -> List[Dict]:
    global _vpsdb_cache
    _vpsdb_cache = table_service.load_vpsdb()
    return _vpsdb_cache

def search_vpsdb(term: str, limit: int = 50) -> List[Dict]:
    return table_service.search_vpsdb(term, limit)

ACCEPT_CRZ = ['.crz', '.cRZ', '.CRZ']  # altcolor accepted extensions (case-insensitive)
ACCEPT_VNI = ['.vni', '.VNI', '.pal', '.PAL']  # vni accepted extensions (case-insensitive)

def ensure_dir(p: Path) -> None:
    table_service.ensure_dir(p)

def save_upload_bytes(dest_file: Path, content: bytes) -> None:
    table_service.save_upload_bytes(dest_file, content)


# --- helper to create a .info file with a chosen VPS record for one folder ---

def associate_vps_to_folder(table_folder: Path, vps_entry: Dict, download_media: bool = False, user_media: bool = False) -> None:
    """
    Creates a `.info` file inside `table_folder` using the selected vps_entry and the VPX metadata.
    """
    table_service.associate_vps_to_folder(table_folder, vps_entry, download_media, user_media)


logger = logging.getLogger("vpinfe.manager.tables")

def get_tables_path() -> str:
    """Resolve tables path from vpinfe.ini [Settings] tablerootdir, fallback to ~/tables."""
    return resolve_tables_path()

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
            "name": (get(("VPinFE", "alttitle"), ("Info", "Title"), ("root", "name"), default=table_name) or "").strip(),
            "filename": get(("VPXFile", "filename"), default=f"{table_name}.vpx"),
            "vpsid": get(("Info", "VPSId"), ("root", "id")),
            "id": get(("VPinFE", "altvpsid"), ("Info", "VPSId"), ("root", "id")),
            "ipdb_id": get(("Info", "IPDBId")),
            "pinball_primer_tut": get(("Info", "PinballPrimerTut")),

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

            # Detection flags (canonical lowercase keys)
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

            # Addon detection (check for directories)
            "pup_pack_exists": (Path(table_dir) / "pupvideos").is_dir(),
            "serum_exists": (Path(table_dir) / "serum").is_dir(),
            "vni_exists": (Path(table_dir) / "vni").is_dir(),
            "alt_sound_exists": (Path(table_dir) / "pinmame" / "altsound").is_dir(),

            # VPinFE settings
            "delete_nvram_on_close": vpinfe.get("deletedNVRamOnClose", False),
            "altlauncher": (vpinfe.get("altlauncher", "") or "").strip(),
            "alttitle": (vpinfe.get("alttitle", "") or "").strip(),
            "altvpsid": (vpinfe.get("altvpsid", "") or "").strip(),
            "frontend_dof_event": (user.get("FrontendDOFEvent", "") or "").strip(),
            "rating": normalize_table_rating(user.get("Rating", 0)),
        }

        return data

    except Exception as e:
        logger.error(f"Error reading {info_path}: {e}")
        return {}

def scan_tables(silent: bool = False):
    tables_path = get_tables_path()
    if not os.path.exists(tables_path):
        logger.warning(f"Tables path does not exist: {tables_path}. Skipping scan.")
        if not silent:
            ui.notify("Tables path does not exist. Please, verify your vpinfe.ini settings", type="negative")
        return []
    return table_service.scan_table_rows(reload=False)

def scan_missing_tables():
    return table_service.scan_missing_table_rows(reload=False)


def load_metadata_from_ini():
    return scan_tables()

def render_panel(tab=None):
    with ui.column().classes('w-full'):
        load_page_style("tables.css")
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
                cached_row = table_index_service.find_by_path(table_path) if table_path else None
                if cached_row is not None:
                    row_data = cached_row
                # Pass update_table_display as callback to refresh table when dialog closes
                open_table_dialog(row_data, on_close=lambda: update_table_display())
            else:
                ui.notify("Error: Unexpected row click event format.", type="negative")

        async def perform_scan(*_, silent: bool = False):
            """Scans for tables asynchronously and updates the UI.
            If silent=True, suppress user notifications.
            """
            logger.info("Scanning tables...")
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

                # Pull rows from the shared startup-backed repository
                table_rows, missing_rows = await run.io_bound(table_index_service.scan_table_data, True)

                # Update UI components (default sort by Name; force refresh by reassigning rows)
                try:
                    table_rows.sort(key=lambda r: (r.get('name') or '').lower())
                except Exception:
                    pass

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

            with dlg, dialog_card("650px"):
                ui.label('Build Metadata').classes('text-xl font-bold').style('color: var(--ink);')
                ui.separator()

                # Options section (hidden during build)
                options_container = ui.column().classes('gap-4 q-my-md w-full')
                with options_container:
                    update_all_switch = ui.switch('Update All Tables', value=False).classes('text-sm')
                    ui.label('Reparse all tables, even if .info already exists').classes('text-xs q-ml-lg').style('color: var(--ink-muted);')

                    download_media_switch = ui.switch('Download Media', value=True).classes('text-sm')
                    ui.label('Automatically download table images and media from VPinMediaDB').classes('text-xs q-ml-lg').style('color: var(--ink-muted);')

                # Progress section (shown during build)
                progress_container = ui.column().classes('w-full gap-2')
                progress_container.visible = False

                with progress_container:
                    progressbar = ui.linear_progress(value=0.0, show_value=False).classes('w-full')
                    status_label = ui.label("Preparing...").classes("text-sm").style('color: var(--ink);')

                    # Log output
                    log_container = ui.column().classes("w-full p-3 overflow-auto").style("max-height: 250px; font-family: monospace; font-size: 11px; color: var(--ink); background: var(--surface); border: 1px solid var(--neon-purple); border-radius: var(--radius);")

                # Buttons
                buttons_container = ui.row().classes('justify-end gap-2 q-mt-md w-full')
                with buttons_container:
                    cancel_btn = ui.button('Cancel', on_click=dlg.close).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')
                    start_btn = ui.button('Start Build', icon='build').style('color: var(--neon-cyan) !important; background: var(--surface) !important; border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;')
                    close_btn = ui.button('Close', on_click=dlg.close).style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')
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
                                ui.label(msg).classes("text-xs whitespace-pre-wrap").style('color: var(--ink);')

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
                            table_service.build_metadata,
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

                        # Invalidate media cache so media page shows fresh data
                        invalidate_media_cache()

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
        with ui.card().classes('w-full mb-4 manager-page-header'):
            with ui.row().classes('w-full justify-between items-center p-4 gap-4'):
                ui.label('Tables Management').classes('text-2xl font-bold').style('color: var(--ink);').style('flex-shrink: 0;')
                with ui.row().classes('gap-3 items-center flex-wrap'):
                    scan_btn = ui.button("Scan Tables", icon="refresh", on_click=open_build_metadata_dialog).style('color: var(--ink) !important; background: var(--neon-purple) !important; border-radius: 18px;')
                    patch_btn = ui.button("Apply Patches", icon="construction").props("color=secondary rounded")
                    # Start with green if no cached missing, will update after scan
                    cached_missing = _missing_cache()
                    initial_missing_count = len(cached_missing) if cached_missing else 0
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

                        with dlg, dialog_card("550px"):
                            ui.label('Apply VPX Patches').classes('text-xl font-bold').style('color: var(--ink);')
                            ui.separator()

                            # Info section
                            info_container = ui.column().classes('gap-2 q-my-md w-full')
                            with info_container:
                                ui.label('This will apply standalone patches to all tables that support them.').classes('text-sm').style('color: var(--ink-muted);')

                            # Progress section (shown during patching)
                            progress_container = ui.column().classes('w-full gap-2')
                            progress_container.visible = False

                            with progress_container:
                                patch_progressbar = ui.linear_progress(value=0.0, show_value=False).classes('w-full')
                                patch_status_label = ui.label("Preparing...").classes("text-sm text-white")

                            # Buttons
                            buttons_container = ui.row().classes('justify-end gap-2 q-mt-md w-full')
                            with buttons_container:
                                cancel_btn = ui.button('Cancel', on_click=dlg.close).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')
                                start_btn = ui.button('Start Build', icon='build').style('color: var(--neon-cyan) !important; background: var(--surface) !important; border-radius: 18px; padding: 4px 10px;')
                                close_btn = ui.button('Close', on_click=dlg.close).style('color: var(--neon-purple) !important; background: var(--surface) !important; border-radius: 18px; padding: 4px 10px;')
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
                                    await run.io_bound(table_service.apply_vpx_patches, progress_cb=patch_progress_cb)
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

                    import_btn = ui.button("Import Table", icon="upload").props("color=accent rounded")

                    import_btn.on_click(lambda: open_import_table_dialog(perform_scan))

        # Use cached data if available, otherwise start with empty
        initial_rows = _tables_cache() if _tables_cache() is not None else []
        initial_missing = _missing_cache() if _missing_cache() is not None else []

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
            return build_table_filter_options(_tables_cache() or [])

        def apply_filters():
            """Filter the cached tables based on current filter state."""
            extra_predicates = []
            if filter_state['has_pup_pack']:
                extra_predicates.append(lambda row: row.get('pup_pack_exists', False))
            return apply_table_filters(
                _tables_cache() or [],
                filter_state,
                search_fields=('name', 'filename'),
                extra_predicates=extra_predicates,
            )

        def update_table_display():
            """Update the table with filtered results."""
            filtered = apply_filters()
            table._props['rows'] = filtered
            table.update()
            # Update title with filtered count
            total = len(_tables_cache() or [])
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
        with ui.card().classes('w-full mb-4').style('border-radius: 8px; background: var(--surface); border: 1px solid var(--line);'):
            with ui.row().classes('w-full items-center gap-4 p-4 flex-wrap'):
                # Search input
                search_input = debounced_input(ui.input(placeholder='Search tables...')).props('outlined dense clearable').classes('flex-grow').style('min-width: 200px;')
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
                pup_pack_checkbox = ui.checkbox('PUP Pack', value=False).style('color: var(--ink);')
                pup_pack_checkbox.on_value_change(on_pup_pack_change)

                # Clear filters button
                ui.button(icon='clear_all', on_click=clear_filters).props('flat round').tooltip('Clear all filters')

        # Batch action bar for adding multiple tables to a collection at once
        batch_bar = ui.card().classes('w-full mb-2').style(
            'border-radius: var(--radius) !important; background: var(--surface) !important; border: 1px solid var(--line) !important;'
        )
        batch_bar.visible = False
        with batch_bar:
            with ui.row().classes('w-full items-center gap-4 p-3'):
                batch_label = ui.label('0 tables selected').classes('font-medium').style('color: var(--ink);')
                batch_collection_select = ui.select(
                    label='Add to Collection',
                    options=get_vpsid_collections(),
                    value=None
                ).props('dense').classes('w-48').style('color: var(--ink); border: 1px solid var(--line);')
                batch_add_btn = ui.button('Add to Collection', icon='playlist_add').style('background: var(--neon-purple) !important; color: var(--ink) !important;')

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
                            <span v-if="Number(props.row.rating || 0) > 0" style="font-size: 0.9em; white-space: nowrap;">
                                <span style="color: #facc15;">{{ '★'.repeat(Math.max(0, Math.min(5, Number(props.row.rating || 0)))) }}</span><span style="color: #64748b;">{{ '☆'.repeat(5 - Math.max(0, Math.min(5, Number(props.row.rating || 0)))) }}</span>
                            </span>
                            <q-badge
                                v-if="props.row.altlauncher"
                                color="orange-8"
                                text-color="white"
                                label="ALT-L"
                                style="font-size: 10px; padding: 2px 6px;"
                            />
                            <q-badge
                                v-if="props.row.alttitle"
                                color="cyan-8"
                                text-color="white"
                                label="ALT-T"
                                style="font-size: 10px; padding: 2px 6px;"
                            />
                            <q-badge
                                v-if="props.row.altvpsid"
                                color="indigo-8"
                                text-color="white"
                                label="ALT-VPS"
                                style="font-size: 10px; padding: 2px 6px;"
                            />
                            <a v-if="props.row.ipdb_id"
                               :href="'https://www.ipdb.org/machine.cgi?id=' + props.row.ipdb_id"
                               target="_blank"
                               @click.stop
                               style="text-decoration: none;">
                                <q-badge color="yellow-8" text-color="black" label="IPDB" style="font-size: 10px; padding: 2px 6px; cursor: pointer;" />
                            </a>
                            <a v-if="props.row.vpsid"
                               :href="'https://virtualpinballspreadsheet.github.io/?game=' + props.row.vpsid"
                               target="_blank"
                               @click.stop
                               style="text-decoration: none;">
                                <q-badge color="blue-8" text-color="white" label="VPS" style="font-size: 10px; padding: 2px 6px; cursor: pointer;" />
                            </a>
                            <a v-if="props.row.pinball_primer_tut"
                               :href="props.row.pinball_primer_tut"
                               target="_blank"
                               @click.stop
                               style="text-decoration: none;">
                                <q-badge color="green-8" text-color="white" label="PP" style="font-size: 10px; padding: 2px 6px; cursor: pointer;" />
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
            # Add top pagination controls (styled to match bottom)
            table.add_slot('top', '''
                <div class="row full-width items-center justify-end q-pa-sm"
                     style="background-color: var(--surface); color: var(--ink); border-bottom: 1px solid var(--line); border-radius: var(--radius);">
                    <q-btn flat round dense icon="first_page" :disable="props.isFirstPage" @click="props.firstPage" size="sm" style="color: var(--ink-muted);" />
                    <q-btn flat round dense icon="chevron_left" :disable="props.isFirstPage" @click="props.prevPage" size="sm" style="color: var(--ink-muted);" />
                    <span class="q-mx-sm" style="font-size: 0.85rem; color: #94a3b8;">
                        Page {{ props.pagination.page }} of {{ props.pagesNumber }}
                    </span>
                    <q-btn flat round dense icon="chevron_right" :disable="props.isLastPage" @click="props.nextPage" size="sm" style="color: var(--ink-muted);" />
                    <q-btn flat round dense icon="last_page" :disable="props.isLastPage" @click="props.lastPage" size="sm" style="color: var(--ink-muted);" />
                </div>
            ''')
            # Add bottom with Select All checkbox alongside pagination
            table.add_slot('bottom', '''
                <div class="row full-width items-center q-pa-sm"
                     style="background-color: var(--surface); color: var(--ink); border-top: 1px solid var(--line);">
                    <q-checkbox
                        :model-value="(() => {
                            const sel = $parent.selected || [];
                            const rows = $parent.rows || [];
                            const p = props.pagination;
                            const start = (p.page - 1) * p.rowsPerPage;
                            const pageRows = rows.slice(start, start + p.rowsPerPage);
                            if (!pageRows.length) return false;
                            const selKeys = new Set(sel.map(r => r.filename));
                            return pageRows.every(r => selKeys.has(r.filename));
                        })()"
                        @update:model-value="() => $parent.$emit('toggle_select_all')"
                        label="Select Page"
                        dark
                        dense
                        color="primary"
                        style="color: var(--ink);"
                    />
                    <q-space />
                    <span class="q-mr-sm" style="font-size: 0.85rem;">Rows per page:</span>
                    <q-select
                        :model-value="props.pagination.rowsPerPage"
                        :options="[25, 50, 100]"
                        @update:model-value="val => $parent.$emit('update:pagination', Object.assign({}, props.pagination, {rowsPerPage: val, page: 1}))"
                        dense
                        borderless
                        dark
                        emit-value
                        map-options
                        options-dense
                        style="min-width: 50px; color: #e2e8f0;"
                    />
                    <q-space />
                    <q-btn flat round dense icon="first_page" :disable="props.isFirstPage" @click="props.firstPage" size="sm" style="color: var(--ink-muted);" />
                    <q-btn flat round dense icon="chevron_left" :disable="props.isFirstPage" @click="props.prevPage" size="sm" style="color: var(--ink-muted);" />
                    <span class="q-mx-sm" style="font-size: 0.85rem;">
                        Page {{ props.pagination.page }} of {{ props.pagesNumber }}
                    </span>
                    <q-btn flat round dense icon="chevron_right" :disable="props.isLastPage" @click="props.nextPage" size="sm" style="color: var(--ink-muted);" />
                    <q-btn flat round dense icon="last_page" :disable="props.isLastPage" @click="props.lastPage" size="sm" style="color: var(--ink-muted);" />
                </div>
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

        # Handle Select All toggle from the bottom slot checkbox (current page only)
        def on_toggle_select_all(e):
            rows = table._props.get('rows', [])
            pagination = table._props.get('pagination', {})
            page = pagination.get('page', 1)
            per_page = pagination.get('rowsPerPage', 25)
            start = (page - 1) * per_page
            end = start + per_page
            page_rows = rows[start:end]

            # If all current page rows are already selected, deselect them; otherwise select them
            selected_keys = {r.get('filename') for r in table.selected}
            page_keys = {r.get('filename') for r in page_rows}
            all_page_selected = page_keys.issubset(selected_keys) and len(page_keys) > 0

            if all_page_selected:
                # Deselect current page rows (keep others)
                table.selected = [r for r in table.selected if r.get('filename') not in page_keys]
            else:
                # Add current page rows to selection (avoid duplicates)
                for r in page_rows:
                    if r.get('filename') not in selected_keys:
                        table.selected.append(r)
            table.update()
            # Update batch bar
            if table.selected:
                batch_bar.visible = True
                count = len(table.selected)
                batch_label.set_text(f'{count} table{"s" if count != 1 else ""} selected')
            else:
                batch_bar.visible = False

        table.on('toggle_select_all', on_toggle_select_all)

        # Update missing button if we have cached data
        cached_missing = _missing_cache()
        if cached_missing is not None:
            missing_button.text = f"Unmatched Tables ({len(cached_missing)})"
            # Update button color: green if 0, red if > 0
            btn_color = "positive" if len(cached_missing) == 0 else "negative"
            missing_button._props['color'] = btn_color
            missing_button.on('click', lambda: open_missing_tables_dialog(
                cached_missing,
                on_close=lambda: asyncio.create_task(perform_scan(silent=True))
            ))

        # Function to refresh the table display
        async def refresh_table_on_startup():
            if _tables_cache() is not None:
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
