from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from pathlib import Path
from typing import Dict, List

from nicegui import context, events, run, ui

from managerui.paths import get_tables_path
from managerui.services import table_service
from managerui.services.media_service import invalidate_media_cache
from managerui.ui_helpers import debounced_input


logger = logging.getLogger("vpinfe.manager.tables")
associate_vps_to_folder = table_service.associate_vps_to_folder
ensure_dir = table_service.ensure_dir
save_upload_bytes = table_service.save_upload_bytes
search_vpsdb = table_service.search_vpsdb


def open_import_table_dialog(perform_scan_cb=None):
    """Top-level dialog for importing a new table with associated files."""
    dlg = ui.dialog().props('persistent max-width=900px')
    import_state = {
        'vps_entry': None,
        'vpx_file': None,       # (name, bytes)
        'directb2s_file': None,  # (name, bytes)
        'rom_file': None,        # (name, bytes)
        'puppack_zip': None,     # (name, bytes)
        'music_zip': None,       # (name, bytes)
        'busy': False,
        'client': context.client,
    }

    def update_import_btn_state():
        can_import = import_state['vps_entry'] is not None and import_state['vpx_file'] is not None
        if can_import:
            do_import_btn.enable()
        else:
            do_import_btn.disable()

    with dlg, ui.card().classes('w-[850px] max-w-[95vw]').style(
        'position: relative; max-height: 90vh; overflow-y: auto;'
    ):
        ui.label('Import Table').classes('text-xl font-bold').style('color: var(--ink);')
        ui.separator()

        # --- Step 1: VPS Search & Selection ---
        ui.label('Step 1: Associate with VPS Database').classes('text-md font-semibold text-blue-300')

        with ui.row().classes('w-full items-center gap-3'):
            selected_label = ui.label('No table selected').classes('text-sm').style('color: var(--ink-muted);')

            def open_vps_search_dialog():
                """Open a separate dialog to search and select a VPS entry."""
                search_dlg = ui.dialog().props('max-width=1080px')

                with search_dlg, ui.card().classes('w-[960px] max-w-[95vw]').style('position: relative; overflow: hidden;'):
                    ui.label('Search VPS Database').classes('text-lg font-bold')
                    ui.separator()

                    results_container = ui.column().classes('gap-1 w-full q-mt-sm').style('max-height: 55vh; overflow: auto;')

                    def render_results(items: List[Dict]):
                        results_container.clear()
                        if not items:
                            with results_container:
                                ui.label('Search by Table Name').classes('text-sm').style('color: var(--ink-muted);')
                            return
                        for it in items:
                            name = it.get('name', '')
                            manuf = it.get('manufacturer') or it.get('mfg') or ''
                            year = it.get('year') or ''
                            vid = it.get('id') or ''
                            with results_container:
                                with ui.row().classes('items-center w-full q-py-xs border-b gap-2').style('flex-wrap: nowrap;'):
                                    ui.label(f"{name} — {manuf} — {year} (ID: {vid})").classes('text-sm').style(
                                        'flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'
                                    )

                                    def _on_pick(it=it):
                                        import_state['vps_entry'] = it
                                        sel_name = it.get('name', '')
                                        sel_manuf = it.get('manufacturer') or it.get('mfg') or ''
                                        sel_year = it.get('year') or ''
                                        display = f"{sel_name} ({sel_manuf} {sel_year})".strip()
                                        selected_label.set_text(f'✓ {display}')
                                        selected_label.classes(add='font-semibold')
                                        selected_label.style(remove='color: var(--ink-muted)', add='color: var(--ok)')
                                        update_import_btn_state()
                                        search_dlg.close()

                                    ui.button('Select', on_click=_on_pick).style('flex-shrink: 0; color: var(--neon-pink); background: var(--surface); border: 1px solid var(--neon-pink); border-radius: var(--radius);')

                    search_input = debounced_input(ui.input('Search VPS…', value='')).classes('w-full')

                    def on_search_change(e: events.ValueChangeEventArguments):
                        term = e.value or ''
                        render_results(search_vpsdb(term, limit=80))

                    search_input.on_value_change(on_search_change)
                    render_results([])

                    with ui.row().classes('justify-end q-mt-md'):
                        ui.button('Close', on_click=search_dlg.close).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink) !important; border-radius: 18px; padding: 4px 10px;')

                search_dlg.open()

            ui.button('Search VPS…', icon='search', on_click=open_vps_search_dialog).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink) !important; border-radius: 18px; padding: 4px 10px;')

        ui.separator().classes('q-mt-sm')

        # --- Step 2: File Uploads ---
        ui.label('Step 2: Upload Files').classes('text-md font-semibold text-blue-300 q-mt-sm')

        # VPX file (required)
        with ui.row().classes('w-full items-center gap-3'):
            ui.label('Table File (.vpx) *').classes('text-sm').style('color: var(--ink); min-width: 160px;')
            vpx_status = ui.label('No file selected').classes('text-xs').style('color: var(--ink-muted);')

        async def on_vpx_upload(e: events.UploadEventArguments):
            data = await e.file.read()
            import_state['vpx_file'] = (e.file.name, data)
            vpx_status.set_text(f'✓ {e.file.name}')
            vpx_status.style(remove='color: var(--ink-muted)', add='color: var(--ok)')
            update_import_btn_state()

        ui.upload(
            on_upload=on_vpx_upload,
            auto_upload=True,
            max_files=1,
        ).props('accept=".vpx" flat bordered').classes('w-full').style(
            'background: var(--bg); border: 1px dashed var(--line);'
        )

        # DirectB2S file (optional)
        with ui.row().classes('w-full items-center gap-3 q-mt-sm'):
            ui.label('Backglass (.directb2s)').classes('text-sm').style('color: var(--ink); min-width: 160px;')
            b2s_status = ui.label('No file selected').classes('text-xs').style('color: var(--ink-muted);')

        async def on_b2s_upload(e: events.UploadEventArguments):
            data = await e.file.read()
            import_state['directb2s_file'] = (e.file.name, data)
            b2s_status.set_text(f'✓ {e.file.name}')
            b2s_status.style(remove='color: var(--ink-muted)', add='color: var(--ok)')

        ui.upload(
            on_upload=on_b2s_upload,
            auto_upload=True,
            max_files=1,
        ).props('accept=".directb2s" flat bordered').classes('w-full').style(
            'background: var(--bg); border: 1px dashed var(--line);'
        )

        # PinMAME ROM (optional)
        with ui.row().classes('w-full items-center gap-3 q-mt-sm'):
            ui.label('PinMAME ROM (.zip)').classes('text-sm').style('color: var(--ink); min-width: 160px;')
            rom_status = ui.label('No file selected').classes('text-xs').style('color: var(--ink-muted);')

        async def on_rom_upload(e: events.UploadEventArguments):
            data = await e.file.read()
            import_state['rom_file'] = (e.file.name, data)
            rom_status.set_text(f'✓ {e.file.name}')
            rom_status.style(remove='color: var(--ink-muted)', add='color: var(--ok)')

        ui.upload(
            on_upload=on_rom_upload,
            auto_upload=True,
            max_files=1,
        ).props('accept=".zip" flat bordered').classes('w-full').style(
            'background: #0f172a; border: 1px dashed #475569;'
        )

        # PUP Pack (.zip)
        with ui.row().classes('w-full items-center gap-3 q-mt-sm'):
            ui.label('PUP Pack (.zip)').classes('text-sm').style('color: var(--ink); min-width: 160px;')
            pup_status = ui.label('No file selected').classes('text-xs').style('color: var(--ink-muted);')

        async def on_pup_upload(e: events.UploadEventArguments):
            data = await e.file.read()
            import_state['puppack_zip'] = (e.file.name, data)
            pup_status.set_text(f'✓ {e.file.name}')
            pup_status.style(remove='color: var(--ink-muted)', add='color: var(--ok)')

        ui.upload(
            on_upload=on_pup_upload,
            auto_upload=True,
            max_files=1,
        ).props('accept=".zip" flat bordered').classes('w-full').style(
            'background: var(--bg); border: 1px dashed var(--line);'
        )

        # Music (.zip)
        with ui.row().classes('w-full items-center gap-3 q-mt-sm'):
            ui.label('Music (.zip)').classes('text-sm').style('color: var(--ink); min-width: 160px;')
            music_status = ui.label('No file selected').classes('text-xs').style('color: var(--ink-muted);')

        async def on_music_upload(e: events.UploadEventArguments):
            data = await e.file.read()
            import_state['music_zip'] = (e.file.name, data)
            music_status.set_text(f'✓ {e.file.name}')
            music_status.style(remove='color: var(--ink-muted)', add='color: var(--ok)')

        ui.upload(
            on_upload=on_music_upload,
            auto_upload=True,
            max_files=1,
        ).props('accept=".zip" flat bordered').classes('w-full').style(
            'background: var(--bg); border: 1px dashed var(--line);'
        )

        # Loading overlay (over entire card)
        import_loading_overlay = ui.element('div').style(
            'position: absolute; top: 0; left: 0; right: 0; bottom: 0; '
            'background: var(--bg); opacity: 0.9; z-index: 1000; '
            'display: none; flex-direction: column; align-items: center; justify-content: center;'
        )
        with import_loading_overlay:
            with ui.column().classes('items-center justify-center gap-4 w-full'):
                ui.spinner('dots', size='xl', color='blue')
                import_loading_label = ui.label('Importing table...').classes('text-lg text-center').style('color: var(--ink);')

        ui.separator()

        # --- Buttons ---
        with ui.row().classes('justify-end gap-2 q-mt-sm w-full'):
            ui.button('Cancel', on_click=dlg.close).props('flat').style('color: var(--ink-muted);')
            do_import_btn = ui.button('Import', icon='upload').style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink) !important; border-radius: 18px; padding: 4px 10px;')
            do_import_btn.disable()

        async def do_import():
            if import_state['busy']:
                return
            if not import_state['vps_entry'] or not import_state['vpx_file']:
                ui.notify('Please select a VPS entry and upload a .vpx file', type='warning')
                return

            import_state['busy'] = True
            client = import_state['client']

            with client:
                import_loading_overlay.style(add='display: flex;', remove='display: none;')
                import_loading_label.set_text('Creating table folder...')
                do_import_btn.disable()

            try:
                vps_entry = import_state['vps_entry']
                # Build folder name
                name = vps_entry.get('name', '')
                mfg = vps_entry.get('manufacturer') or vps_entry.get('mfg') or ''
                year = vps_entry.get('year') or ''
                if mfg and year:
                    folder_name = f"{name} ({mfg} {year})"
                elif mfg:
                    folder_name = f"{name} ({mfg})"
                elif year:
                    folder_name = f"{name} ({year})"
                else:
                    folder_name = name
                # Sanitize
                folder_name = "".join(c for c in folder_name if c not in '<>:"/\\|?*')

                table_root = get_tables_path()
                table_dir = Path(table_root) / folder_name

                if table_dir.exists():
                    with client:
                        ui.notify(f'Folder already exists: {folder_name}', type='negative')
                        import_loading_overlay.style(add='display: none;', remove='display: flex;')
                        do_import_btn.enable()
                    import_state['busy'] = False
                    return

                # Create folder
                ensure_dir(table_dir)

                # Write VPX file
                with client:
                    import_loading_label.set_text('Copying table file...')
                vpx_name, vpx_bytes = import_state['vpx_file']
                await run.io_bound(save_upload_bytes, table_dir / vpx_name, vpx_bytes)

                # Write directb2s if provided
                if import_state['directb2s_file']:
                    with client:
                        import_loading_label.set_text('Copying backglass file...')
                    b2s_name, b2s_bytes = import_state['directb2s_file']
                    await run.io_bound(save_upload_bytes, table_dir / b2s_name, b2s_bytes)

                # Write ROM if provided
                if import_state['rom_file']:
                    with client:
                        import_loading_label.set_text('Copying PinMAME ROM...')
                    rom_name, rom_bytes = import_state['rom_file']
                    await run.io_bound(save_upload_bytes, table_dir / 'pinmame' / 'roms' / rom_name, rom_bytes)

                # Extract PUP Pack zip if provided
                if import_state['puppack_zip']:
                    with client:
                        import_loading_label.set_text('Extracting PUP Pack...')
                    pup_name, pup_bytes = import_state['puppack_zip']
                    dest = table_dir / 'pupvideos'
                    ensure_dir(dest)
                    await run.io_bound(lambda: zipfile.ZipFile(io.BytesIO(pup_bytes)).extractall(dest))

                # Extract music zip if provided
                if import_state['music_zip']:
                    with client:
                        import_loading_label.set_text('Extracting music...')
                    mus_name, mus_bytes = import_state['music_zip']
                    dest = table_dir / 'music'
                    ensure_dir(dest)
                    await run.io_bound(lambda: zipfile.ZipFile(io.BytesIO(mus_bytes)).extractall(dest))

                # Create metadata and download media
                with client:
                    import_loading_label.set_text('Creating metadata and downloading media...')
                await run.io_bound(associate_vps_to_folder, table_dir, vps_entry, True)

                # Rebuild metadata (same as "Rebuild Meta" button in table detail)
                table_dir_name = table_dir.name
                with client:
                    import_loading_label.set_text('Rebuilding metadata...')
                await run.io_bound(
                    table_service.build_metadata,
                    downloadMedia=True,
                    updateAll=True,
                    tableName=table_dir_name,
                )

                # Invalidate media cache
                invalidate_media_cache()

                with client:
                    ui.notify(f'Table imported successfully: {folder_name}', type='positive')
                dlg.close()

                # Refresh table list
                if callable(perform_scan_cb):
                    await perform_scan_cb(silent=True)

            except Exception as ex:
                logger.exception('Table import failed')
                with client:
                    ui.notify(f'Import failed: {ex}', type='negative')
                    import_loading_overlay.style(add='display: none;', remove='display: flex;')
                    do_import_btn.enable()
            finally:
                import_state['busy'] = False

        do_import_btn.on_click(lambda: asyncio.create_task(do_import()))

    dlg.open()
