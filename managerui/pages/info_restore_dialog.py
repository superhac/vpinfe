"""Offering to put back .info files that a newer VPinFE converted.

Somebody who lands here has usually just gone back to this version because a newer one
did not work out for them. Requiring them to know this feature exists is requiring the
wrong thing at the worst moment, so the banner looks for the situation and offers the fix
without being asked. It renders only when there is something to put back, which for
anyone who never ran a newer VPinFE is never.

All or nothing across the library: conversion happened per table as tables were used, so
the user never chose which ones converted and cannot be asked to choose which come back.
The list is there to answer "what will this touch", not to be picked from.
"""

from __future__ import annotations

import asyncio
import logging
from queue import Queue

from nicegui import run, ui

from managerui.services import table_service
from managerui.ui_helpers import dialog_card

logger = logging.getLogger("vpinfe.manager.info_restore")

_ACCENT = ('color: var(--neon-cyan) !important; background: var(--surface) !important; '
           'border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;')
_MUTED = ('color: var(--ink-muted) !important; background: var(--surface) !important; '
          'border: 1px solid var(--line); border-radius: 18px; padding: 4px 10px;')

INTRO = (
    "Puts back the .info file each table had before a newer VPinFE converted it. Your "
    "ratings, favourites, tags and play counts go back to what this version recorded."
)

DETAIL = (
    "The file being replaced is saved alongside it first, so this can be undone. Tables "
    "that were never converted are left exactly as they are."
)


def _restorable_names():
    try:
        return table_service.restorable_table_names()
    except Exception:
        logger.exception("Could not list tables with a saved .info")
        return []


def open_restore_dialog(on_done=None) -> None:
    names = _restorable_names()
    if not names:
        ui.notify("No table has an older .info saved, so there is nothing to put back.",
                  type='info')
        return

    dlg = ui.dialog().props('persistent max-width=700px')
    state = {'running': False, 'lines': [], 'progress_q': Queue(), 'log_q': Queue()}

    with dlg, dialog_card("650px"):
        ui.label('Restore table info').classes('text-xl font-bold').style('color: var(--ink);')
        ui.separator()

        intro_container = ui.column().classes('gap-3 q-my-md w-full')
        with intro_container:
            ui.label(INTRO).classes('text-sm').style('color: var(--ink);')
            ui.label(DETAIL).classes('text-xs').style('color: var(--ink-muted);')
            with ui.expansion(f'Show the {len(names)} tables').classes('w-full'):
                with ui.column().classes('w-full p-2').style(
                        'max-height: 14rem; overflow: auto;'):
                    for name in names:
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
            start_btn = ui.button('Restore all', icon='history').style(_ACCENT)
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
                    table_service.restore_info,
                    progress_cb=lambda c, t, m: state['progress_q'].put((c, t, m)),
                    log_cb=state['log_q'].put,
                )
                progressbar.value = 1.0
                status_label.text = "Finished"
            except Exception as exc:
                logger.exception("Restore failed")
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


def render_restore_banner(on_done=None) -> None:
    """Say something only when a newer VPinFE has been here."""
    names = _restorable_names()
    if not names:
        return

    tables = "1 table has" if len(names) == 1 else f"{len(names)} tables have"
    with ui.card().classes('w-full mb-4').style(
            'background: var(--surface-soft); border: 1px solid var(--line);'):
        with ui.row().classes('w-full items-center justify-between gap-4 p-3 flex-wrap'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('history', size='20px').style('color: var(--neon-cyan);')
                with ui.column().classes('gap-1'):
                    ui.label(f'{tables} info saved by a newer VPinFE.').classes(
                        'text-sm').style('color: var(--ink);')
                    ui.label('Restore to put back the version this release can read. Your '
                             'current info is saved first.').classes('text-xs').style(
                        'color: var(--ink-muted);')
            ui.button('Restore', icon='history',
                      on_click=lambda: open_restore_dialog(on_done)).style(_ACCENT)
