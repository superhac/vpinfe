import os
import logging
import asyncio
import shutil
from nicegui import ui, events, run, app, context
from pathlib import Path
import json
from typing import List, Dict, Optional
from platformdirs import user_config_dir

# Resolve project root and important paths explicitly
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
VPINFE_INI_PATH = CONFIG_DIR / 'vpinfe.ini'

from common.iniconfig import IniConfig
from common.metaconfig import MetaConfig
_INI_CFG = IniConfig(str(VPINFE_INI_PATH))

logger = logging.getLogger("media")

# Cache for scanned media data (persists across page visits)
_media_cache: Optional[List[Dict]] = None
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
]


def get_tables_path() -> str:
    try:
        tableroot = _INI_CFG.config.get('Settings', 'tablerootdir', fallback='').strip()
        if tableroot:
            return os.path.expanduser(tableroot)
    except Exception as e:
        logger.debug(f'Could not read tablerootdir from vpinfe.ini: {e}')
    return os.path.expanduser('~/tables')


def scan_media_tables(silent: bool = False):
    """Scan table directories and collect media file info."""
    tables_path = get_tables_path()
    rows = []
    if not os.path.exists(tables_path):
        logger.warning(f"Tables path does not exist: {tables_path}. Skipping scan.")
        if not silent:
            ui.notify("Tables path does not exist. Please verify your vpinfe.ini settings", type="negative")
        return []

    for root, _, files in os.walk(tables_path):
        current_dir = os.path.basename(root)
        info_file = f"{current_dir}.info"

        if info_file in files:
            has_vpx = any(f.lower().endswith('.vpx') for f in files)
            if not has_vpx:
                continue

            meta_path = os.path.join(root, info_file)
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)

                info = raw.get("Info", {})
                vpx = raw.get("VPXFile", {})

                name = (info.get("Title") or current_dir).strip()
                manufacturer = info.get("Manufacturer", "")
                year = info.get("Year", "")
                ttype = info.get("Type", "")
                themes = info.get("Themes", [])

                # Build media availability dict
                media_info = {}
                medias_dir = os.path.join(root, "medias")
                for media_key, _, media_filename in MEDIA_TYPES:
                    # Check medias/ subfolder first, then fall back to root folder
                    img_path_medias = os.path.join(medias_dir, media_filename)
                    img_path_root = os.path.join(root, media_filename)
                    if os.path.exists(img_path_medias):
                        # URL path relative to the served tables directory
                        media_info[media_key] = f"/media_tables/{current_dir}/medias/{media_filename}"
                    elif os.path.exists(img_path_root):
                        media_info[media_key] = f"/media_tables/{current_dir}/{media_filename}"
                    else:
                        media_info[media_key] = None

                rows.append({
                    'name': name,
                    'table_dir': current_dir,
                    'table_path': root,
                    'manufacturer': manufacturer,
                    'year': year,
                    'type': ttype,
                    'themes': themes,
                    'media': media_info,
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
                })
            except Exception as e:
                logger.error(f"Error reading {meta_path}: {e}")

    return rows


def render_panel():
    global _media_route_registered

    # Register media files route once
    if not _media_route_registered:
        tables_path = get_tables_path()
        if os.path.exists(tables_path):
            app.add_media_files('/media_tables', tables_path)
            _media_route_registered = True

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
        ]

        # --- Filter state and functions ---
        filter_state = {
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
        }

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

        def update_table_display():
            filtered = apply_filters()
            media_table._props['rows'] = filtered
            media_table.update()
            total = len(_media_cache or [])
            shown = len(filtered)
            if shown == total:
                count_label.set_text(f"Tables ({total})")
            else:
                count_label.set_text(f"Tables ({shown} of {total})")

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

        def clear_filters():
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
            media_table._props['pagination']['page'] = 1
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
            print("Scanning media...")
            # Capture client context before any io_bound calls (may not exist if called from timer)
            try:
                client = context.client
            except RuntimeError:
                client = None
            try:
                scan_btn.disable()
            except Exception:
                pass
            try:
                media_rows = await run.io_bound(scan_media_tables, silent)
                try:
                    media_rows.sort(key=lambda r: (r.get('name') or '').lower())
                except Exception:
                    pass

                _media_cache = media_rows

                try:
                    refresh_filter_options()
                    update_table_display()
                except NameError:
                    media_table._props['rows'] = media_rows
                    media_table.update()

                await asyncio.sleep(0.05)
                try:
                    ui.run_javascript('window.dispatchEvent(new Event("resize"));')
                except RuntimeError:
                    pass

                if not silent and client:
                    with client:
                        ui.notify('Media scan complete!', type='positive')
            except Exception as e:
                logger.exception("Failed to scan media")
                if not silent and client:
                    with client:
                        ui.notify(f"Error during scan: {e}", type='negative')
            finally:
                try:
                    scan_btn.enable()
                except Exception:
                    pass

        # --- Media replacement logic ---
        # Lookup: media_key -> standard filename
        MEDIA_KEY_TO_FILENAME = {key: fname for key, _, fname in MEDIA_TYPES}

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

        def update_cache_entry(table_dir: str, media_key: str, url_path: str):
            """Update the in-memory cache for the replaced media."""
            if _media_cache is None:
                return
            for row in _media_cache:
                if row['table_dir'] == table_dir:
                    row['media'][media_key] = url_path
                    row[f'has_{media_key}'] = url_path is not None
                    break

        def open_replace_dialog(table_dir: str, table_path: str, table_name: str, media_key: str, media_label: str):
            """Open a dialog to replace a media image for a table."""
            target_filename = MEDIA_KEY_TO_FILENAME[media_key]
            current_url = None
            # Find current image URL from cache
            if _media_cache:
                for row in _media_cache:
                    if row['table_dir'] == table_dir:
                        current_url = row['media'].get(media_key)
                        break

            with ui.dialog() as dlg, ui.card().style('min-width: 500px; background: #1e293b; border: 1px solid #334155;'):
                ui.label(f'Replace {media_label} Image').classes('text-xl font-bold text-white mb-2')
                ui.label(f'Table: {table_name}').classes('text-slate-400 mb-1')
                ui.label(f'Target: {target_filename}').classes('text-slate-500 text-sm mb-4')

                # Show current image if exists
                if current_url:
                    ui.label('Current:').classes('text-slate-400 text-sm')
                    ui.image(current_url).style('max-width: 240px; max-height: 240px; border-radius: 6px; border: 1px solid #334155;').classes('mb-4')
                else:
                    ui.label('No current image').classes('text-slate-500 italic mb-4')

                # File upload
                ui.label('Select new image:').classes('text-slate-400 text-sm mb-1')
                upload_state = {'path': None}

                async def handle_upload(e: events.UploadEventArguments):
                    # Save to a temp location first
                    tmp_dir = os.path.join(table_path, '.tmp_upload')
                    os.makedirs(tmp_dir, exist_ok=True)
                    tmp_path = os.path.join(tmp_dir, e.name)
                    with open(tmp_path, 'wb') as f:
                        f.write(e.content.read())
                    upload_state['path'] = tmp_path
                    confirm_btn.enable()
                    ui.notify(f'File ready: {e.name}', type='info')

                ui.upload(
                    on_upload=handle_upload,
                    auto_upload=True,
                    max_files=1,
                ).props('accept="image/*" flat bordered').classes('w-full mb-4').style('background: #0f172a; border: 1px dashed #475569;')

                with ui.row().classes('w-full justify-end gap-3 mt-2'):
                    ui.button('Cancel', on_click=dlg.close).props('flat').classes('text-slate-400')

                    async def do_replace():
                        if not upload_state['path']:
                            return
                        try:
                            src = upload_state['path']
                            await run.io_bound(replace_media_file, table_path, table_dir, media_key, src)

                            # Build the URL for the new image (now in medias/ subfolder)
                            new_url = f"/media_tables/{table_dir}/medias/{target_filename}"
                            update_cache_entry(table_dir, media_key, new_url)
                            update_table_display()

                            # Cleanup temp
                            tmp_dir = os.path.join(table_path, '.tmp_upload')
                            if os.path.exists(tmp_dir):
                                shutil.rmtree(tmp_dir, ignore_errors=True)

                            ui.notify(f'{media_label} image replaced!', type='positive')
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
                search_input = ui.input(placeholder='Search tables...').props('outlined dense clearable').classes('flex-grow').style('min-width: 200px;')
                search_input.on_value_change(on_search_change)

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
                            media_table._props['pagination']['page'] = 1
                            update_table_display()
                        return handler
                    cb = ui.checkbox(media_label, value=False, on_change=make_handler(media_key)).classes('text-white')
                    missing_checkboxes[media_key] = cb

        # Table count label
        total = len(initial_rows)
        count_label = ui.label(f"Tables ({total})").classes('text-lg font-semibold text-slate-300 py-1 text-center w-full')

        # Table with image thumbnails
        table_container = ui.column().classes("w-full media-table").style("flex: 1; overflow: hidden; display: flex;")

        with table_container:
            media_table = (
                ui.table(columns=columns, rows=initial_rows, row_key='table_dir', pagination={'rowsPerPage': 25})
                  .props('rows-per-page-options="[25,50,100]" sort-by="name" sort-order="asc"')
                  .classes("w-full")
                  .style("flex: 1; overflow: auto;")
            )

            # Lookup for media_key -> label
            MEDIA_KEY_TO_LABEL = {key: label for key, label, _ in MEDIA_TYPES}

            # Custom slot for each media type column to show thumbnail or missing indicator
            for media_key, media_label, _ in MEDIA_TYPES:
                col_name = media_key
                if media_key == 'table':
                    col_name = 'table_img'
                emit_expr = "$parent.$emit('media_click', [props.row.table_dir, props.row.table_path, props.row.name, '" + media_key + "'])"
                media_table.add_slot(f'body-cell-{col_name}', '''
                    <q-td :props="props">
                        <div v-if="props.row.media.''' + media_key + '''" class="media-thumb-wrapper"
                             @click.stop="''' + emit_expr + '''"
                             style="cursor: pointer;">
                            <img :src="props.row.media.''' + media_key + '''"
                                 class="media-thumb"
                                 loading="lazy" />
                            <q-tooltip anchor="top middle" self="bottom middle" :offset="[0, 8]"
                                       class="bg-dark" style="padding: 4px;">
                                <img :src="props.row.media.''' + media_key + '''"
                                     style="max-width: 240px; max-height: 240px; border-radius: 6px; border: 2px solid #3b82f6;" />
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

        # Startup scan
        async def refresh_on_startup():
            if _media_cache is not None:
                refresh_filter_options()
                update_table_display()
            else:
                await perform_scan(silent=True)
            try:
                ui.run_javascript('window.dispatchEvent(new Event("resize"));')
            except RuntimeError:
                pass

        async def startup_refresh():
            await asyncio.sleep(0.2)
            await refresh_on_startup()

        ui.timer(0.1, lambda: asyncio.create_task(startup_refresh()), once=True)
