from __future__ import annotations
import logging
from nicegui import ui, app, context
from fastapi.responses import JSONResponse
from .pages import tables as tab_tables
from .pages import vpinfe_config as tab_vpinfe
from .pages import vpx_config as tab_vpx_config
from .pages import collections as tab_collections
from .pages import media as tab_media
from .pages import themes as tab_themes
from .pages import system as tab_system
from .pages import mobile as tab_mobile
from .pages import vpinplay as tab_vpinplay
from .pages import vpinplay_player as tab_vpinplay_player
from .pages import logs as tab_logs
from .page_registry import NAV_PAGES, PAGE_ALIASES
from .services import app_control
from .services.archive_service import cleanup_archive, create_vpxz_archive
from .ui_helpers import load_manager_styles, nav_button
import asyncio
import threading
import os
import socket
import time
from common.app_version import get_version
from common.app_updater import (
    check_for_updates as check_for_app_updates,
    launch_prepared_update,
    prepare_update,
    CONFIG_DIR as UPDATER_CONFIG_DIR,
)

logger = logging.getLogger("vpinfe.manager.ui")

# Shutdown event — set by _quit_app() to unblock headless mode
import threading as _threading
_shutdown_event = _threading.Event()

# First-run flag — set by main.py when no vpinfe.ini existed
_first_run = False

def set_first_run(value: bool = True):
    global _first_run
    _first_run = value

# Shared state for remote launch notifications
_remote_launch_state = {
    'launching': False,
    'table_name': None,
}

# Cache for release check result (check once per session)
_update_check_cache = {
    'checked': False,
    'update_available': False,
    'error': None,
    'current_version': get_version(),
    'latest_version': None,
    'update_supported': False,
    'support_reason': None,
    'asset_name': None,
}
_update_action_state = {
    'busy': False,
}


def _force_exit_after_update(delay_seconds: int = 8) -> None:
    """Ensure the old process does not linger after handing off to the updater."""
    def _worker():
        time.sleep(delay_seconds)
        logger.warning("Forcing process exit after update handoff; graceful shutdown did not complete in %ss", delay_seconds)
        os._exit(0)

    threading.Thread(target=_worker, daemon=True, name="update-force-exit").start()

def check_for_updates() -> dict:
    global _update_check_cache

    if _update_check_cache['checked']:
        logger.info(
            "Returning cached update check result: current=%s latest=%s available=%s error=%s supported=%s support_reason=%s asset=%s",
            _update_check_cache.get('current_version'),
            _update_check_cache.get('latest_version'),
            _update_check_cache.get('update_available'),
            _update_check_cache.get('error'),
            _update_check_cache.get('update_supported'),
            _update_check_cache.get('support_reason'),
            _update_check_cache.get('asset_name'),
        )
        return _update_check_cache

    logger.info("Running initial header update check for current_version=%s", get_version())
    _update_check_cache.update(check_for_app_updates())
    _update_check_cache['checked'] = True
    logger.info(
        "Initial header update check complete: current=%s latest=%s available=%s error=%s supported=%s support_reason=%s asset=%s",
        _update_check_cache.get('current_version'),
        _update_check_cache.get('latest_version'),
        _update_check_cache.get('update_available'),
        _update_check_cache.get('error'),
        _update_check_cache.get('update_supported'),
        _update_check_cache.get('support_reason'),
        _update_check_cache.get('asset_name'),
    )
    return _update_check_cache


_PAGE_RENDERERS = {
    'tables': tab_tables.render_panel,
    'collections': tab_collections.render_panel,
    'media': tab_media.render_panel,
    'themes': tab_themes.render_panel,
    'mobile': lambda: tab_mobile.build(standalone=False),
    'system': tab_system.render_panel,
    'logs': tab_logs.render_panel,
    'vpinfe': tab_vpinfe.render_panel,
    'vpinplay': tab_vpinplay.render_panel,
    'vpinplay_player': tab_vpinplay_player.render_panel,
    'vpx_config': tab_vpx_config.render_panel,
}


def header():
    # Enable dark mode by default
    ui.dark_mode(value=True)
    with ui.header().classes('items-center justify-between').style(
        'background: var(--header-gradient); '
        'box-shadow: var(--shadow);'
    ):
        with ui.row().classes('gap-3 items-center'):
            ui.image('/static/img/vpinfe-logo.png').classes('manager-header-logo')
            ui.label('VPinFE Manager').classes('text-xl manager-title')
            ui.button(icon='restart_alt', on_click=lambda: app_control.restart_app()) \
                .props('flat round dense').classes('text-green-400') \
                .tooltip('Restart VPinFE')
            ui.button(icon='power_settings_new', on_click=lambda: app_control.quit_app()) \
                .props('flat round dense').classes('text-red-400') \
                .tooltip('Quit VPinFE')

        # Version + release status (right side of header)
        update_container = ui.row().classes('gap-2 items-center')
        with update_container:
            page_client = context.client
            current_version = get_version()
            ui.icon('sell', size='18px').style('color: var(--ink-muted);')
            ui.label(f'Version: {current_version}').classes('text-sm').style('color: var(--ink-muted); font-weight: 500;')

            async def run_update_install():
                from nicegui import run
                if _update_action_state['busy']:
                    with page_client:
                        ui.notify('An update is already in progress', type='warning')
                    return

                _update_action_state['busy'] = True
                try:
                    with page_client:
                        ui.notify('Downloading update package...', type='info')
                    prepared = await run.io_bound(prepare_update)
                    await run.io_bound(lambda: launch_prepared_update(prepared))
                    with page_client:
                        ui.notify('Update staged. Restarting VPinFE...', type='positive')
                        _force_exit_after_update()
                        app_control.quit_app()
                except Exception as e:
                    with page_client:
                        ui.notify(f'Update failed: {e}', type='negative')
                finally:
                    _update_action_state['busy'] = False

            def show_update_dialog(result: dict):
                with ui.dialog() as dialog, ui.card().classes('p-6 w-[28rem]').style('background: var(--bg); border: 1px solid var(--neon-purple); box-shadow: var(--glow-purple);'):
                    ui.label(f"Update to {result.get('latest_version', 'latest')}?").classes('text-lg font-bold').style('color: var(--ink);')
                    ui.label(
                        'This will download the release package, close VPinFE, replace the install, and relaunch automatically.'
                    ).classes('text-sm mt-2').style('color: var(--ink-muted);')

                    with ui.row().classes('justify-end gap-2 mt-4 w-full'):
                        ui.button('Cancel', on_click=dialog.close).props('flat').style('color: var(--ink-muted);')
                        ui.button(
                            'Update Now',
                            icon='system_update_alt',
                            on_click=lambda: (dialog.close(), asyncio.create_task(run_update_install())),
                        ).props('unelevated color=amber')
                dialog.open()

            async def check_updates_async():
                from nicegui import run
                logger.info("Scheduling async header update check")
                result = await run.io_bound(check_for_updates)
                logger.info(
                    "Header update check UI render: current=%s latest=%s available=%s error=%s supported=%s support_reason=%s asset=%s",
                    result.get('current_version'),
                    result.get('latest_version'),
                    result.get('update_available'),
                    result.get('error'),
                    result.get('update_supported'),
                    result.get('support_reason'),
                    result.get('asset_name'),
                )
                with update_container:
                    if result.get('update_available'):
                        ui.icon('system_update', size='20px').classes('text-yellow-400')
                        if result.get('update_supported'):
                            ui.button(
                                f"Update Available ({result.get('latest_version', 'latest')})",
                                icon='download',
                                on_click=lambda r=result: show_update_dialog(r),
                            ).props('flat dense no-caps').classes(
                                'text-yellow-400 text-sm font-medium hover:text-yellow-300'
                            )
                        else:
                            ui.link(
                                f"Update Available ({result.get('latest_version', 'latest')})",
                                'https://github.com/superhac/vpinfe/releases/latest',
                                new_tab=True
                            ).classes('text-yellow-400 text-sm font-medium hover:text-yellow-300').style('text-decoration: none;')
                    elif result.get('error') is None:
                        ui.icon('check_circle', size='20px').classes('text-green-400')
                        ui.label('Up to date').classes('text-green-400 text-sm font-medium')
                    else:
                        ui.icon('info', size='18px').style('color: var(--ink-muted);')
                        ui.link(
                            f"Latest: {result.get('latest_version', 'unknown')}",
                            'https://github.com/superhac/vpinfe/releases/latest',
                            new_tab=True
                        ).classes('text-sm font-medium').style('text-decoration: none; ')

            ui.timer(0.5, check_updates_async, once=True)

def build_app():
    load_manager_styles()

    header()

    # Main content area - offset by nav panel width (create first so toggle_nav can reference it)
    content_container = ui.column().classes('p-6 manager-content nav-expanded')

    # Navigation panel container (fixed position on left side)
    nav_panel = ui.column().classes('fixed left-0 top-16 bottom-0 manager-nav-panel')

    # Track expanded/collapsed state and UI element references
    nav_state = {'expanded': True, 'nav_content': None, 'nav_label': None, 'remote_container': None}
    nav_buttons = {}

    def toggle_nav():
        nav_state['expanded'] = not nav_state['expanded']
        if nav_state['expanded']:
            nav_panel.classes(remove='nav-panel-collapsed')
            nav_state['nav_content'].classes(remove='nav-collapsed')
            nav_state['remote_container'].classes(remove='nav-collapsed')
            ui.query('body').classes(remove='nav-is-collapsed')
            nav_state['nav_label'].set_visibility(True)
            content_container.classes(add='nav-expanded', remove='nav-collapsed-content')
        else:
            nav_panel.classes(add='nav-panel-collapsed')
            nav_state['nav_content'].classes(add='nav-collapsed')
            nav_state['remote_container'].classes(add='nav-collapsed')
            ui.query('body').classes(add='nav-is-collapsed') 
            nav_state['nav_label'].set_visibility(False)
            content_container.classes(add='nav-collapsed-content', remove='nav-expanded')

    with nav_panel:
        # Navigation header with hamburger menu
        with ui.row().classes('w-full items-center gap-2 p-3 manager-nav-header'):
            ui.button(icon='menu', on_click=toggle_nav).props('flat round dense').classes('manager-nav-header-button')
            nav_state['nav_label'] = ui.label('Navigation').classes('text-lg font-bold manager-nav-label')

        # Navigation menu items
        nav_state['nav_content'] = ui.column().classes('w-full gap-1 mt-2')
        with nav_state['nav_content']:
            for page in NAV_PAGES:
                nav_buttons[page.key] = nav_button(
                    page.label,
                    page.icon,
                    on_click=lambda key=page.key: show_page(key),
                    tooltip=page.tooltip,
                )
        # Remote control button anchored to bottom
        nav_state['remote_container'] = ui.column().classes('w-full gap-1 mt-auto').style('margin-top: auto; padding-bottom: 16px;')
        with nav_state['remote_container']:
            ui.separator().style('background: var(--surface-2);')
            nav_button(
                'Remote Control',
                'settings_remote',
                on_click=lambda: ui.navigate.to('/remote', new_tab=True),
                tooltip='Remote',
            )

    current_page = {'value': None}

    def show_page(page_key: str, *, persist: bool = True):
        if persist:
            app.storage.user['active_page'] = page_key

        for key, button in nav_buttons.items():
            if key == page_key:
                button.classes(add='nav-btn-active')
            else:
                button.classes(remove='nav-btn-active')

        # Only re-render if page changed
        if current_page['value'] == page_key:
            return

        current_page['value'] = page_key
        content_container.clear()

        with content_container:
            render_page = _PAGE_RENDERERS.get(page_key)
            if render_page is not None:
                render_page()

    # Determine initial page: URL ?page= param takes priority, then first-run, then saved page
    global _first_run
    page_param = app.storage.user.get('_page_param')
    if page_param:
        del app.storage.user['_page_param']

    if _first_run:
        initial_page = 'vpinfe'
    elif page_param:
        initial_page = page_param
    else:
        initial_page = app.storage.user.get('active_page', 'tables')
    show_page(initial_page, persist=not bool(page_param))

    # Show dialog if requested via URL param, or first-run dialog
    dialog_param = app.storage.user.get('_dialog_param')
    if dialog_param:
        del app.storage.user['_dialog_param']

    if _first_run:
        _first_run = False  # Only show once
        _dialog_first_run()
    elif dialog_param:
        handler = _DIALOG_HANDLERS.get(dialog_param)
        if handler:
            handler()

def _dialog_test():
    """Test dialog triggered by ?dialog=test."""
    with ui.dialog() as dlg, ui.card():
        ui.label('Testing dialog').classes('text-lg font-bold')
        ui.button('Close', on_click=dlg.close)
    dlg.open()

def _dialog_first_run():
    """Welcome dialog shown on first run when no vpinfe.ini existed."""
    with ui.dialog() as dlg, ui.card().classes('p-6'):
        ui.icon('settings_suggest', size='48px').classes('text-blue-400 self-center')
        ui.label('Welcome to VPinFE!').classes('text-xl font-bold text-center')
        ui.label(
            'No configuration file was found so a default vpinfe.ini has been created. '
            'Please configure your settings below, then restart VPinFE.'
        ).classes('text-sm text-gray-300 text-center')
        ui.button('Got it', on_click=dlg.close).classes('self-center mt-2')
    dlg.open()

# Registry mapping dialog param values to handler functions.
# Add new entries here to support additional dialogs via ?dialog=<key>.
_DIALOG_HANDLERS = {
    'test': _dialog_test,
    'first_run': _dialog_first_run,
}

@ui.page('/')
def index(page: str = '', dialog: str = ''):
    if page:
        resolved = PAGE_ALIASES.get(page.lower())
        if resolved:
            app.storage.user['_page_param'] = resolved
    if dialog:
        key = dialog.lower()
        if key in _DIALOG_HANDLERS:
            app.storage.user['_dialog_param'] = key
    build_app()

@ui.page('/remote')
def remote_page():
    load_manager_styles()
    from .pages import remote
    remote.build()

@ui.page('/mobile')
def mobile_page():
    load_manager_styles()
    tab_mobile.build()


# API endpoint for remote launch state (polled by frontend themes)
@app.get('/api/remote-launch')
def get_remote_launch_state():
    """Returns current remote launch state for frontend to poll."""
    return JSONResponse(
        content=_remote_launch_state,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "*",
        }
    )


@app.get('/api/download-table-vpxz')
def download_table_vpxz(name: str):
    """Zip a table folder and serve it as a .vpxz download, then clean up."""
    from starlette.responses import FileResponse
    from starlette.background import BackgroundTask

    try:
        archive = create_vpxz_archive(name)
    except ValueError:
        return JSONResponse(content={"error": "Invalid table path"}, status_code=400)
    except FileNotFoundError:
        return JSONResponse(content={"error": "Table not found"}, status_code=404)

    logger.info("Created download archive: %s", archive.path)

    def cleanup():
        cleanup_archive(archive)
        logger.info("Cleaned up temp archive: %s", archive.temp_dir)

    return FileResponse(
        archive.path,
        media_type='application/octet-stream',
        filename=archive.filename,
        background=BackgroundTask(cleanup),
    )


def set_remote_launch_state(launching: bool, table_name: str = None):
    """Set the remote launch state (called by remote.py)."""
    global _remote_launch_state
    _remote_launch_state['launching'] = launching
    _remote_launch_state['table_name'] = table_name

# keep a reference to the running thread
_ui_thread = None

_ui_port = 8001


def _manager_ui_urls(port: int) -> list[str]:
    urls = [f"http://localhost:{port}"]
    seen = {"127.0.0.1", "0.0.0.0", "::1"}
    resolved_ips: list[str] = []
    resolve_error: list[Exception] = []

    def _resolve() -> None:
        try:
            hostname = socket.gethostname()
            for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, socket.AF_INET):
                if family != socket.AF_INET:
                    continue
                ip = sockaddr[0]
                if ip in seen:
                    continue
                resolved_ips.append(ip)
        except Exception as e:
            resolve_error.append(e)

    resolver = threading.Thread(target=_resolve, daemon=True, name="manager-ui-ip-resolver")
    resolver.start()
    resolver.join(timeout=1.0)

    if resolver.is_alive():
        logger.warning(
            "Timed out while enumerating Manager UI network addresses; "
            "continuing startup with localhost URL only."
        )
        return urls

    if resolve_error:
        logger.warning("Failed to enumerate Manager UI network addresses: %s", resolve_error[0])
        return urls

    for ip in resolved_ips:
        seen.add(ip)
        urls.append(f"http://{ip}:{port}")
    return urls

def _run_ui():
    STORAGE_SECRET = "verysecret" # The storage is just to keep the active tab between sessions. Nothing sensitive.
    nicegui_storage_dir = UPDATER_CONFIG_DIR / ".nicegui"
    nicegui_storage_dir.mkdir(parents=True, exist_ok=True)
    os.environ["NICEGUI_STORAGE_PATH"] = str(nicegui_storage_dir)
    logger.info("Using NiceGUI storage path: %s", nicegui_storage_dir)
    logger.info("Starting Manager UI on host=0.0.0.0 port=%s", _ui_port)
    logger.info("Manager UI expected URLs: %s", ", ".join(_manager_ui_urls(_ui_port)))
    ui.run(title='VPinFE Manager UI',
           host='0.0.0.0',
           port=_ui_port,
           reload=False,
           show=False,
           storage_secret=STORAGE_SECRET)

def start_manager_ui(port=8001):
    global _ui_thread, _ui_port
    _ui_port = port
    if _ui_thread and _ui_thread.is_alive():
        logger.info("Manager UI is already running")
        return _ui_thread
    _ui_thread = threading.Thread(target=_run_ui, daemon=True)
    _ui_thread.start()
    return _ui_thread

def stop_manager_ui():
    app.shutdown()
