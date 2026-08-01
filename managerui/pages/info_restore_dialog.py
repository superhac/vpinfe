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
from datetime import datetime
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
    "Puts your ratings, favourites, tags and play counts back to how they were{when}. "
    "Your current .info files are backed up first."
)

DETAIL = (
    "Tables a newer VPinFE never touched are left exactly as they are."
)


def _files(n):
    return "1 .info file" if n == 1 else f"{n} .info files"


def _backup_date(stamp):
    """A backup timestamp as a plain date, or "" if it cannot be read.

    Built without %-d, which is not portable to Windows.
    """
    try:
        parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    except (TypeError, ValueError):
        return ""
    return parsed.strftime("%d %B %Y").lstrip("0")


def _strip(icon, colour, headline, detail, actions):
    """One row: icon, text, actions.

    The text column needs `grow min-w-0` and the row `flex-nowrap`, or a long detail line
    grows past the available width and pushes the icon onto a line of its own.
    """
    with ui.card().classes('w-full mb-3').style(
            f'background: var(--surface-soft); border: 1px solid {colour};'):
        with ui.row().classes('w-full items-center gap-4 px-4 py-3 flex-wrap md:flex-nowrap'):
            ui.icon(icon, size='24px').classes('shrink-0').style(f'color: {colour};')
            with ui.column().classes('gap-1 grow min-w-0'):
                ui.label(headline).classes('text-sm font-medium').style('color: var(--ink);')
                ui.label(detail).classes('text-xs').style('color: var(--ink-muted);')
            with ui.row().classes('gap-2 items-center shrink-0'):
                actions()


def _refresh_banners():
    """Re-render the strips after a restore, so the one that prompted it goes away."""
    try:
        render_restore_banner.refresh()
    except Exception:
        logger.debug("Banner refresh skipped", exc_info=True)


def _when():
    date = _backup_date(table_service.newest_backup_stamp())
    return f" on {date}" if date else " before the upgrade"


def _restorable_names():
    try:
        return table_service.restorable_table_names()
    except Exception:
        logger.exception("Could not list tables with a saved .info")
        return []


def open_restore_dialog(on_done=None) -> None:
    names = _restorable_names()
    if not names:
        ui.notify("There are no backups to restore.", type='info')
        return

    dlg = ui.dialog().props('persistent max-width=700px')
    state = {'running': False, 'lines': [], 'progress_q': Queue(), 'log_q': Queue()}

    with dlg, dialog_card("650px"):
        ui.label('Restore backups').classes('text-xl font-bold').style('color: var(--ink);')
        ui.separator()

        intro_container = ui.column().classes('gap-3 q-my-md w-full')
        with intro_container:
            ui.label(INTRO.format(when=_when())).classes('text-sm').style('color: var(--ink);')
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
                _refresh_banners()

        start_btn.on_click(lambda: asyncio.create_task(go()))

    dlg.open()


@ui.refreshable
def render_restore_banner(on_done=None) -> None:
    """Say something only when a newer VPinFE has been here."""
    _render_unreadable_warning()
    names = _restorable_names()
    if not names:
        return

    _strip(
        'history', 'var(--neon-cyan)',
        f'A newer VPinFE upgraded {_files(len(names))}.',
        'Restore puts your ratings, favourites, tags and play counts back to how this '
        'version recorded them, and backs up the current files first.',
        lambda: ui.button('Restore backups', icon='history',
                          on_click=lambda: open_restore_dialog(on_done)).style(_ACCENT),
    )


def _render_unreadable_warning() -> None:
    """Not dismissible: the table is missing from the frontend until somebody deals with it."""
    try:
        broken = table_service.unreadable_tables()
    except Exception:
        logger.exception("Could not read the unreadable-table list")
        return
    if not broken:
        return

    shown = ", ".join(row.get("folder", "?") for row in broken[:3])
    if len(broken) > 3:
        shown += f" and {len(broken) - 3} more"
    tables = "1 table is" if len(broken) == 1 else f"{len(broken)} tables are"
    _strip(
        'warning', 'var(--neon-pink)',
        f'{tables} missing because the .info file could not be read.',
        f'{shown}. The files were left untouched — a backup may hold a working copy.',
        lambda: ui.button('Restore backups', icon='history',
                          on_click=lambda: open_restore_dialog()).style(_ACCENT),
    )
