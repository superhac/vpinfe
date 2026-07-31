"""Converting the library's .info files, and putting them back.

Tables convert one at a time as they are used, so a library is normally a mix of shapes
and the user has no way to see which is which. The banner here is the only place that
answers "is my library converted yet", and it removes itself once the answer is yes.

Both operations are all-or-nothing across the library: the user did not choose which
tables converted - their play habits did - so they cannot be asked to choose which ones
come back.
"""

from __future__ import annotations

import asyncio
import logging
from queue import Queue

from nicegui import run, ui

from managerui.services import table_service
from managerui.ui_helpers import dialog_card

logger = logging.getLogger("vpinfe.manager.info_maintenance")

_ACCENT = ('color: var(--neon-cyan) !important; background: var(--surface) !important; '
           'border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;')
_MUTED = ('color: var(--ink-muted) !important; background: var(--surface) !important; '
          'border: 1px solid var(--line); border-radius: 18px; padding: 4px 10px;')

CONVERT_INTRO = (
    "Converts every table's .info file to the format this version uses. Your ratings, "
    "favourites, tags and play counts come across unchanged, and the file being replaced "
    "is saved beside it so this can be undone."
)

CONVERT_DETAIL = (
    "Nothing is re-read from your .vpx files and nothing is downloaded - this is a format "
    "change only, so it is much quicker than a table scan."
)

RESTORE_INTRO = (
    "Puts back the .info file saved before each table was converted. Ratings, favourites, "
    "tags and play counts go back to what that older version recorded. Your current file "
    "is saved first, so this can be undone too."
)

RESTORE_DETAIL = (
    "This version converts tables again as you use them, so restore if you are about to "
    "go back to an older VPinFE."
)


def _counts(reload: bool = False) -> dict:
    try:
        return table_service.info_maintenance_counts(reload=reload)
    except Exception:
        logger.exception("Could not read info maintenance counts")
        return {"pending_convert": 0, "restorable": 0}


def _run_dialog(title: str, intro: str, detail: str, confirm_label: str, action,
                table_names=None, on_done=None) -> None:
    """One progress dialog for both operations: explain, confirm, then report.

    Modelled on the metadata build dialog so a long library operation looks the same
    wherever it was started.
    """
    dlg = ui.dialog().props('persistent max-width=700px')
    state = {'running': False, 'lines': [], 'progress_q': Queue(), 'log_q': Queue()}

    with dlg, dialog_card("650px"):
        ui.label(title).classes('text-xl font-bold').style('color: var(--ink);')
        ui.separator()

        intro_container = ui.column().classes('gap-3 q-my-md w-full')
        with intro_container:
            ui.label(intro).classes('text-sm').style('color: var(--ink);')
            ui.label(detail).classes('text-xs').style('color: var(--ink-muted);')
            if table_names:
                with ui.expansion(f'Show the {len(table_names)} tables').classes('w-full'):
                    with ui.column().classes('w-full p-2').style(
                            'max-height: 14rem; overflow: auto;'):
                        for name in table_names:
                            ui.label(name).classes('text-xs').style('color: var(--ink-muted);')

        progress_container = ui.column().classes('w-full gap-2')
        progress_container.visible = False
        with progress_container:
            progressbar = ui.linear_progress(value=0.0, show_value=False).classes('w-full')
            status_label = ui.label("Preparing...").classes("text-sm").style('color: var(--ink);')
            log_container = ui.column().classes("w-full p-3 overflow-auto").style(
                "max-height: 250px; font-family: monospace; font-size: 11px; "
                "color: var(--ink); background: var(--surface); "
                "border: 1px solid var(--neon-purple); border-radius: var(--radius);")

        with ui.row().classes('justify-end gap-2 q-mt-md w-full'):
            cancel_btn = ui.button('Cancel', on_click=dlg.close).style(_MUTED)
            start_btn = ui.button(confirm_label, icon='check').style(_ACCENT)
            close_btn = ui.button('Close', on_click=dlg.close).style(_MUTED)
            close_btn.visible = False

        def pump():
            updated = False
            while not state['progress_q'].empty():
                updated = True
                current, total, message = state['progress_q'].get_nowait()
                if total:
                    progressbar.value = max(0.0, min(1.0, current / total))
                    status_label.text = f'{message} — {current}/{total}'
                else:
                    status_label.text = message or ''
            while not state['log_q'].empty():
                state['lines'].append(state['log_q'].get_nowait())
                if len(state['lines']) > 100:
                    state['lines'].pop(0)
                updated = True
            if updated:
                log_container.clear()
                with log_container:
                    for line in state['lines']:
                        ui.label(line).classes("text-xs whitespace-pre-wrap").style(
                            'color: var(--ink);')

        timer = ui.timer(0.1, pump, active=False)

        async def go():
            if state['running']:
                return
            state['running'] = True
            intro_container.visible = False
            progress_container.visible = True
            start_btn.visible = False
            cancel_btn.visible = False
            timer.active = True
            try:
                await run.io_bound(
                    action,
                    progress_cb=lambda c, t, m: state['progress_q'].put((c, t, m)),
                    log_cb=state['log_q'].put,
                )
                progressbar.value = 1.0
                status_label.text = "Finished"
            except Exception as exc:
                logger.exception("%s failed", title)
                status_label.text = "Stopped"
                state['log_q'].put(f"Stopped before finishing: {exc}")
            finally:
                pump()
                timer.active = False
                close_btn.visible = True
                state['running'] = False
                if on_done:
                    on_done()

        start_btn.on_click(lambda: asyncio.create_task(go()))

    dlg.open()


def open_convert_dialog(on_done=None) -> None:
    _run_dialog(
        title='Convert table info',
        intro=CONVERT_INTRO,
        detail=CONVERT_DETAIL,
        confirm_label='Convert all',
        action=table_service.convert_info,
        on_done=on_done,
    )


def open_restore_dialog(on_done=None) -> None:
    try:
        names = table_service.restorable_table_names()
    except Exception:
        logger.exception("Could not list tables with a saved .info")
        names = []

    if not names:
        ui.notify("No table has an older .info saved, so there is nothing to put back.",
                  type='info')
        return

    _run_dialog(
        title='Restore table info',
        intro=RESTORE_INTRO,
        detail=RESTORE_DETAIL,
        confirm_label='Restore all',
        action=table_service.restore_info,
        table_names=names,
        on_done=on_done,
    )


def render_convert_banner(on_done=None) -> None:
    """Offer a one-pass conversion while any table still needs one.

    Deliberately phrased as an offer rather than a warning: the lazy path is working as
    designed and nothing is wrong. It stops rendering for good once the count is zero,
    which is what makes it an answer rather than a nag.
    """
    pending = _counts().get('pending_convert', 0)
    if not pending:
        return

    tables = "1 table" if pending == 1 else f"{pending} tables"
    with ui.card().classes('w-full mb-4').style(
            'background: var(--surface-soft); border: 1px solid var(--line);'):
        with ui.row().classes('w-full items-center justify-between gap-4 p-3 flex-wrap'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('info', size='20px').style('color: var(--neon-cyan);')
                with ui.column().classes('gap-1'):
                    ui.label('Your tables convert to the new info format as you use them.'
                             ).classes('text-sm').style('color: var(--ink);')
                    ui.label(f'{tables} still to go — convert them all now if you would '
                             'rather do it in one pass.').classes('text-xs').style(
                        'color: var(--ink-muted);')
            ui.button('Convert all', icon='check',
                      on_click=lambda: open_convert_dialog(on_done)).style(_ACCENT)


def maintenance_menu(on_done=None) -> None:
    """Both operations, in the same place in every build so a downgrade keeps them there."""
    with ui.button(icon='build_circle').props('flat').tooltip('Table info maintenance'):
        with ui.menu():
            ui.menu_item('Convert table info', lambda: open_convert_dialog(on_done))
            ui.menu_item('Restore table info', lambda: open_restore_dialog(on_done))
