from __future__ import annotations
import logging
from nicegui import ui, app, context
from fastapi.responses import JSONResponse
from .pages import tables as tab_tables
from .pages import vpinfe_config as tab_vpinfe
from .pages import collections as tab_collections
from .pages import media as tab_media
from .pages import themes as tab_themes
from .pages import system as tab_system
from .pages import remote
from .pages.remote import _restart_app, _quit_app
from .pages import mobile as tab_mobile
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

def header():
    # Enable dark mode by default
    ui.dark_mode(value=True)
    with ui.header().classes('items-center justify-between').style(
        'background: var(--header-gradient); '
        'box-shadow: var(--shadow);'
    ):
        with ui.row().classes('gap-3 items-center'):
            ui.image('/static/img/vpinfe-logo.png').style('height: 60px; width: 75px; filter: drop-shadow(var(--glow-cyan));margin: -10px;')
            ui.label('VPinFE Manager').classes('text-xl').style('color: var(--ink); text-shadow: var(--glow-cyan); font-weigth: 900;')
            ui.button(icon='restart_alt', on_click=lambda: _restart_app()) \
                .props('flat round dense').classes('text-green-400') \
                .tooltip('Restart VPinFE')
            ui.button(icon='power_settings_new', on_click=lambda: _quit_app()) \
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
                        _quit_app()
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
    # Add global styles for modern look
    ui.add_head_html('''
    <style>
        :root {
          --bg: #0a0518;
          --bg-secondary: #150a2e;
          --surface: #1a0f35;
          --surface-2: #251447;
          --surface-soft: #2a1a4a;
          --ink: #e8d5ff;
          --ink-muted: #b89dd9;
          --line: #3d2461;
          --neon-pink: #ff0a78;
          --neon-cyan: #00d9ff;
          --neon-purple: #b429f9;
          --neon-orange: #ff6b35;
          --neon-yellow: #ffd93d;
          --header-gradient: linear-gradient(135deg, #b429f9 0%, #4a1e7c 50%, #0a0518 100%);
          --sunset-gradient: linear-gradient(180deg, #ff6b35 0%, #ff0a78 25%, #b429f9 50%, #4a1e7c 100%);
          --link: #00d9ff;
          --ok: #00ff9f;
          --warn: #ffd93d;
          --bad: #ff0a78;
          --table-row: #1a0f35;
          --table-row-alt: #251447;
          --table-hover: #3d2461;
          --glow-pink: 0 0 4px rgba(255, 10, 120, 0.5), 0 0 8px rgba(255, 10, 120, 0.3);
          --glow-cyan: 0 0 4px rgba(0, 217, 255, 0.5), 0 0 8px rgba(0, 217, 255, 0.3);
          --glow-purple: 0 0 4px rgba(180, 41, 249, 0.5), 0 0 8px rgba(180, 41, 249, 0.3);
          --glow-yellow: 0 0 2px rgba(255, 217, 61, 0.4);
          --shadow: 0 2px 8px rgba(180, 41, 249, 0.2);
          --shadow-intense: 0 2px 8px rgba(180, 41, 249, 0.35);
          --radius: 12px;
          --grid-color: rgba(0, 217, 255, 0.2);
        }

        [data-theme="light"] {
          --bg: #fef3ff;
          --bg-secondary: #f5e6ff;
          --surface: #ffffff;
          --surface-2: #f0e0ff;
          --surface-soft: #faf5ff;
          --ink: #2d1b3d;
          --ink-muted: #6b4c7d;
          --line: #e0c9f0;
          --neon-pink: #d4006d;
          --neon-cyan: #0099cc;
          --neon-purple: #8e24c7;
          --neon-orange: #e65528;
          --neon-yellow: #d4a500;
          --header-gradient: linear-gradient(135deg, #fef3ff 0%, #f0e0ff 50%, #0099cc 100%);
          --sunset-gradient: linear-gradient(180deg, #e65528 0%, #d4006d 25%, #8e24c7 50%, #6b4c7d 100%);
          --link: #0099cc;
          --ok: #00a876;
          --warn: #d4a500;
          --bad: #c7004f;
          --table-row: #ffffff;
          --table-row-alt: #faf5ff;
          --table-hover: #f0e0ff;
          --glow-pink: 0 4px 16px rgba(212, 0, 109, 0.25);
          --glow-cyan: 0 4px 16px rgba(0, 153, 204, 0.25);
          --glow-purple: 0 4px 16px rgba(142, 36, 199, 0.25);
          --glow-yellow: 0 2px 10px rgba(212, 165, 0, 0.2);
          --shadow: 0 4px 24px rgba(142, 36, 199, 0.2);
          --shadow-intense: 0 8px 32px rgba(142, 36, 199, 0.2);
          --radius: 12px;
          --grid-color: rgba(0, 153, 204, 0.2);
        }

        * { box-sizing: border-box; }

        body {
            background: var(--bg) !important;
            color: var(--ink);
            font-family: sans-serif;
            min-height: 100vh;
            overflow-x: hidden;
            transition: background 300ms ease, color 300ms ease;
        }
        
        body::before {
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-image:
                linear-gradient(0deg, var(--grid-color) 1px, transparent 1px),
                linear-gradient(90deg, var(--grid-color) 1px, transparent 1px);
            background-size: 40px 40px;
            pointer-events: none;
            opacity: 0.3;
            z-index: 0;
        }
        
        .nicegui-content {
            overflow-x: hidden !important;
            max-width: 100vw !important;
        }
        
        .nav-btn {
            transition: all 0.2s ease !important;
            border-radius: var(--radius) !important;
            margin: 4px 8px !important;
            max-width: calc(100% - 16px) !important;
            overflow: hidden !important;
            color: var(--ink-muted) !important;
        }
        .nav-btn:hover {
            background: var(--surface-2) !important;
            box-shadow: var(--glow-purple) !important;
            color: var(--ink) !important;
        }
        .nav-btn-active {
            background: var(--surface-2) !important;
            box-shadow: var(--glow-purple) !important;
        }
        .nav-btn .q-btn__content {
            transition: opacity 0.3s ease;
        }
        .nav-collapsed .nav-btn .q-btn__content > :not(.q-icon) {
            opacity: 0;
            width: 0;
            height: 0;
            overflow: hidden;
            position: absolute;
        }
        .nav-collapsed .nav-btn {
            padding: 12px 8px !important;
        }
        .version-link {
            color: var(--ink) !important;
            text-shadow: var(--glow-cyan);
        }        
        .version-link:hover {
            color: var(--neon-cyan) !important;
        }
    </style>
    ''')

    header()

    # Main content area - offset by nav panel width (create first so toggle_nav can reference it)
    content_container = ui.column().classes('p-6').style('margin-left: 206px; transition: margin-left 0.3s ease; width: calc(100vw - 220px); max-width: calc(100vw - 220px); box-sizing: border-box;')

    # Navigation panel container (fixed position on left side)
    nav_panel = ui.column().classes('fixed left-0 top-16 bottom-0').style(
        'background: var(--bg-secondary); '
        'border-right: 1px solid var(--line); '
        'z-index: 100; '
        'transition: width 0.3s ease; '
        'width: 220px; '
        'overflow: hidden; '
        'display: flex; '
        'flex-direction: column;'
    )

    # Track expanded/collapsed state and UI element references
    nav_state = {'expanded': True, 'nav_content': None, 'nav_label': None, 'remote_container': None}

    def toggle_nav():
        nav_state['expanded'] = not nav_state['expanded']
        if nav_state['expanded']:
            nav_panel.style(add='width: 220px;', remove='width: 56px;')
            nav_state['nav_content'].classes(remove='nav-collapsed')
            nav_state['remote_container'].classes(remove='nav-collapsed')
            ui.query('body').classes(remove='nav-is-collapsed')
            nav_state['nav_label'].set_visibility(True)
            content_container.style(add='margin-left: 206px; width: calc(100vw - 220px); max-width: calc(100vw - 220px);', remove='margin-left: 56px; width: calc(100vw - 56px); max-width: calc(100vw - 56px);')
        else:
            nav_panel.style(add='width: 56px;', remove='width: 220px;')
            nav_state['nav_content'].classes(add='nav-collapsed')
            nav_state['remote_container'].classes(add='nav-collapsed')
            ui.query('body').classes(add='nav-is-collapsed') 
            nav_state['nav_label'].set_visibility(False)
            content_container.style(add='margin-left: 40px; width: calc(100vw - 56px); max-width: calc(100vw - 56px);', remove='margin-left: 220px; width: calc(100vw - 220px); max-width: calc(100vw - 220px);')

    with nav_panel:
        # Navigation header with hamburger menu
        with ui.row().classes('w-full items-center gap-2 p-3').style(
            'background: var(--surface) !important; border-bottom: 1px solid var(--line); margin-top: 6px;'
        ):
            ui.button(icon='menu', on_click=toggle_nav).props('flat round dense').style('color: var(--neon-cyan) !important; background: var(--surface) !important;')
            nav_state['nav_label'] = ui.label('Navigation').classes('text-lg font-bold').style('color: var(--neon-cyan) !important; background: var(--surface) !important;')

        # Navigation menu items
        nav_state['nav_content'] = ui.column().classes('w-full gap-1 mt-2')
        with nav_state['nav_content']:
            tables_btn = (
                ui.button('Tables', icon='view_list', on_click=lambda: show_page('tables'))
                .classes('w-full nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px; color: var(--ink-muted) !important;')
                .props('flat align=left')
                .tooltip('Tables')
            )
            collections_btn = (
                ui.button('Collections', icon='collections_bookmark', on_click=lambda: show_page('collections'))
                .classes('w-full nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px; color: var(--ink-muted) !important;')
                .props('flat align=left')
                .tooltip('Collections')
            )
            media_btn = (
                ui.button('Media', icon='image', on_click=lambda: show_page('media'))
                .classes('w-full nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px; color: var(--ink-muted) !important;')
                .props('flat align=left')
                .tooltip('Media')
            )
            themes_btn = (
                ui.button('Themes', icon='palette', on_click=lambda: show_page('themes'))
                .classes('w-full nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px; color: var(--ink-muted) !important;')
                .props('flat align=left')
                .tooltip('Themes')
            )
            mobile_btn = (
                ui.button('Mobile Uploader', icon='smartphone', on_click=lambda: show_page('mobile'))
                .classes('w-full nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px; color: var(--ink-muted) !important;')
                .props('flat align=left')
                .tooltip('Mobile Uploader')
            )
            system_btn = (
                ui.button('System', icon='monitor_heart', on_click=lambda: show_page('system'))
                .classes('w-full nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px; color: var(--ink-muted) !important;')
                .props('flat align=left')
                .tooltip('System')
            )
            config_btn = (
                ui.button('Configuration', icon='tune', on_click=lambda: show_page('vpinfe'))
                .classes('w-full nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px; color: var(--ink-muted) !important;')
                .props('flat align=left')
                .tooltip('Configuration')
            )
        # Remote control button anchored to bottom
        nav_state['remote_container'] = ui.column().classes('w-full gap-1 mt-auto').style('margin-top: auto; padding-bottom: 16px;')
        with nav_state['remote_container']:
            ui.separator().style('background: var(--surface-2);')
            (
                ui.button('Remote Control', icon='settings_remote', on_click=lambda: ui.navigate.to('/remote', new_tab=True))
                .classes('w-full nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px; color: var(--ink-muted) !important;')
                .props('flat align=left')
                .tooltip('Remote')
            )

    current_page = {'value': None}

    def show_page(page_key: str):
        app.storage.user['active_page'] = page_key

        # Update button styles - reset all first
        tables_btn.classes(remove='nav-btn-active')
        collections_btn.classes(remove='nav-btn-active')
        media_btn.classes(remove='nav-btn-active')
        themes_btn.classes(remove='nav-btn-active')
        mobile_btn.classes(remove='nav-btn-active')
        system_btn.classes(remove='nav-btn-active')
        config_btn.classes(remove='nav-btn-active')

        # Set active button
        if page_key == 'tables':
            tables_btn.classes(add='nav-btn-active')
        elif page_key == 'collections':
            collections_btn.classes(add='nav-btn-active')
        elif page_key == 'media':
            media_btn.classes(add='nav-btn-active')
        elif page_key == 'themes':
            themes_btn.classes(add='nav-btn-active')
        elif page_key == 'mobile':
            mobile_btn.classes(add='nav-btn-active')
        elif page_key == 'system':
            system_btn.classes(add='nav-btn-active')
        elif page_key == 'vpinfe':
            config_btn.classes(add='nav-btn-active')

        # Only re-render if page changed
        if current_page['value'] == page_key:
            return

        current_page['value'] = page_key
        content_container.clear()

        with content_container:
            if page_key == 'tables':
                tab_tables.render_panel()
            elif page_key == 'collections':
                tab_collections.render_panel()
            elif page_key == 'media':
                tab_media.render_panel()
            elif page_key == 'themes':
                tab_themes.render_panel()
            elif page_key == 'mobile':
                tab_mobile.build(standalone=False)
            elif page_key == 'system':
                tab_system.render_panel()
            elif page_key == 'vpinfe':
                tab_vpinfe.render_panel()

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
    show_page(initial_page)

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

# Map of friendly URL param values to internal page keys
_PAGE_ALIASES = {
    'tables': 'tables',
    'collections': 'collections',
    'media': 'media',
    'themes': 'themes',
    'mobile': 'mobile',
    'system': 'system',
    'vpinfe': 'vpinfe',
    'vpinfe_config': 'vpinfe',
    'configuration': 'vpinfe',
    'config': 'vpinfe',
}

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
        resolved = _PAGE_ALIASES.get(page.lower())
        if resolved:
            app.storage.user['_page_param'] = resolved
    if dialog:
        key = dialog.lower()
        if key in _DIALOG_HANDLERS:
            app.storage.user['_dialog_param'] = key
    build_app()

@ui.page('/remote')
def remote_page():
    remote.build()

@ui.page('/mobile')
def mobile_page():
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
    import tempfile
    import shutil
    from starlette.responses import FileResponse
    from starlette.background import BackgroundTask

    tables_path = tab_mobile._get_tables_path()
    table_dir = os.path.join(tables_path, name)

    # Validate the path exists and is under tables root
    real_table = os.path.realpath(table_dir)
    real_root = os.path.realpath(tables_path)
    if not real_table.startswith(real_root + os.sep):
        return JSONResponse(content={"error": "Invalid table path"}, status_code=400)
    if not os.path.isdir(table_dir):
        return JSONResponse(content={"error": "Table not found"}, status_code=404)

    # Create zip in a temp directory
    tmp_dir = tempfile.mkdtemp()
    zip_base = os.path.join(tmp_dir, name)
    zip_path = shutil.make_archive(zip_base, 'zip', root_dir=tables_path, base_dir=name)
    # Rename .zip to .vpxz
    vpxz_path = zip_base + '.vpxz'
    os.rename(zip_path, vpxz_path)

    logger.info("Created download archive: %s", vpxz_path)

    def cleanup():
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.info("Cleaned up temp archive: %s", tmp_dir)

    return FileResponse(
        vpxz_path,
        media_type='application/octet-stream',
        filename=f"{name}.vpxz",
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
    STORAGE_SECRET = "verysecret" # The storatage is just to keep the active tab between sessions. Nothing sensitive.
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
