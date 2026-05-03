import logging
from typing import Dict, List

from nicegui import ui, events, run, app
from managerui.services import collections_service
from managerui.services import table_index_service
from managerui.ui_helpers import debounced_input, load_page_style

logger = logging.getLogger("vpinfe.manager.collections")
_collection_icons_route_registered = False

def get_collections_manager():
    """Get a fresh VPXCollections instance."""
    return collections_service.get_collections_manager()


def get_table_name_map() -> Dict[str, str]:
    """Build a map of VPS ID -> table name from the tables cache."""
    return collections_service.get_table_name_map()


def vpsid_to_name(vpsid: str, table_map: Dict[str, str] = None) -> str:
    """Convert a VPS ID to table name, or return the ID if not found."""
    return collections_service.vpsid_to_name(vpsid, table_map)


def get_filter_options() -> Dict[str, List[str]]:
    """Get filter options (letters, themes, types, manufacturers, years, ratings) from the tables cache."""
    return collections_service.get_filter_options()


def render_panel(tab=None):
    global _collection_icons_route_registered
    load_page_style("collections.css")
    if not _collection_icons_route_registered:
        icon_dir = collections_service.ensure_collection_icons_dir()
        app.add_media_files('/collection_icons', str(icon_dir))
        _collection_icons_route_registered = True

    with ui.column().classes('w-full'):
        # Header card
        with ui.card().classes('w-full mb-4').style(
            'background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--radius);'
        ):
            with ui.row().classes('w-full justify-between items-center p-4 gap-4'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('collections_bookmark', size='32px').classes('text-white').style('filter: drop-shadow(var(--glow-purple));')
                    ui.label('Collections Manager').classes('text-2xl font-bold text-white').style('text-shadow: var(--glow-purple);')
                with ui.row().classes('gap-3'):
                    add_vpsid_btn = ui.button("New Table Collection", icon="add").props("color=primary rounded")
                    add_filter_btn = ui.button("New Filter Collection", icon="filter_list").props("color=secondary rounded")

        # Collections list container
        collections_container = ui.column().classes('w-full gap-3')

        def create_image_picker(initial_image: str = "") -> dict:
            """Create upload/select controls and return mutable state with selected filename."""
            state = {'filename': initial_image or ''}
            preview_container = ui.column().classes('mt-2')

            def render_preview():
                preview_container.clear()
                with preview_container:
                    if state['filename']:
                        url = collections_service.collection_icon_url(state['filename'])
                        with ui.row().classes('items-center gap-3'):
                            ui.image(url).classes('collection-icon-preview')
                            ui.label(state['filename']).classes('text-sm text-gray-300')
                            ui.button(icon='close', on_click=clear_image).props('flat round dense color=negative').tooltip('Clear image')
                    else:
                        ui.label('No collection image set').classes('text-gray-500 text-sm')

            def clear_image():
                state['filename'] = ''
                render_preview()

            async def handle_upload(e: events.UploadEventArguments):
                try:
                    content = await e.file.read()
                    filename = await run.io_bound(collections_service.save_collection_icon, e.file.name, content)
                    state['filename'] = filename
                    render_preview()
                    ui.notify(f'Collection image uploaded: {filename}', type='positive')
                except Exception as ex:
                    ui.notify(f'Image upload failed: {ex}', type='negative')

            ui.upload(
                label='Upload Collection Image',
                on_upload=handle_upload,
                auto_upload=True,
                max_files=1,
            ).props('accept="image/*" flat bordered').classes('w-full').style('background: var(--bg); border: 1px dashed var(--line);')
            render_preview()
            return state

        def refresh_collections():
            """Refresh the collections list display."""
            collections_container.clear()
            manager = get_collections_manager()
            collection_names = manager.get_collections_name()
            table_map = get_table_name_map()

            def _is_truthy(value) -> bool:
                return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}

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
                    collection_image = collections_service.get_collection_image(name)

                    with ui.card().classes('collection-card w-full p-4'):
                        with ui.row().classes('w-full justify-between items-center'):
                            with ui.row().classes('items-center gap-3 min-w-0 flex-nowrap collection-card-heading'):
                                icon_url = collections_service.collection_icon_url(collection_image)
                                if icon_url:
                                    with ui.element('div').classes('collection-list-icon-wrap flex-none'):
                                        ui.element('img').props(
                                            f'src="{icon_url}" alt="" '
                                            'onmouseenter="const c=this.closest(\'.collection-card\');'
                                            'if(c){c.style.position=\'relative\';c.style.zIndex=\'2147483000\';}'
                                            'this.parentElement.style.zIndex=\'2147483001\';'
                                            'this.style.transform=\'scale(3)\';this.style.zIndex=\'2147483002\';" '
                                            'onmouseleave="const c=this.closest(\'.collection-card\');'
                                            'if(c){c.style.zIndex=\'\';}'
                                            'this.parentElement.style.zIndex=\'\';'
                                            'this.style.transform=\'scale(1)\';this.style.zIndex=\'1\';"'
                                        ).classes('collection-list-icon').style(
                                            'width: 72px; height: 72px; max-width: 72px; max-height: 72px; display: block;'
                                        )
                                else:
                                    ui.icon('filter_list' if is_filter else 'list', size='24px').classes(
                                        ('text-purple-400' if is_filter else 'text-cyan-400') + ' collection-list-fallback-icon flex-none'
                                    )
                                with ui.column().classes('gap-1 min-w-0'):
                                    ui.label(name).classes('text-lg font-medium text-white collection-card-title')
                                    if is_filter:
                                        ui.label('Filter').classes('filter-badge text-white self-start')
                                    else:
                                        vpsids = manager.get_vpsids(name)
                                        ui.label(f'{len(vpsids)}\u00a0Tables').classes('vpsid-badge text-white self-start')

                            with ui.row().classes('gap-2'):
                                ui.button(icon='drive_file_rename_outline', on_click=lambda n=name: open_rename_dialog(n)).props('flat round color=white').tooltip('Rename')
                                ui.button(icon='edit', on_click=lambda n=name, f=is_filter: open_edit_dialog(n, f)).props('flat round color=primary').tooltip('Edit')
                                ui.button(icon='delete', on_click=lambda n=name: confirm_delete(n)).props('flat round color=negative').tooltip('Delete')

                        # Show details based on type
                        if is_filter:
                            filters = manager.get_filters(name)
                            with ui.row().classes('mt-3 gap-2 flex-wrap'):
                                rating_value = filters.get('rating', 'All') if filters else 'All'
                                rating_or_higher = _is_truthy(filters.get('rating_or_higher', 'false')) if filters else False
                                key_labels = {
                                    'letter': 'letter',
                                    'theme': 'theme',
                                    'table_type': 'type',
                                    'manufacturer': 'mfr',
                                    'year': 'year',
                                    'sort_by': 'sort',
                                    'order_by': 'order',
                                }
                                for key in ('letter', 'theme', 'table_type', 'manufacturer', 'year', 'sort_by', 'order_by'):
                                    value = (filters or {}).get(key, '')
                                    if value and value != 'All':
                                        for v in str(value).split(','):
                                            ui.chip(f'{key_labels[key]}: {v.strip()}', icon='label').props('outline color=purple dense')
                                if rating_value and rating_value != 'All':
                                    rating_chip = f'rating: {rating_value}+ ' if rating_or_higher else f'rating: {rating_value}'
                                    ui.chip(rating_chip.strip(), icon='star').props('outline color=amber dense')
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
                            collections_service.delete_collection(name)
                            # Sync the tables cache with updated collection memberships
                            table_index_service.sync_collection_memberships(collections_service.get_vpsid_collections_map())
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
                            collections_service.rename_collection(name, new_name)
                            # Sync the tables cache with updated collection memberships
                            table_index_service.sync_collection_memberships(collections_service.get_vpsid_collections_map())
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
                image_state = create_image_picker()

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
                search_input = debounced_input(ui.input('Search...', placeholder='Type to search tables')).classes('w-full')
                search_results = ui.column().classes('w-full gap-1 mt-2').style('max-height: 200px; overflow-y: auto;')

                async def do_search(e: events.ValueChangeEventArguments):
                    term = (e.value or '').strip().lower()
                    search_results.clear()

                    if not term:
                        return

                    with search_results:
                        matches = await run.io_bound(collections_service.search_tables, term)
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
                            vpsids = [t['id'] for t in selected_tables['items']]
                            collections_service.create_vpsid_collection(name, vpsids, image=image_state['filename'])
                            # Sync the tables cache with updated collection memberships
                            table_index_service.sync_collection_memberships(collections_service.get_vpsid_collections_map())
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
                image_state = create_image_picker()

                ui.label('Filter Criteria:').classes('text-sm text-gray-400 mt-4 mb-2')

                # Multi-select filter dropdowns (empty selection = All)
                _ms_props = 'clearable use-chips multiple'

                def _make_label_updater(select, base_label):
                    def update(e):
                        select.label = base_label if e.value else f'{base_label} (All)'
                    return update

                letter_input = ui.select(label='Starting Letter (All)', options=filter_opts['letters'][1:], value=[], multiple=True).props(_ms_props).classes('w-full')
                letter_input.on_value_change(_make_label_updater(letter_input, 'Starting Letter'))
                theme_input = ui.select(label='Theme (All)', options=filter_opts['themes'][1:], value=[], multiple=True).props(_ms_props).classes('w-full')
                theme_input.on_value_change(_make_label_updater(theme_input, 'Theme'))
                type_input = ui.select(label='Table Type (All)', options=filter_opts['types'][1:], value=[], multiple=True).props(_ms_props).classes('w-full')
                type_input.on_value_change(_make_label_updater(type_input, 'Table Type'))
                manufacturer_input = ui.select(label='Manufacturer (All)', options=filter_opts['manufacturers'][1:], value=[], multiple=True).props(_ms_props).classes('w-full')
                manufacturer_input.on_value_change(_make_label_updater(manufacturer_input, 'Manufacturer'))
                year_input = ui.select(label='Year (All)', options=filter_opts['years'][1:], value=[], multiple=True).props(_ms_props).classes('w-full')
                year_input.on_value_change(_make_label_updater(year_input, 'Year'))
                rating_input = ui.select(label='Rating', options=filter_opts['ratings'], value='All').props('clearable').classes('w-full')
                rating_or_higher_input = ui.checkbox('Or Higher', value=False).classes('text-white')
                rating_or_higher_input.disable()

                def _on_new_rating_change(e):
                    current_rating = e.value or 'All'
                    if current_rating == 'All':
                        rating_or_higher_input.value = False
                        rating_or_higher_input.disable()
                    else:
                        rating_or_higher_input.enable()

                rating_input.on_value_change(_on_new_rating_change)
                sort_input = ui.select(label='Sort By', options=filter_opts['sort_options'], value='Alpha').classes('w-full')
                order_input = ui.select(label='Order By', options=filter_opts['order_options'], value='Descending').classes('w-full')

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
                            selected_rating = rating_input.value or 'All'
                            selected_rating_or_higher = 'true' if (selected_rating != 'All' and rating_or_higher_input.value) else 'false'
                            collections_service.create_filter_collection(
                                name,
                                letter=_join_or_all(letter_input.value),
                                theme=_join_or_all(theme_input.value),
                                table_type=_join_or_all(type_input.value),
                                manufacturer=_join_or_all(manufacturer_input.value),
                                year=_join_or_all(year_input.value),
                                rating=selected_rating,
                                rating_or_higher=selected_rating_or_higher,
                                sort_by=sort_input.value or 'Alpha',
                                order_by=order_input.value or 'Descending',
                                image=image_state['filename'],
                            )
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
            image_state_value = collections_service.get_collection_image(name)

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
            saved_rating = str(filters.get('rating', 'All') or 'All')
            saved_rating_or_higher = str(filters.get('rating_or_higher', 'false')).strip().lower() in {'1', 'true', 'yes', 'on'}

            letter_opts = _ensure_values_in_options(filter_opts['letters'][1:], saved_letters)
            theme_opts = _ensure_values_in_options(filter_opts['themes'][1:], saved_themes)
            type_opts = _ensure_values_in_options(filter_opts['types'][1:], saved_types)
            manufacturer_opts = _ensure_values_in_options(filter_opts['manufacturers'][1:], saved_manufacturers)
            year_opts = _ensure_values_in_options(filter_opts['years'][1:], saved_years)
            rating_opts = list(filter_opts['ratings'])
            if saved_rating not in rating_opts:
                rating_opts.append(saved_rating)

            dlg = ui.dialog().props('persistent max-width=600px')
            with dlg, ui.card().classes('w-[550px]').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                ui.label(f'Edit Filter: {name}').classes('text-xl font-bold text-white')
                ui.separator()
                image_state = create_image_picker(image_state_value)

                ui.label('Filter Criteria:').classes('text-sm text-gray-400 mt-4 mb-2')

                # Multi-select filter dropdowns (empty selection = All)
                _ms_props = 'clearable use-chips multiple'

                def _make_label_updater(select, base_label):
                    def update(e):
                        select.label = base_label if e.value else f'{base_label} (All)'
                    return update

                def _init_label(base_label, values):
                    return base_label if values else f'{base_label} (All)'

                letter_input = ui.select(label=_init_label('Starting Letter', saved_letters), options=letter_opts, value=saved_letters, multiple=True).props(_ms_props).classes('w-full')
                letter_input.on_value_change(_make_label_updater(letter_input, 'Starting Letter'))
                theme_input = ui.select(label=_init_label('Theme', saved_themes), options=theme_opts, value=saved_themes, multiple=True).props(_ms_props).classes('w-full')
                theme_input.on_value_change(_make_label_updater(theme_input, 'Theme'))
                type_input = ui.select(label=_init_label('Table Type', saved_types), options=type_opts, value=saved_types, multiple=True).props(_ms_props).classes('w-full')
                type_input.on_value_change(_make_label_updater(type_input, 'Table Type'))
                manufacturer_input = ui.select(label=_init_label('Manufacturer', saved_manufacturers), options=manufacturer_opts, value=saved_manufacturers, multiple=True).props(_ms_props).classes('w-full')
                manufacturer_input.on_value_change(_make_label_updater(manufacturer_input, 'Manufacturer'))
                year_input = ui.select(label=_init_label('Year', saved_years), options=year_opts, value=saved_years, multiple=True).props(_ms_props).classes('w-full')
                year_input.on_value_change(_make_label_updater(year_input, 'Year'))
                rating_input = ui.select(label='Rating', options=rating_opts, value=saved_rating).props('clearable').classes('w-full')
                rating_or_higher_input = ui.checkbox('Or Higher', value=saved_rating_or_higher).classes('text-white')
                if saved_rating == 'All':
                    rating_or_higher_input.value = False
                    rating_or_higher_input.disable()

                def _on_edit_rating_change(e):
                    current_rating = e.value or 'All'
                    if current_rating == 'All':
                        rating_or_higher_input.value = False
                        rating_or_higher_input.disable()
                    else:
                        rating_or_higher_input.enable()

                rating_input.on_value_change(_on_edit_rating_change)
                saved_order = filters.get('order_by') or 'Descending'
                if saved_order not in filter_opts['order_options']:
                    saved_order = 'Descending'
                sort_input = ui.select(label='Sort By', options=filter_opts['sort_options'], value=filters.get('sort_by', 'Alpha')).classes('w-full')
                order_input = ui.select(label='Order By', options=filter_opts['order_options'], value=saved_order).classes('w-full')

                def _join_or_all(values):
                    if not values:
                        return 'All'
                    return ','.join(str(v) for v in values)

                with ui.row().classes('justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dlg.close).props('flat')

                    def save_changes():
                        try:
                            selected_rating = rating_input.value or 'All'
                            collections_service.update_filter_collection(
                                name,
                                letter=_join_or_all(letter_input.value),
                                theme=_join_or_all(theme_input.value),
                                table_type=_join_or_all(type_input.value),
                                manufacturer=_join_or_all(manufacturer_input.value),
                                year=_join_or_all(year_input.value),
                                rating=selected_rating,
                                rating_or_higher='true' if (selected_rating != 'All' and rating_or_higher_input.value) else 'false',
                                sort_by=sort_input.value or 'Alpha',
                                order_by=order_input.value or 'Descending',
                                image=image_state['filename'],
                            )
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
            image_state_value = collections_service.get_collection_image(name)

            dlg = ui.dialog().props('persistent max-width=800px')
            with dlg, ui.card().classes('w-[750px]').style('background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);'):
                ui.label(f'Edit Collection: {name}').classes('text-xl font-bold text-white')
                ui.separator()
                image_state = create_image_picker(image_state_value)

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
                search_input = debounced_input(ui.input('Search...', placeholder='Type to search tables')).classes('w-full')
                search_results = ui.column().classes('w-full gap-1 mt-2').style('max-height: 150px; overflow-y: auto;')

                async def do_search(e: events.ValueChangeEventArguments):
                    term = (e.value or '').strip().lower()
                    search_results.clear()

                    if not term:
                        return

                    with search_results:
                        matches = await run.io_bound(collections_service.search_tables, term)
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
                            vpsids = [t['id'] for t in selected_tables['items']]
                            collections_service.update_vpsid_collection(name, vpsids, image=image_state['filename'])
                            # Sync the tables cache with updated collection memberships
                            table_index_service.sync_collection_memberships(collections_service.get_vpsid_collections_map())
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
