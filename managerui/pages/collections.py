import logging
import asyncio
from nicegui import ui, events, run
from pathlib import Path
from typing import List, Dict, Optional
from platformdirs import user_config_dir
from common.vpxcollections import VPXCollections

logger = logging.getLogger("collections")

CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
COLLECTIONS_PATH = CONFIG_DIR / "collections.ini"

# Import tables module to access cache (import module, not variable, to get live values)
from . import tables as tables_module


def get_collections_manager() -> VPXCollections:
    """Get a fresh VPXCollections instance."""
    return VPXCollections(str(COLLECTIONS_PATH))


def get_table_name_map() -> Dict[str, str]:
    """Build a map of VPS ID -> table name from the tables cache."""
    # Access the cache through the module to get the current value
    tables = tables_module._tables_cache

    # If cache is empty, scan tables to populate it
    if not tables:
        tables = tables_module.scan_tables(silent=True)

    return {t.get('id'): t.get('name', t.get('id')) for t in tables if t.get('id')}


def vpsid_to_name(vpsid: str, table_map: Dict[str, str] = None) -> str:
    """Convert a VPS ID to table name, or return the ID if not found."""
    if table_map is None:
        table_map = get_table_name_map()
    return table_map.get(vpsid, vpsid)


def get_filter_options() -> Dict[str, List[str]]:
    """Get filter options (letters, themes, types, manufacturers, years) from the tables cache."""
    # Use the tables cache from the tables module (same data used in the Tables page)
    tables = tables_module._tables_cache

    # If cache is empty, scan tables to populate it
    if not tables:
        tables = tables_module.scan_tables(silent=True)

    if not tables:
        # Fallback to basic options if no tables
        return {
            'letters': ['All'],
            'themes': ['All'],
            'types': ['All'],
            'manufacturers': ['All'],
            'years': ['All'],
            'sort_options': ['Alpha', 'Newest'],
        }

    # Extract unique values from the cached table data
    letters = set()
    themes = set()
    types = set()
    manufacturers = set()
    years = set()

    for t in tables:
        # Get starting letter from name
        name = t.get('name', '')
        if name:
            first_char = name[0].upper()
            if first_char.isalnum():
                letters.add(first_char)

        # Get type (EM, SS, PM, etc.)
        table_type = t.get('type', '')
        if table_type:
            types.add(table_type)

        # Get manufacturer
        mfr = t.get('manufacturer', '')
        if mfr:
            manufacturers.add(mfr)

        # Get year
        year = t.get('year', '')
        if year:
            years.add(str(year))

        # Get themes (stored as list in meta, but might be string in cache)
        # Note: themes are stored in Info.Themes in the .info JSON
        table_themes = t.get('themes', [])
        if isinstance(table_themes, list):
            themes.update(table_themes)
        elif table_themes:
            themes.add(table_themes)

    return {
        'letters': ['All'] + sorted(letters),
        'themes': ['All'] + sorted(themes),
        'types': ['All'] + sorted(types),
        'manufacturers': ['All'] + sorted(manufacturers),
        'years': ['All'] + sorted(years),
        'sort_options': ['Alpha', 'Newest'],
    }


def render_panel(tab=None):
    # Add custom styles
    ui.add_head_html('''
    <style>
        .collection-card {
            background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%) !important;
            border: 1px solid #334155 !important;
            border-radius: 12px !important;
            transition: all 0.2s ease !important;
        }
        .collection-card:hover {
            border-color: #3b82f6 !important;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15) !important;
        }
        .collection-item {
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 12px 16px;
            transition: all 0.2s ease;
        }
        .collection-item:hover {
            background: rgba(51, 65, 85, 0.6);
            border-color: #475569;
        }
        .filter-badge {
            background: linear-gradient(135deg, #7c3aed 0%, #a855f7 100%);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
        }
        .vpsid-badge {
            background: linear-gradient(135deg, #0891b2 0%, #06b6d4 100%);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
        }
    </style>
    ''')

    with ui.column().classes('w-full'):
        # Header card
        with ui.card().classes('w-full mb-4').style(
            'background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); border-radius: 12px;'
        ):
            with ui.row().classes('w-full justify-between items-center p-4 gap-4'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('collections_bookmark', size='32px').classes('text-white')
                    ui.label('Collections Manager').classes('text-2xl font-bold text-white')
                with ui.row().classes('gap-3'):
                    add_vpsid_btn = ui.button("New Table Collection", icon="add").props("color=primary rounded")
                    add_filter_btn = ui.button("New Filter Collection", icon="filter_list").props("color=secondary rounded")

        # Collections list container
        collections_container = ui.column().classes('w-full gap-3')

        def refresh_collections():
            """Refresh the collections list display."""
            collections_container.clear()
            manager = get_collections_manager()
            collection_names = manager.get_collections_name()
            table_map = get_table_name_map()

            if not collection_names:
                with collections_container:
                    with ui.card().classes('collection-card w-full p-8'):
                        with ui.column().classes('w-full items-center gap-4'):
                            ui.icon('folder_off', size='48px').classes('text-gray-500')
                            ui.label('No collections yet').classes('text-lg text-gray-400')
                            ui.label('Create a collection to organize your tables').classes('text-sm text-gray-500')
                return

            with collections_container:
                for name in collection_names:
                    is_filter = manager.is_filter_based(name)

                    with ui.card().classes('collection-card w-full p-4'):
                        with ui.row().classes('w-full justify-between items-center'):
                            with ui.row().classes('items-center gap-3'):
                                ui.icon('filter_list' if is_filter else 'list', size='24px').classes(
                                    'text-purple-400' if is_filter else 'text-cyan-400'
                                )
                                ui.label(name).classes('text-lg font-medium text-white')
                                if is_filter:
                                    ui.label('Filter').classes('filter-badge text-white')
                                else:
                                    vpsids = manager.get_vpsids(name)
                                    ui.label(f'{len(vpsids)} Tables').classes('vpsid-badge text-white')

                            with ui.row().classes('gap-2'):
                                ui.button(icon='drive_file_rename_outline', on_click=lambda n=name: open_rename_dialog(n)).props('flat round color=white').tooltip('Rename')
                                ui.button(icon='edit', on_click=lambda n=name, f=is_filter: open_edit_dialog(n, f)).props('flat round color=primary').tooltip('Edit')
                                ui.button(icon='delete', on_click=lambda n=name: confirm_delete(n)).props('flat round color=negative').tooltip('Delete')

                        # Show details based on type
                        if is_filter:
                            filters = manager.get_filters(name)
                            with ui.row().classes('mt-3 gap-2 flex-wrap'):
                                for key, value in filters.items():
                                    if value and value != 'All':
                                        for v in value.split(','):
                                            ui.chip(f'{key}: {v.strip()}', icon='label').props('outline color=purple dense')
                        else:
                            vpsids = manager.get_vpsids(name)
                            if vpsids:
                                # Create expandable chips section with isolated state
                                create_expandable_chips(vpsids, table_map)

        def create_expandable_chips(vps_ids: list, tbl_map: dict):
            """Factory function to create expandable chips with isolated state."""
            chips_container = ui.column().classes('mt-3 w-full gap-2')
            state = {'expanded': False}

            def render():
                chips_container.clear()
                with chips_container:
                    with ui.row().classes('gap-2 flex-wrap'):
                        display_ids = vps_ids if state['expanded'] else vps_ids[:5]
                        for vid in display_ids:
                            tbl_name = vpsid_to_name(vid, tbl_map)
                            ui.chip(tbl_name, icon='sports_esports').props('outline color=cyan dense')

                        if len(vps_ids) > 5:
                            if state['expanded']:
                                collapse_chip = ui.chip('Show less', icon='expand_less').props('outline color=grey dense clickable')
                                collapse_chip.on('click', toggle)
                            else:
                                expand_chip = ui.chip(f'+{len(vps_ids) - 5} more', icon='expand_more').props('outline color=grey dense clickable')
                                expand_chip.on('click', toggle)

            def toggle():
                state['expanded'] = not state['expanded']
                render()

            # Initial render
            render()

        def confirm_delete(name: str):
            """Show delete confirmation dialog."""
            dlg = ui.dialog()
            with dlg, ui.card().classes('p-4').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                ui.label(f'Delete "{name}"?').classes('text-lg font-bold text-white')
                ui.label('This action cannot be undone.').classes('text-sm text-gray-400 mt-2')
                with ui.row().classes('justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dlg.close).props('flat')
                    def do_delete():
                        try:
                            manager = get_collections_manager()
                            manager.delete_collection(name)
                            manager.save()
                            # Sync the tables cache with updated collection memberships
                            tables_module.sync_collections_to_cache()
                            ui.notify(f'Collection "{name}" deleted', type='positive')
                            dlg.close()
                            refresh_collections()
                        except Exception as e:
                            ui.notify(f'Error: {e}', type='negative')
                    ui.button('Delete', on_click=do_delete).props('color=negative')
            dlg.open()

        def open_rename_dialog(name: str):
            """Show dialog to rename a collection."""
            dlg = ui.dialog()
            with dlg, ui.card().classes('p-4 w-[400px]').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                ui.label(f'Rename Collection').classes('text-lg font-bold text-white')
                ui.label(f'Current name: {name}').classes('text-sm text-gray-400 mt-2')

                new_name_input = ui.input('New Name', value=name).classes('w-full mt-4')

                with ui.row().classes('justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dlg.close).props('flat')

                    def do_rename():
                        new_name = new_name_input.value.strip()
                        if not new_name:
                            ui.notify('Please enter a new name', type='warning')
                            return
                        if new_name == name:
                            dlg.close()
                            return
                        try:
                            manager = get_collections_manager()
                            manager.rename_collection(name, new_name)
                            manager.save()
                            # Sync the tables cache with updated collection memberships
                            tables_module.sync_collections_to_cache()
                            ui.notify(f'Renamed to "{new_name}"', type='positive')
                            dlg.close()
                            refresh_collections()
                        except Exception as e:
                            ui.notify(f'Error: {e}', type='negative')

                    ui.button('Rename', icon='check', on_click=do_rename).props('color=primary')
            dlg.open()

        def open_new_vpsid_dialog():
            """Dialog to create a new VPS ID-based collection."""
            dlg = ui.dialog().props('persistent max-width=800px')
            with dlg, ui.card().classes('w-[750px]').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                ui.label('New Table Collection').classes('text-xl font-bold text-white')
                ui.separator()

                name_input = ui.input('Collection Name', placeholder='My Favorites').classes('w-full mt-4')

                ui.label('Add tables to this collection:').classes('text-sm text-gray-400 mt-4')

                # Selected tables list
                selected_tables = {'items': []}  # {id, name}
                selected_container = ui.column().classes('w-full gap-1 mt-2').style('max-height: 150px; overflow-y: auto;')

                def update_selected_display():
                    selected_container.clear()
                    with selected_container:
                        if not selected_tables['items']:
                            ui.label('No tables selected').classes('text-gray-500 text-sm')
                        else:
                            for item in selected_tables['items']:
                                with ui.row().classes('w-full items-center justify-between p-2 bg-gray-800 rounded'):
                                    ui.label(item['name']).classes('text-white text-sm')
                                    ui.button(icon='close', on_click=lambda i=item: remove_table(i)).props('flat round dense size=sm')

                def remove_table(item):
                    selected_tables['items'] = [t for t in selected_tables['items'] if t['id'] != item['id']]
                    update_selected_display()

                update_selected_display()

                # Table search and selection
                ui.label('Search installed tables:').classes('text-sm text-gray-400 mt-4')
                search_input = ui.input('Search...', placeholder='Type to search tables').classes('w-full')
                search_results = ui.column().classes('w-full gap-1 mt-2').style('max-height: 200px; overflow-y: auto;')

                async def do_search(e: events.ValueChangeEventArguments):
                    term = (e.value or '').strip().lower()
                    search_results.clear()

                    # Get tables from cache or scan
                    tables = tables_module._tables_cache
                    if tables is None:
                        tables = await run.io_bound(tables_module.scan_tables, True)

                    if not term:
                        return

                    with search_results:
                        matches = [t for t in tables if term in (t.get('name') or '').lower()][:20]
                        if not matches:
                            ui.label('No tables found').classes('text-gray-500 text-sm')
                        else:
                            for t in matches:
                                vps_id = t.get('id', '')
                                name = t.get('name', 'Unknown')
                                if not vps_id:
                                    continue
                                # Check if already selected
                                already_selected = any(s['id'] == vps_id for s in selected_tables['items'])
                                with ui.row().classes('w-full items-center justify-between p-2 bg-gray-800 rounded hover:bg-gray-700'):
                                    ui.label(f'{name}').classes('text-white text-sm flex-grow')
                                    if already_selected:
                                        ui.icon('check', color='green')
                                    else:
                                        def add_table(vid=vps_id, n=name):
                                            if not any(s['id'] == vid for s in selected_tables['items']):
                                                selected_tables['items'].append({'id': vid, 'name': n})
                                                update_selected_display()
                                                ui.notify(f'Added {n}', type='positive')
                                        ui.button(icon='add', on_click=add_table).props('flat round dense size=sm color=primary')

                search_input.on_value_change(do_search)

                with ui.row().classes('justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dlg.close).props('flat')

                    def save_collection():
                        name = name_input.value.strip()
                        if not name:
                            ui.notify('Please enter a collection name', type='warning')
                            return
                        try:
                            manager = get_collections_manager()
                            vpsids = [t['id'] for t in selected_tables['items']]
                            manager.add_collection(name, vpsids)
                            manager.save()
                            # Sync the tables cache with updated collection memberships
                            tables_module.sync_collections_to_cache()
                            ui.notify(f'Collection "{name}" created', type='positive')
                            dlg.close()
                            refresh_collections()
                        except ValueError as e:
                            ui.notify(str(e), type='negative')

                    ui.button('Create', icon='save', on_click=save_collection).props('color=primary')

            dlg.open()

        def open_new_filter_dialog():
            """Dialog to create a new filter-based collection."""
            # Get filter options from tables
            filter_opts = get_filter_options()

            dlg = ui.dialog().props('persistent max-width=600px')
            with dlg, ui.card().classes('w-[550px]').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                ui.label('New Filter Collection').classes('text-xl font-bold text-white')
                ui.separator()

                name_input = ui.input('Collection Name', placeholder='80s Tables').classes('w-full mt-4')

                ui.label('Filter Criteria:').classes('text-sm text-gray-400 mt-4 mb-2')

                # Filter dropdowns populated from table data (multi-select supported)
                # Remove 'All' from options for multi-select; empty selection means 'All'
                letter_input = ui.select(label='Starting Letter', options=filter_opts['letters'][1:], value=[], multiple=True).classes('w-full')
                theme_input = ui.select(label='Theme', options=filter_opts['themes'][1:], value=[], multiple=True).classes('w-full')
                type_input = ui.select(label='Table Type', options=filter_opts['types'][1:], value=[], multiple=True).classes('w-full')
                manufacturer_input = ui.select(label='Manufacturer', options=filter_opts['manufacturers'][1:], value=[], multiple=True).classes('w-full')
                year_input = ui.select(label='Year', options=filter_opts['years'][1:], value=[], multiple=True).classes('w-full')
                sort_input = ui.select(label='Sort By', options=filter_opts['sort_options'], value='Alpha').classes('w-full')

                def _join_or_all(values):
                    """Join selected values with comma, or return 'All' if none selected."""
                    if not values:
                        return 'All'
                    return ','.join(str(v) for v in values)

                with ui.row().classes('justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dlg.close).props('flat')

                    def save_filter():
                        name = name_input.value.strip()
                        if not name:
                            ui.notify('Please enter a collection name', type='warning')
                            return
                        try:
                            manager = get_collections_manager()
                            manager.add_filter_collection(
                                name,
                                letter=_join_or_all(letter_input.value),
                                theme=_join_or_all(theme_input.value),
                                table_type=_join_or_all(type_input.value),
                                manufacturer=_join_or_all(manufacturer_input.value),
                                year=_join_or_all(year_input.value),
                                sort_by=sort_input.value or 'Alpha',
                            )
                            manager.save()
                            ui.notify(f'Filter collection "{name}" created', type='positive')
                            dlg.close()
                            refresh_collections()
                        except ValueError as e:
                            ui.notify(str(e), type='negative')

                    ui.button('Create', icon='save', on_click=save_filter).props('color=primary')

            dlg.open()

        def open_edit_dialog(name: str, is_filter: bool):
            """Open edit dialog for existing collection."""
            if is_filter:
                open_edit_filter_dialog(name)
            else:
                open_edit_vpsid_dialog(name)

        def open_edit_filter_dialog(name: str):
            """Dialog to edit a filter-based collection."""
            manager = get_collections_manager()
            filters = manager.get_filters(name)

            # Get filter options from tables
            filter_opts = get_filter_options()

            def _parse_csv_to_list(value):
                """Parse a comma-separated filter value into a list, or empty list for 'All'."""
                if not value or value == 'All':
                    return []
                return [v.strip() for v in value.split(',') if v.strip()]

            def _ensure_values_in_options(options, values):
                """Ensure all saved values exist in the options list."""
                result = list(options)
                for v in values:
                    if v not in result:
                        result.append(v)
                return sorted(result)

            # Parse saved values and build option lists (without 'All')
            saved_letters = _parse_csv_to_list(filters.get('letter', 'All'))
            saved_themes = _parse_csv_to_list(filters.get('theme', 'All'))
            saved_types = _parse_csv_to_list(filters.get('table_type', 'All'))
            saved_manufacturers = _parse_csv_to_list(filters.get('manufacturer', 'All'))
            saved_years = _parse_csv_to_list(filters.get('year', 'All'))

            letter_opts = _ensure_values_in_options(filter_opts['letters'][1:], saved_letters)
            theme_opts = _ensure_values_in_options(filter_opts['themes'][1:], saved_themes)
            type_opts = _ensure_values_in_options(filter_opts['types'][1:], saved_types)
            manufacturer_opts = _ensure_values_in_options(filter_opts['manufacturers'][1:], saved_manufacturers)
            year_opts = _ensure_values_in_options(filter_opts['years'][1:], saved_years)

            dlg = ui.dialog().props('persistent max-width=600px')
            with dlg, ui.card().classes('w-[550px]').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                ui.label(f'Edit Filter: {name}').classes('text-xl font-bold text-white')
                ui.separator()

                ui.label('Filter Criteria:').classes('text-sm text-gray-400 mt-4 mb-2')

                # Multi-select filter dropdowns
                letter_input = ui.select(label='Starting Letter', options=letter_opts, value=saved_letters, multiple=True).classes('w-full')
                theme_input = ui.select(label='Theme', options=theme_opts, value=saved_themes, multiple=True).classes('w-full')
                type_input = ui.select(label='Table Type', options=type_opts, value=saved_types, multiple=True).classes('w-full')
                manufacturer_input = ui.select(label='Manufacturer', options=manufacturer_opts, value=saved_manufacturers, multiple=True).classes('w-full')
                year_input = ui.select(label='Year', options=year_opts, value=saved_years, multiple=True).classes('w-full')
                sort_input = ui.select(label='Sort By', options=filter_opts['sort_options'], value=filters.get('sort_by', 'Alpha')).classes('w-full')

                def _join_or_all(values):
                    if not values:
                        return 'All'
                    return ','.join(str(v) for v in values)

                with ui.row().classes('justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dlg.close).props('flat')

                    def save_changes():
                        try:
                            m = get_collections_manager()
                            m.config[name]['letter'] = _join_or_all(letter_input.value)
                            m.config[name]['theme'] = _join_or_all(theme_input.value)
                            m.config[name]['table_type'] = _join_or_all(type_input.value)
                            m.config[name]['manufacturer'] = _join_or_all(manufacturer_input.value)
                            m.config[name]['year'] = _join_or_all(year_input.value)
                            m.config[name]['sort_by'] = sort_input.value or 'Alpha'
                            m.save()
                            ui.notify(f'Collection "{name}" updated', type='positive')
                            dlg.close()
                            refresh_collections()
                        except Exception as e:
                            ui.notify(f'Error: {e}', type='negative')

                    ui.button('Save', icon='save', on_click=save_changes).props('color=primary')

            dlg.open()

        def open_edit_vpsid_dialog(name: str):
            """Dialog to edit a VPS ID-based collection."""
            manager = get_collections_manager()
            current_vpsids = manager.get_vpsids(name)

            dlg = ui.dialog().props('persistent max-width=800px')
            with dlg, ui.card().classes('w-[750px]').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                ui.label(f'Edit Collection: {name}').classes('text-xl font-bold text-white')
                ui.separator()

                # Track current tables in collection
                selected_tables = {'items': []}

                # Try to resolve VPS IDs to names from cache
                table_map = get_table_name_map()

                for vid in current_vpsids:
                    selected_tables['items'].append({
                        'id': vid,
                        'name': table_map.get(vid, vid)
                    })

                ui.label('Tables in this collection:').classes('text-sm text-gray-400 mt-4')
                selected_container = ui.column().classes('w-full gap-1 mt-2').style('max-height: 200px; overflow-y: auto;')

                def update_selected_display():
                    selected_container.clear()
                    with selected_container:
                        if not selected_tables['items']:
                            ui.label('No tables in collection').classes('text-gray-500 text-sm')
                        else:
                            for item in selected_tables['items']:
                                with ui.row().classes('w-full items-center justify-between p-2 bg-gray-800 rounded'):
                                    ui.label(item['name']).classes('text-white text-sm')
                                    ui.button(icon='close', on_click=lambda i=item: remove_table(i)).props('flat round dense size=sm color=negative')

                def remove_table(item):
                    selected_tables['items'] = [t for t in selected_tables['items'] if t['id'] != item['id']]
                    update_selected_display()

                update_selected_display()

                # Table search and add
                ui.label('Add more tables:').classes('text-sm text-gray-400 mt-4')
                search_input = ui.input('Search...', placeholder='Type to search tables').classes('w-full')
                search_results = ui.column().classes('w-full gap-1 mt-2').style('max-height: 150px; overflow-y: auto;')

                async def do_search(e: events.ValueChangeEventArguments):
                    term = (e.value or '').strip().lower()
                    search_results.clear()

                    tables = tables_module._tables_cache
                    if tables is None:
                        tables = await run.io_bound(tables_module.scan_tables, True)

                    if not term:
                        return

                    with search_results:
                        matches = [t for t in tables if term in (t.get('name') or '').lower()][:20]
                        if not matches:
                            ui.label('No tables found').classes('text-gray-500 text-sm')
                        else:
                            for t in matches:
                                vps_id = t.get('id', '')
                                tname = t.get('name', 'Unknown')
                                if not vps_id:
                                    continue
                                already_selected = any(s['id'] == vps_id for s in selected_tables['items'])
                                with ui.row().classes('w-full items-center justify-between p-2 bg-gray-800 rounded hover:bg-gray-700'):
                                    ui.label(f'{tname}').classes('text-white text-sm flex-grow')
                                    if already_selected:
                                        ui.icon('check', color='green')
                                    else:
                                        def add_table(vid=vps_id, n=tname):
                                            if not any(s['id'] == vid for s in selected_tables['items']):
                                                selected_tables['items'].append({'id': vid, 'name': n})
                                                update_selected_display()
                                                ui.notify(f'Added {n}', type='positive')
                                        ui.button(icon='add', on_click=add_table).props('flat round dense size=sm color=primary')

                search_input.on_value_change(do_search)

                with ui.row().classes('justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dlg.close).props('flat')

                    def save_changes():
                        try:
                            m = get_collections_manager()
                            vpsids = [t['id'] for t in selected_tables['items']]
                            m.config[name]['vpsids'] = ','.join(vpsids)
                            m.save()
                            # Sync the tables cache with updated collection memberships
                            tables_module.sync_collections_to_cache()
                            ui.notify(f'Collection "{name}" updated', type='positive')
                            dlg.close()
                            refresh_collections()
                        except Exception as e:
                            ui.notify(f'Error: {e}', type='negative')

                    ui.button('Save', icon='save', on_click=save_changes).props('color=primary')

            dlg.open()

        # Wire up the add buttons
        add_vpsid_btn.on_click(open_new_vpsid_dialog)
        add_filter_btn.on_click(open_new_filter_dialog)

        # Initial load
        refresh_collections()
