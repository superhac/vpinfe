"""Upgrading the library's .info files, and putting them back.

A library upgrades all at once at first launch, so a table still on the old format means
that did not finish. See INFO-SCHEMA.local.md §5b.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from queue import Queue

from nicegui import run, ui

from managerui.services import game_service, ui_state
from managerui.ui_helpers import dialog_card

logger = logging.getLogger("vpinfe.manager.info_maintenance")

_ACCENT = ('color: var(--neon-cyan) !important; background: var(--surface) !important; '
           'border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;')
_MUTED = ('color: var(--ink-muted) !important; background: var(--surface) !important; '
          'border: 1px solid var(--line); border-radius: 18px; padding: 4px 10px;')

UPGRADE_INTRO = (
    "Upgrades the .info files that were missed. Ratings, favorites, tags and play "
    "counts carry over unchanged, and each file is backed up first."
)

UPGRADE_DETAIL = (
    "A format change only - nothing is re-read from your .vpx files and nothing is "
    "downloaded."
)

RESTORE_INTRO = (
    "Puts your ratings, favorites, tags, play counts and collections back to how they "
    "were{when}. Your current files are backed up first."
)

RESTORE_DETAIL = (
    "Only worth doing if you are going back to an older VPinFE - this version upgrades "
    "them again on the next start."
)


def _refresh_banners() -> None:
    """Re-render the strips after an operation, so the one that prompted it goes away."""
    try:
        render_info_banners.refresh()
    except Exception:
        logger.debug("Banner refresh skipped", exc_info=True)


def _subject(count: int, collections: bool) -> str:
    """What was upgraded, named the way the user would name it."""
    if count and collections:
        return f"{_files(count)} and your collections"
    if collections:
        return "your collections"
    return _files(count)


def _collections_restorable() -> bool:
    try:
        return game_service.collections_restorable()
    except Exception:
        logger.exception("Could not check for a saved collections file")
        return False


def _games(n: int) -> str:
    return "1 table" if n == 1 else f"{n} tables"


def _files(n: int) -> str:
    return "1 .info file" if n == 1 else f"{n} .info files"


def _backup_date(stamp: str) -> str:
    # No %-d: not portable to Windows.
    try:
        parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    except (TypeError, ValueError):
        return ""
    return parsed.strftime("%d %B %Y").lstrip("0")


def _counts(reload: bool = False) -> dict:
    try:
        return game_service.info_maintenance_counts(reload=reload)
    except Exception:
        logger.exception("Could not read info maintenance counts")
        return {"pending_upgrade": 0, "restorable": 0, "newer_than_us": 0}


def _run_dialog(title: str, intro: str, detail: str, confirm_label: str, action,
                game_names=None, on_done=None) -> None:
    """Explain, confirm, report - shaped like the metadata build dialog."""
    dlg = ui.dialog().props('persistent max-width=700px')
    state = {'running': False, 'lines': [], 'progress_q': Queue(), 'log_q': Queue()}

    with dlg, dialog_card("650px"):
        ui.label(title).classes('text-xl font-bold').style('color: var(--ink);')
        ui.separator()

        intro_container = ui.column().classes('gap-3 q-my-md w-full')
        with intro_container:
            ui.label(intro).classes('text-sm').style('color: var(--ink);')
            ui.label(detail).classes('text-xs').style('color: var(--ink-muted);')
            if game_names:
                with ui.expansion(f'Show the {len(game_names)} tables').classes('w-full'):
                    with ui.column().classes('w-full p-2').style(
                            'max-height: 14rem; overflow: auto;'):
                        for name in game_names:
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
                _refresh_banners()

        start_btn.on_click(lambda: asyncio.create_task(go()))

    dlg.open()


def open_upgrade_dialog(on_done=None) -> None:
    try:
        names = game_service.pending_upgrade_game_names()
    except Exception:
        logger.exception("Could not list the .info files still to upgrade")
        names = []

    if not names:
        ui.notify("Every .info file is already on the current format.", type='info')
        return

    _run_dialog(
        title='Upgrade .info files',
        intro=UPGRADE_INTRO,
        detail=UPGRADE_DETAIL,
        confirm_label='Upgrade all',
        action=game_service.upgrade_info,
        game_names=names,
        on_done=on_done,
    )


def open_restore_dialog(on_done=None) -> None:
    try:
        names = game_service.restorable_game_names()
    except Exception:
        logger.exception("Could not list tables with a saved .info")
        names = []

    collections = _collections_restorable()
    if not names and not collections:
        ui.notify("There are no backups to restore.", type='info')
        return

    date = _backup_date(game_service.newest_backup_stamp())
    _run_dialog(
        title='Restore backups',
        intro=RESTORE_INTRO.format(when=f" on {date}" if date else " before the upgrade"),
        detail=RESTORE_DETAIL,
        confirm_label='Restore all',
        action=game_service.restore_info,
        game_names=names,
        on_done=on_done,
    )


UPGRADED_NOTICE_SEEN = "info_upgrade_notice_seen"


def _strip(icon: str, color: str, headline: str, detail: str, actions) -> None:
    # grow/min-w-0 and flex-nowrap together: without them a long detail line pushes the
    # icon onto a line of its own.
    with ui.card().classes('w-full mb-3').style(
            f'background: var(--surface-soft); border: 1px solid {color};'):
        with ui.row().classes('w-full items-center gap-4 px-4 py-3 flex-wrap md:flex-nowrap'):
            ui.icon(icon, size='24px').classes('shrink-0').style(f'color: {color};')
            with ui.column().classes('gap-1 grow min-w-0'):
                ui.label(headline).classes('text-sm font-medium').style('color: var(--ink);')
                ui.label(detail).classes('text-xs').style('color: var(--ink-muted);')
            with ui.row().classes('gap-2 items-center shrink-0'):
                actions()


@ui.refreshable
def render_info_banners(on_done=None) -> None:
    """A table the scan could not read, tables the upgrade missed, then news that it ran."""
    _render_unreadable_warning()
    counts = _counts()
    if counts.get('newer_than_us', 0):
        _render_newer_warning(counts['newer_than_us'])
    elif counts.get('pending_upgrade', 0):
        _render_not_upgraded_warning(counts['pending_upgrade'], on_done)
    elif counts.get('restorable', 0):
        _render_upgraded_notice(counts['restorable'])


def _render_unreadable_warning() -> None:
    """Not dismissible: the table is missing from the frontend until somebody deals with it."""
    try:
        broken = game_service.unreadable_games()
    except Exception:
        logger.exception("Could not read the unreadable-table list")
        return
    if not broken:
        return

    names = ", ".join(row.get("folder", "?") for row in broken[:3])
    if len(broken) > 3:
        names += f" and {len(broken) - 3} more"
    games = "1 table is" if len(broken) == 1 else f"{len(broken)} tables are"
    _strip(
        'warning', 'var(--neon-pink)',
        f'{games} missing because the .info file could not be read.',
        f'{names}. The files were left untouched — a backup may hold a working copy.',
        lambda: ui.button('Restore backups', icon='history',
                          on_click=lambda: open_restore_dialog()).style(_ACCENT),
    )


def _render_newer_warning(newer: int) -> None:
    """A newer VPinFE has been here, so this build is reading a shape it does not know.

    Takes priority over the upgraded notice: claiming "I upgraded these" when something
    newer did is the one message that is actively wrong.
    """
    _strip(
        'history', 'var(--neon-pink)',
        f'A newer VPinFE upgraded {_subject(newer, _collections_restorable())}.',
        'This version can only read part of them, so some details may be missing. Restore '
        'puts your ratings, favorites, tags and play counts back to how this version '
        'recorded them.',
        lambda: ui.button('Restore backups', icon='history',
                          on_click=lambda: open_restore_dialog()).style(_ACCENT),
    )


def _render_not_upgraded_warning(pending: int, on_done) -> None:
    """Reported as a problem, not offered as a choice - nobody opts into the upgrade."""
    _strip(
        'warning', 'var(--neon-pink)',
        f'{_files(pending)} are still on the old format.',
        'Probably an interrupted start, or files that could not be written. Their '
        'details may be incomplete until this is fixed.',
        lambda: ui.button('Upgrade them', icon='check',
                          on_click=lambda: open_upgrade_dialog(on_done)).style(_ACCENT),
    )



def _render_upgraded_notice(restorable: int) -> None:
    """The first chance the user has to learn their files changed shape.

    Do not promise "you can downgrade": the backups are invisible to a release older than
    the one that learned to restore.
    """
    if ui_state.get(UPGRADED_NOTICE_SEEN):
        return


    def actions():
        def acknowledge():
            ui_state.set(UPGRADED_NOTICE_SEEN, True)
            _refresh_banners()

        ui.button('Restore backups', icon='history',
                  on_click=lambda: open_restore_dialog()).style(_MUTED)
        ui.button('Got it', on_click=acknowledge).style(_ACCENT)

    _strip(
        'check_circle', 'var(--neon-cyan)',
        'Your .info files were upgraded for this version.',
        f'Nothing was lost — a backup of all {restorable} was saved first. Undo it from '
        f'Maintenance at any time.',
        actions,
    )


def maintenance_menu(on_done=None) -> None:
    """Labelled, because once the notice is dismissed this is the only route to a restore."""
    pending = _counts().get('pending_upgrade', 0)
    with ui.button("MAINTENANCE", icon="build").props("outline color=info").style(
            'border-radius: 0;'):
        with ui.menu():
            ui.menu_item('Restore backups', lambda: open_restore_dialog(on_done))
            if pending:
                ui.menu_item('Upgrade .info files', lambda: open_upgrade_dialog(on_done))
