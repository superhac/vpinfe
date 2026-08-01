from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

from nicegui import events, run, ui

from managerui.pages.game_dialog_context import GameDialogContext, default_context
from managerui.services import game_service
from managerui.ui_helpers import debounced_input

logger = logging.getLogger("vpinfe.manager.games")
_missing_games_dialog: Optional[ui.dialog] = None

associate_vps_to_folder = game_service.associate_vps_to_folder
search_vpsdb = game_service.search_vpsdb


def scan_missing_games():
    return game_service.scan_missing_game_rows(reload=True)


def open_missing_games_dialog(
    missing_rows: list[dict],
    on_close: Optional[Callable[[], None]] = None,
    context: GameDialogContext | None = None,
):
    context = context or default_context()
    on_close = on_close or context.refresh_missing
    return _render_missing_games_dialog(missing_rows, on_close=on_close)


def open_match_vps_dialog(
    missing_row: dict,
    refresh_missing: Optional[Callable[[], None]] = None,
    refresh_installed: Optional[Callable[[], None]] = None,
    context: GameDialogContext | None = None,
):
    context = context or default_context()
    refresh_missing = refresh_missing or context.refresh_missing
    refresh_installed = refresh_installed or context.refresh_games
    return _render_match_vps_dialog(
        missing_row,
        refresh_missing=refresh_missing,
        refresh_installed=refresh_installed,
    )


def _render_missing_games_dialog(missing_rows: list[dict], on_close: Optional[Callable[[], None]] = None):
    global _missing_games_dialog
    # Close any previous dialog to avoid stacking
    try:
        if _missing_games_dialog:
            _missing_games_dialog.close()
    except Exception:
        pass
    dlg = ui.dialog().props('max-width=1080px')
    _missing_games_dialog = dlg
    with dlg, ui.card().classes('w-[960px] max-w-[95vw]'):
        title = ui.label(f'Missing Tables ({len(missing_rows)})').classes('text-lg font-bold')
        ui.separator()

        container = ui.column().classes('w-full')

        def render(items: list[dict]):
            container.clear()
            title.set_text(f'Missing Tables ({len(items)})')
            if not items:
                with container:
                    ui.label('No tables without .info metadata.').classes('q-my-md')
                return
            for r in items:
                with container, ui.row().classes('justify-between items-center w-full q-py-xs border-b'):
                    ui.label(r['folder']).classes('font-medium')
                    ui.button(
                        'Match VPS ID',
                        on_click=lambda rr=r: open_match_vps_dialog(
                            rr,
                            refresh_missing=lambda: (ui.notify('Missing list updated', type='info'), render(scan_missing_games())),
                            refresh_installed=None,
                        )
                    ).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink) !important; border-radius: 18px; padding: 4px 10px;')

        render(missing_rows)

        with ui.row().classes('justify-end q-mt-md'):
            def _close():
                dlg.close()
                # clear global ref so a new one can be created next time
                global _missing_games_dialog
                _missing_games_dialog = None
                if callable(on_close):
                    on_close()
            ui.button('Close', on_click=_close).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink) !important; border-radius: 18px; padding: 4px 10px;')
    dlg.open()


def _render_match_vps_dialog(
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
            ui.icon('info', size='sm').style('color: var(--neon-purple);')
            ui.label(
                'Clicking "Associate" will: optionally rename the folder to "TABLE NAME (MANUFACTURER YEAR)" format, '
                'create a `.info` metadata file, and download media images from vpinmediadb.'
            ).classes('text-sm').style('color: var(--ink-muted);')
        rename_folder_switch = ui.switch('Rename folder to VPS format', value=True)
        rename_folder_switch.props('dense')
        ui.label('Disable to keep the current folder name.').classes('text-xs').style('color: var(--ink-muted);')

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
                    ui.label('Search by Table Name').classes('text-sm').style('color: var(--ink-muted);')
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
                            loading_label.set_text('Preparing association...')

                            try:
                                old_path = Path(missing_row['path'])
                                folder_path = old_path
                                if rename_folder_switch.value:
                                    loading_label.set_text('Renaming folder...')
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

                                # Update loading message and run association in background
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

                        ui.button('Associate', on_click=_on_assoc).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink) !important; border-radius: 18px; padding: 4px 10px;')

        # Pre-fill the search with folder name for convenience
        initial_term = missing_row['folder']
        search_input = debounced_input(ui.input('Search VPS…', value=initial_term)).classes('w-full')

        def on_search_change(e: events.ValueChangeEventArguments):
            term = e.value or ''
            render_results(search_vpsdb(term, limit=80))

        search_input.on_value_change(on_search_change)

        # Render initial results:
        render_results(search_vpsdb(initial_term, limit=80))

        with ui.row().classes('justify-end q-mt-md'):
            ui.button('Close', on_click=dlg.close).style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple) !important; border-radius: 18px; padding: 4px 10px;')
    dlg.open()
