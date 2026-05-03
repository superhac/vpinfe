from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Callable, Optional

from nicegui import context, events, run, ui

from managerui.pages.table_dialog_context import TableDialogContext, default_context
from managerui.services import table_index_service, table_service
from managerui.services.media_service import invalidate_media_cache
from managerui.ui_helpers import load_page_style


logger = logging.getLogger("vpinfe.manager.tables")
ACCEPT_CRZ = ['.crz', '.cRZ', '.CRZ']
ACCEPT_VNI = ['.vni', '.VNI', '.pal', '.PAL']

normalize_table_rating = table_service.normalize_table_rating
update_vpinfe_setting = table_service.update_vpinfe_setting
update_user_setting = table_service.update_user_setting
get_vpsid_collections = table_service.get_vpsid_collections
get_vpsid_collections_map = table_service.get_vpsid_collections_map
ensure_dir = table_service.ensure_dir
save_upload_bytes = table_service.save_upload_bytes


def add_table_to_collection(vpsid: str, collection_name: str) -> bool:
    if not table_service.add_table_to_collection(vpsid, collection_name):
        return False
    table_index_service.add_collection_membership(vpsid, collection_name)
    return True


def open_table_dialog(
    row_data: dict,
    on_close: Optional[Callable[[], None]] = None,
    context: TableDialogContext | None = None,
):
    context = context or default_context()
    on_close = on_close or context.refresh_tables
    return _render_table_dialog(row_data, on_close=on_close)


def _render_table_dialog(row_data: dict, on_close: Optional[Callable[[], None]] = None):
    # Add dialog styles
    load_page_style("table_dialog.css")

    dlg = ui.dialog()
    with dlg, ui.card().classes('table-dialog-card').style('width: 1000px; max-width: 85vw;'):
        table_name = row_data.get('name') or row_data.get('filename') or 'Table'
        table_path_str = row_data.get('table_path', '')
        row_data['rating'] = normalize_table_rating(row_data.get('rating', 0))

        # Header
        with ui.row().classes('table-dialog-header w-full items-center gap-3'):
            ui.icon('casino', size='32px').style('color: var(--ink);')
            with ui.column().classes('gap-0 flex-grow'):
                with ui.row().classes('items-center gap-2'):
                    title_label = ui.label(table_name).classes('text-xl font-bold').style('color: var(--ink);')
                    if (row_data.get('altlauncher', '') or '').strip():
                        ui.badge('ALT-L', color='warning').props('rounded')
                    if (row_data.get('alttitle', '') or '').strip():
                        ui.badge('ALT-T', color='info').props('rounded')
                manufacturer = row_data.get('manufacturer', '')
                year = row_data.get('year', '')
                if manufacturer or year:
                    ui.label(f'{manufacturer} {year}'.strip()).classes('text-sm').style('color: var(--neon-purple);')
            # Rebuild metadata button - anchored to the right
            table_dir_name = os.path.basename(row_data.get('table_path', ''))
            if table_dir_name:
                rebuild_btn = ui.button('Rebuild Meta', icon='refresh').props('dense').classes('ml-auto').style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')
                update_btn = ui.button('Update Table', icon='upload_file').props('dense').style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')
                rebuild_status = ui.label('').classes('text-xs ml-2').style('color: var(--ink);')
                rebuild_status.visible = False
                rebuild_client = context.client

                async def on_rebuild_meta():
                    client = rebuild_client
                    with client:
                        rebuild_btn.disable()
                        rebuild_status.visible = True
                        rebuild_status.set_text('Rebuilding...')
                    try:
                        result = await run.io_bound(
                            table_service.build_metadata,
                            downloadMedia=True,
                            updateAll=True,
                            tableName=table_dir_name,
                        )
                        with client:
                            not_found = result.get('not_found', 0)
                            if not_found > 0:
                                rebuild_status.set_text('Not found in VPS')
                                ui.notify('Table not found in VPSdb', type='warning')
                            else:
                                rebuild_status.visible = False
                                ui.notify('Metadata rebuilt successfully', type='positive')
                            # Invalidate media cache so media page shows fresh data
                            invalidate_media_cache()
                    except Exception as ex:
                        with client:
                            rebuild_status.set_text('Error')
                            ui.notify(f'Rebuild failed: {ex}', type='negative')
                    finally:
                        with client:
                            rebuild_btn.enable()

                def open_update_table_dialog():
                    update_dlg = ui.dialog()
                    with update_dlg, ui.card().classes('table-dialog-card').style('width: 620px; max-width: 92vw;'):
                        ui.label('Update Table').classes('text-lg font-semibold').style('color: var(--ink);')
                        ui.label(table_name).classes('text-sm').style('color: var(--ink-muted);')
                        update_status = ui.label('Choose a .vpx table file or .directb2s backglass file.').classes('text-xs').style('color: var(--ink-muted);')

                        async def handle_table_update(e: events.UploadEventArguments, file_type: str):
                            upload_name = e.file.name
                            data = await e.file.read()
                            client = context.client
                            with client:
                                update_btn.disable()
                                rebuild_btn.disable()
                                update_status.set_text(f'Updating {upload_name}...')
                            try:
                                result = await run.io_bound(
                                    table_service.replace_table_file,
                                    table_path_str,
                                    upload_name,
                                    data,
                                    file_type,
                                    row_data.get('filename', ''),
                                )
                                if result.get('file_type') == 'vpx':
                                    row_data['filename'] = result.get('filename', row_data.get('filename', ''))
                                    table_index_service.update_row_by_path(table_path_str, {'filename': row_data['filename']})
                                    with client:
                                        update_status.set_text('Table file updated. Rebuilding metadata...')
                                        ui.notify('Table file updated', type='positive')
                                    await on_rebuild_meta()
                                else:
                                    with client:
                                        update_status.set_text(f'Backglass updated: {result.get("filename", "")}')
                                        ui.notify('Backglass updated', type='positive')

                                invalidate_media_cache()
                                if on_close:
                                    on_close()
                            except Exception as ex:
                                logger.exception('Table update failed')
                                with client:
                                    update_status.set_text('Update failed')
                                    ui.notify(f'Update failed: {ex}', type='negative')
                            finally:
                                with client:
                                    update_btn.enable()
                                    rebuild_btn.enable()

                        ui.separator()
                        with ui.column().classes('w-full gap-3'):
                            with ui.column().classes('w-full gap-1'):
                                ui.label('Replace table file (.vpx)').classes('text-sm').style('color: var(--ink);')
                                ui.upload(
                                    on_upload=lambda e: asyncio.create_task(handle_table_update(e, 'vpx')),
                                    auto_upload=True,
                                    max_files=1,
                                ).props('accept=".vpx" flat bordered').classes('w-full').style(
                                    'background: var(--bg); border: 1px dashed var(--line);'
                                )
                            with ui.column().classes('w-full gap-1'):
                                ui.label('Replace backglass (.directb2s)').classes('text-sm').style('color: var(--ink);')
                                ui.upload(
                                    on_upload=lambda e: asyncio.create_task(handle_table_update(e, 'directb2s')),
                                    auto_upload=True,
                                    max_files=1,
                                ).props('accept=".directb2s" flat bordered').classes('w-full').style(
                                    'background: var(--bg); border: 1px dashed var(--line);'
                                )

                        with ui.column().classes('w-full gap-1 q-mt-sm').style(
                            'background: var(--bg); border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px;'
                        ):
                            ui.label('How updates work').classes('text-sm font-semibold').style('color: var(--ink);')
                            ui.label('.vpx: deletes the old table file, saves the uploaded table file, renames any existing .directb2s to match the new table filename, then rebuilds metadata.').classes('text-xs').style('color: var(--ink-muted);')
                            ui.label('.directb2s: saves the uploaded backglass using the existing .directb2s filename. If none exists, it uses the current .vpx filename with a .directb2s extension.').classes('text-xs').style('color: var(--ink-muted);')

                        with ui.row().classes('w-full justify-end'):
                            ui.button('Close', icon='close', on_click=update_dlg.close).props('flat').style('color: var(--ink-muted);')

                    update_dlg.open()

                rebuild_btn.on_click(lambda: asyncio.create_task(on_rebuild_meta()))
                update_btn.on_click(open_update_table_dialog)

        # Main info section
        with ui.column().classes('w-full gap-4 p-4'):
            # Key details in a grid
            with ui.card().classes('w-full p-4').style('background: var(--bg); border: 1px solid var(--line); border-radius: var(--radius);'):
                ui.label('Table Information').classes('text-lg font-semibold mb-3').style('color: var(--ink);')

                # Define which fields to show and their display names
                display_fields = [
                    ('filename', 'Filename', 'description'),
                    ('id', 'VPS ID', 'fingerprint'),
                    ('rom', 'ROM', 'memory'),
                    ('version', 'Version', 'tag'),
                    ('type', 'Type', 'category'),
                    ('table_path', 'Folder', 'folder'),
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
                            display_value = os.path.basename(value) if key == 'table_path' else str(value)
                            with ui.row().classes('detail-row items-center gap-2 w-full'):
                                ui.icon(icon, size='18px').style('color: var(--neon-purple);')
                                ui.label(label).classes('detail-label')
                                ui.label(display_value).classes('detail-value')

                    # Render list fields (authors, themes) - join lists with comma
                    for key, label, icon in list_fields:
                        value = row_data.get(key, [])
                        if value:
                            display_value = ', '.join(value) if isinstance(value, list) else str(value)
                            with ui.row().classes('detail-row items-center gap-2 w-full'):
                                ui.icon(icon, size='18px').style('color: var(--neon-purple);')
                                ui.label(label).classes('detail-label')
                                ui.label(display_value).classes('detail-value')

                # Render hash fields side by side
                with ui.row().classes('w-full gap-3'):
                    for key, label, icon in long_fields:
                        value = row_data.get(key, '')
                        if value:
                            with ui.row().classes('detail-row items-center gap-2').style('flex: 1; flex-wrap: nowrap;'):
                                ui.icon(icon, size='18px').style('color: var(--neon-purple); flex-shrink: 0;')
                                ui.label(label).style('color: var(--neon-cyan); font-size: 0.85rem; flex-shrink: 0;')
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
                        ui.icon('settings_suggest', size='18px').style('color: var(--neon-purple);')
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
                    ui.icon('extension', size='18px').style('color: var(--neon-purple);')
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

                # User rating row
                rating_state = {'value': normalize_table_rating(row_data.get('rating', 0))}
                rating_buttons = []

                with ui.row().classes('detail-row items-center gap-2 w-full mt-2'):
                    ui.icon('star', size='18px').style('color: var(--neon-purple);')
                    ui.label('Rating').classes('detail-label')
                    with ui.row().classes('items-center gap-1 flex-wrap'):
                        rating_text = ui.label('').style('color: var(--neon-cyan); font-size: 0.85rem; min-width: 48px;')

                        def refresh_rating_ui() -> None:
                            value = normalize_table_rating(rating_state['value'])
                            rating_text.set_text(f'({value}/5)')
                            for idx, button in enumerate(rating_buttons, start=1):
                                is_set = idx <= value
                                color = 'var(--neon-yellow)' if is_set else 'var(--shadow)'
                                button.set_text('★' if is_set else '☆')
                                button.style(
                                    'min-width: 34px; '
                                    f'color: {color} !important; '
                                    'font-size: 1.1rem; '
                                    'background: transparent !important;'
                                )

                        def save_rating(new_rating: int) -> None:
                            clamped = normalize_table_rating(new_rating)
                            if not table_path_str:
                                ui.notify('Unable to save rating: missing table path', type='negative')
                                return
                            if update_user_setting(table_path_str, 'Rating', clamped):
                                rating_state['value'] = clamped
                                row_data['rating'] = clamped
                                table_index_service.update_row_by_path(table_path_str, {'rating': clamped})
                                refresh_rating_ui()
                                if on_close:
                                    on_close()
                                ui.notify('Rating saved', type='positive')
                            else:
                                ui.notify('Failed to save rating', type='negative')

                        for star_index in range(1, 6):
                            star_button = ui.button('★', on_click=lambda v=star_index: save_rating(v)).props(
                                'flat round dense color=white text-color=white'
                            )
                            rating_buttons.append(star_button)

                        ui.button(
                            'Clear',
                            on_click=lambda: save_rating(0)
                        ).props('flat dense size=sm').classes('ml-1').style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')

                        refresh_rating_ui()

            # Collections section - add table to collection
            vpsid = row_data.get('id', '')
            current_collections = row_data.get('collections', [])
            available_collections = get_vpsid_collections()

            if vpsid and available_collections:
                with ui.card().classes('w-full p-4').style('background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);'):
                    ui.label('Collections').classes('text-lg font-semibold mb-3').style('color: var(--ink);')

                    # Show current collections
                    if current_collections:
                        with ui.row().classes('gap-2 flex-wrap mb-3'):
                            ui.label('Member of:').classes('text-sm').style('color: var(--ink-muted);')
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

                            ui.button('Add', icon='add', on_click=on_add_to_collection).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')
                    else:
                        ui.label('Table is in all available collections').classes('text-sm').style('color: var(--ink-muted);')

            # VPinFE Settings section
            with ui.card().classes('w-full p-4').style('background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);'):
                ui.label('Overrides').classes('text-lg font-semibold mb-3').style('color: var(--ink);')

                delete_nvram_value = row_data.get('delete_nvram_on_close', False)
                altlauncher_value = row_data.get('altlauncher', '')
                alttitle_value = row_data.get('alttitle', '')
                altvpsid_value = row_data.get('altvpsid', '')
                frontend_dof_event_value = row_data.get('frontend_dof_event', '')

                with ui.row().classes('items-center gap-3 w-full'):
                    alttitle_input = ui.input(
                        label='Alt Title',
                        value=alttitle_value,
                        placeholder='Optional display name override'
                    ).props('outlined dense clearable').classes('flex-grow')

                    def on_alttitle_save():
                        new_value = (alttitle_input.value or '').strip()
                        if update_vpinfe_setting(table_path_str, 'alttitle', new_value):
                            row_data['alttitle'] = new_value
                            fallback_name = (row_data.get('filename') or 'Table').strip()
                            try:
                                info_path = Path(table_path_str) / f"{Path(table_path_str).name}.info"
                                with open(info_path, 'r', encoding='utf-8') as f:
                                    raw = json.load(f)
                                info = raw.get("Info", {})
                                fallback_name = (info.get("Title") or raw.get("name") or fallback_name).strip()
                            except Exception:
                                pass
                            effective_name = new_value or fallback_name
                            table_index_service.update_row_by_path(table_path_str, {
                                'alttitle': new_value,
                                'name': effective_name,
                            })
                            row_data['name'] = effective_name
                            title_label.set_text(effective_name)
                            # Keep media list in sync on next visit
                            invalidate_media_cache()
                            if on_close:
                                on_close()
                            ui.notify('Alt title saved', type='positive')
                        else:
                            ui.notify('Failed to save alt title', type='negative')

                    ui.button('Save', icon='save', on_click=on_alttitle_save).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')
                ui.label('When set, this overrides the table name shown in Manager UI lists').classes('text-xs').style('color: var(--ink-muted);')

                with ui.row().classes('items-center gap-3 w-full'):
                    altvpsid_input = ui.input(
                        label='Alt VPS ID',
                        value=altvpsid_value,
                        placeholder='Optional VPS ID override'
                    ).props('outlined dense clearable').classes('flex-grow')

                    def on_altvpsid_save():
                        new_value = (altvpsid_input.value or '').strip()
                        if update_vpinfe_setting(table_path_str, 'altvpsid', new_value):
                            row_data['altvpsid'] = new_value
                            fallback_id = (row_data.get('id') or '').strip()
                            try:
                                info_path = Path(table_path_str) / f"{Path(table_path_str).name}.info"
                                with open(info_path, 'r', encoding='utf-8') as f:
                                    raw = json.load(f)
                                info = raw.get("Info", {})
                                fallback_id = (info.get("VPSId") or raw.get("id") or fallback_id).strip()
                            except Exception:
                                pass
                            effective_id = new_value or fallback_id
                            vpsid_collections_map = get_vpsid_collections_map()
                            table_index_service.update_row_by_path(table_path_str, {
                                'altvpsid': new_value,
                                'id': effective_id,
                                'collections': vpsid_collections_map.get(effective_id, []),
                            })
                            row_data['id'] = effective_id
                            row_data['collections'] = get_vpsid_collections_map().get(effective_id, [])
                            if on_close:
                                on_close()
                            ui.notify('Alt VPS ID saved', type='positive')
                        else:
                            ui.notify('Failed to save alt VPS ID', type='negative')

                    ui.button('Save', icon='save', on_click=on_altvpsid_save).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')
                ui.label('When set, this overrides the VPS ID shown/used in Manager UI').classes('text-xs').style('color: var(--ink-muted);')

                with ui.row().classes('items-center gap-3 w-full'):
                    altlauncher_input = ui.input(
                        label='Alt Launcher',
                        value=altlauncher_value,
                        placeholder='Optional executable override for this table'
                    ).props('outlined dense clearable').classes('flex-grow')

                    def on_altlauncher_save():
                        new_value = (altlauncher_input.value or '').strip()
                        if update_vpinfe_setting(table_path_str, 'altlauncher', new_value):
                            row_data['altlauncher'] = new_value
                            table_index_service.update_row_by_path(table_path_str, {'altlauncher': new_value})
                            ui.notify('Alt launcher saved', type='positive')
                        else:
                            ui.notify('Failed to save alt launcher', type='negative')

                    ui.button('Save', icon='save', on_click=on_altlauncher_save).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')
                ui.label('When set, this overrides Settings.vpxbinpath for this table only').classes('text-xs').style('color: var(--ink-muted);')

                with ui.row().classes('items-center gap-3 w-full'):
                    frontend_dof_event_input = ui.input(
                        label='FrontendDOFEvent',
                        value=frontend_dof_event_value,
                        placeholder='Optional frontend DOF event override'
                    ).props('outlined dense clearable').classes('flex-grow')

                    def on_frontend_dof_event_save():
                        new_value = (frontend_dof_event_input.value or '').strip()
                        if update_user_setting(table_path_str, 'FrontendDOFEvent', new_value):
                            row_data['frontend_dof_event'] = new_value
                            table_index_service.update_row_by_path(table_path_str, {'frontend_dof_event': new_value})
                            ui.notify('Frontend DOF event saved', type='positive')
                        else:
                            ui.notify('Failed to save Frontend DOF event', type='negative')

                    ui.button('Save', icon='save', on_click=on_frontend_dof_event_save).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink) !important; border-radius: 18px; padding: 4px 10px;')
                ui.label('When set, this stores the per-table User.FrontendDOFEvent value').classes('text-xs').style('color: var(--ink-muted);')

                with ui.row().classes('items-center gap-3 mt-3'):
                    def on_delete_nvram_change(e):
                        new_value = e.value
                        if update_vpinfe_setting(table_path_str, 'deletedNVRamOnClose', new_value):
                            row_data['delete_nvram_on_close'] = new_value
                            # Also update the cache so the value persists across dialog opens
                            table_index_service.update_row_by_path(table_path_str, {'delete_nvram_on_close': new_value})
                            ui.notify('Setting saved', type='positive')
                        else:
                            ui.notify('Failed to save setting', type='negative')
                            # Revert checkbox
                            e.sender.value = not new_value

                    nvram_checkbox = ui.checkbox('Delete NVRAM on close', value=delete_nvram_value)
                    nvram_checkbox.on_value_change(on_delete_nvram_change)
                    ui.label('Remove NVRAM file when table exits').classes('text-xs').style('color: var(--ink-muted);')

            # Addons section
            with ui.expansion('Install Addons', icon='extension').classes('w-full').style('background: var(--bg); opacity: 0.5; border-radius: 8px;'):
                table_path = Path(row_data.get('table_path', ''))
                rom_name = (row_data.get('rom') or '').strip()

                with ui.column().classes('gap-4 p-2').style('background: var(--surface); border-radius: 8px;'):
                    # Pupvideos uploader (zip file)
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('video_library', size='24px').style('color: var(--neon-purple);')
                            with ui.column().classes('gap-0'):
                                ui.label('PupVideos').classes('font-medium').style('color: var(--ink);')
                                ui.label('Upload .zip file to extract to pupvideos folder').classes('text-xs').style('color: var(--ink-muted);')
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
                        ui.upload(on_upload=on_pup_upload, multiple=False).props('flat label="Upload .zip"').style('color: var(--neon-purple); background: var(--surface); border: 1px solid var(--neon-purple); border-radius: var(--radius);')

                    # Serum uploader
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('palette', size='24px').style('color: var(--warning);')
                            with ui.column().classes('gap-0'):
                                ui.label('Serum').classes('font-medium').style('color: var(--ink);')
                                ui.label('Upload .cRZ color files (requires ROM)').classes('text-xs').style('color: var(--ink-muted);')
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
                        ui.upload(on_upload=on_altcolor_upload, multiple=False).props('flat label="Upload .cRZ"').style('color: var(--neon-purple); background: var(--surface); border: 1px solid var(--neon-purple); border-radius: var(--radius);')

                    # VNI uploader
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('palette', size='24px').style('color: var(--neon-cyan);')
                            with ui.column().classes('gap-0'):
                                ui.label('VNI').classes('font-medium').style('color: var(--ink);')
                                ui.label('Upload .vni and .pal files (requires ROM)').classes('text-xs').style('color: var(--ink-muted);')
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
                        ui.upload(on_upload=on_vni_upload, multiple=True).props('flat label="Upload .vni/.pal"').style('color: var(--neon-purple); background: var(--surface); border: 1px solid var(--neon-purple); border-radius: var(--radius);')

                    # AltSound uploader
                    with ui.row().classes('addon-card w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('music_note', size='24px').style('color: var(--ok);')
                            with ui.column().classes('gap-0'):
                                ui.label('AltSound').classes('font-medium').style('color: var(--ink);')
                                ui.label('Upload sound pack files (requires ROM)').classes('text-xs').style('color: var(--ink-muted);')
                        def on_altsound_upload(e):
                            if not rom_name:
                                ui.notify('ROM not found. Update metadata first.', type='warning')
                                return
                            dest = table_path / 'pinmame' / 'altsound' / rom_name / e.name
                            # Read content from SpooledTemporaryFile if needed
                            content = e.content.read() if hasattr(e.content, 'read') else e.content
                            save_upload_bytes(dest, content)
                            ui.notify(f'Saved: {e.name}', type='positive')
                        ui.upload(on_upload=on_altsound_upload, multiple=True).props('flat label="Upload"').style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple) !important;')

        # Footer with close button
        with ui.row().classes('w-full justify-end p-4 pt-0'):
            def close_dialog():
                dlg.close()
                if on_close:
                    on_close()
            ui.button('Close', icon='close', on_click=close_dialog).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink) !important; border-radius: 18px; padding: 4px 10px;')
    dlg.open()
