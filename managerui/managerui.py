from __future__ import annotations
from pathlib import Path
from nicegui import ui, app
from fastapi import Response
from fastapi.responses import JSONResponse
from .pages import tables as tab_tables
from .pages import vpinfe_config as tab_vpinfe
from .pages import collections as tab_collections
from .pages import media as tab_media
from .pages import remote
import threading
import subprocess
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import os
import json

# Shared state for remote launch notifications
_remote_launch_state = {
    'launching': False,
    'table_name': None,
}

# Cache for update check result (check once per session)
_update_check_cache = {'checked': False, 'update_available': False, 'error': None}

def _get_project_root() -> Path:
    """Get the project root directory (where .git should be)."""
    return Path(__file__).resolve().parents[1]

def _has_git_repo() -> bool:
    """Check if the project has a .git directory."""
    git_dir = _get_project_root() / '.git'
    return git_dir.exists() and git_dir.is_dir()

def _get_local_commit_date() -> datetime | None:
    """Get the commit date of the local HEAD."""
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%cI'],
            capture_output=True,
            text=True,
            cwd=str(_get_project_root()),
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse ISO 8601 date
            date_str = result.stdout.strip()
            return datetime.fromisoformat(date_str)
    except Exception as e:
        print(f"[UpdateCheck] Failed to get local commit date: {e}")
    return None

def _get_remote_last_modified() -> datetime | None:
    """Get the last-modified date from GitHub API."""
    try:
        url = 'https://api.github.com/repos/superhac/vpinfe/commits'
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', 'VPinFE-UpdateChecker')
        with urllib.request.urlopen(req, timeout=10) as response:
            last_modified = response.headers.get('Last-Modified')
            if last_modified:
                return parsedate_to_datetime(last_modified)
    except Exception as e:
        print(f"[UpdateCheck] Failed to check remote: {e}")
    return None

def check_for_updates() -> dict:
    """
    Check if updates are available by comparing local commit date with remote.
    Returns dict with 'update_available' (bool) and 'error' (str or None).
    """
    global _update_check_cache

    # Return cached result if already checked
    if _update_check_cache['checked']:
        return _update_check_cache

    _update_check_cache['checked'] = True

    if not _has_git_repo():
        _update_check_cache['error'] = 'no_git'
        return _update_check_cache

    local_date = _get_local_commit_date()
    if not local_date:
        _update_check_cache['error'] = 'local_date_failed'
        return _update_check_cache

    remote_date = _get_remote_last_modified()
    if not remote_date:
        _update_check_cache['error'] = 'remote_check_failed'
        return _update_check_cache

    # Ensure both dates are timezone-aware for comparison
    if local_date.tzinfo is None:
        local_date = local_date.replace(tzinfo=timezone.utc)
    if remote_date.tzinfo is None:
        remote_date = remote_date.replace(tzinfo=timezone.utc)

    # Update available if remote is newer than local
    _update_check_cache['update_available'] = remote_date > local_date
    _update_check_cache['local_date'] = local_date
    _update_check_cache['remote_date'] = remote_date

    return _update_check_cache

def header():
    # Enable dark mode by default
    ui.dark_mode(value=True)
    with ui.header().classes('items-center justify-between').style(
        'background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); '
        'box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);'
    ):
        with ui.row().classes('gap-3 items-center'):
            ui.icon('sports_esports', size='28px').classes('text-blue-400')
            ui.label('VPinFE Manager').classes('text-xl font-bold text-white')

        # Update notification (right side of header)
        update_container = ui.row().classes('gap-2 items-center')
        with update_container:
            # Check for updates asynchronously to not block UI
            async def check_updates_async():
                from nicegui import run
                result = await run.io_bound(check_for_updates)
                with update_container:
                    if result.get('update_available'):
                        ui.icon('system_update', size='20px').classes('text-yellow-400')
                        ui.link(
                            'Update Available',
                            'https://github.com/superhac/vpinfe/commits/master/',
                            new_tab=True
                        ).classes('text-yellow-400 text-sm font-medium hover:text-yellow-300').style('text-decoration: none;')
                    elif result.get('error') is None:
                        ui.icon('check_circle', size='20px').classes('text-green-400')
                        ui.label('Up to date').classes('text-green-400 text-sm font-medium')

            # Only check if git repo exists
            if _has_git_repo():
                ui.timer(0.5, check_updates_async, once=True)

def build_app():
    # Add global styles for modern look
    ui.add_head_html('''
    <style>
        body {
            background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%) !important;
            min-height: 100vh;
            overflow-x: hidden;
        }
        .nicegui-content {
            overflow-x: hidden !important;
            max-width: 100vw !important;
        }
        .nav-btn {
            transition: all 0.2s ease !important;
            border-radius: 8px !important;
            margin: 4px 8px !important;
            max-width: calc(100% - 16px) !important;
            overflow: hidden !important;
        }
        .nav-btn:hover {
            background: rgba(59, 130, 246, 0.2) !important;
        }
        .nav-btn-active {
            background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%) !important;
            box-shadow: 0 2px 8px rgba(45, 90, 135, 0.4) !important;
        }
    </style>
    ''')

    header()

    # Main content area - offset by nav panel width (create first so toggle_nav can reference it)
    content_container = ui.column().classes('p-6').style('margin-left: 220px; transition: margin-left 0.3s ease; width: calc(100vw - 220px); max-width: calc(100vw - 220px); box-sizing: border-box;')

    # Navigation panel container (fixed position on left side)
    nav_panel = ui.column().classes('fixed left-0 top-16 bottom-0').style(
        'background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%); '
        'border-right: 1px solid #334155; '
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
            nav_state['nav_content'].set_visibility(True)
            nav_state['nav_label'].set_visibility(True)
            nav_state['remote_container'].set_visibility(True)
            content_container.style(add='margin-left: 220px; width: calc(100vw - 220px); max-width: calc(100vw - 220px);', remove='margin-left: 56px; width: calc(100vw - 56px); max-width: calc(100vw - 56px);')
        else:
            nav_panel.style(add='width: 56px;', remove='width: 220px;')
            nav_state['nav_content'].set_visibility(False)
            nav_state['nav_label'].set_visibility(False)
            nav_state['remote_container'].set_visibility(False)
            content_container.style(add='margin-left: 56px; width: calc(100vw - 56px); max-width: calc(100vw - 56px);', remove='margin-left: 220px; width: calc(100vw - 220px); max-width: calc(100vw - 220px);')

    with nav_panel:
        # Navigation header with hamburger menu
        with ui.row().classes('w-full items-center gap-2 p-3').style(
            'background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);'
        ):
            ui.button(icon='menu', on_click=toggle_nav).props('flat round dense').classes('text-white')
            nav_state['nav_label'] = ui.label('Navigation').classes('text-white text-lg font-bold')

        # Navigation menu items
        nav_state['nav_content'] = ui.column().classes('w-full gap-1 mt-2')
        with nav_state['nav_content']:
            tables_btn = (
                ui.button('Tables', icon='view_list', on_click=lambda: show_page('tables'))
                .classes('w-full text-white nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px;')
                .props('flat align=left')
            )
            collections_btn = (
                ui.button('Collections', icon='collections_bookmark', on_click=lambda: show_page('collections'))
                .classes('w-full text-white nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px;')
                .props('flat align=left')
            )
            media_btn = (
                ui.button('Media', icon='image', on_click=lambda: show_page('media'))
                .classes('w-full text-white nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px;')
                .props('flat align=left')
            )
            config_btn = (
                ui.button('Configuration', icon='tune', on_click=lambda: show_page('vpinfe'))
                .classes('w-full text-white nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px;')
                .props('flat align=left')
            )

        # Remote control button anchored to bottom
        nav_state['remote_container'] = ui.column().classes('w-full gap-1 mt-auto').style('margin-top: auto; padding-bottom: 16px;')
        with nav_state['remote_container']:
            ui.separator().classes('bg-slate-600')
            (
                ui.button('Remote Control', icon='settings_remote', on_click=lambda: ui.navigate.to('/remote', new_tab=True))
                .classes('w-full text-white nav-btn')
                .style('justify-content: flex-start; padding: 12px 16px;')
                .props('flat align=left')
            )

    current_page = {'value': None}

    def show_page(page_key: str):
        app.storage.user['active_page'] = page_key

        # Update button styles - reset all first
        tables_btn.classes(remove='nav-btn-active')
        collections_btn.classes(remove='nav-btn-active')
        media_btn.classes(remove='nav-btn-active')
        config_btn.classes(remove='nav-btn-active')

        # Set active button
        if page_key == 'tables':
            tables_btn.classes(add='nav-btn-active')
        elif page_key == 'collections':
            collections_btn.classes(add='nav-btn-active')
        elif page_key == 'media':
            media_btn.classes(add='nav-btn-active')
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
            elif page_key == 'vpinfe':
                tab_vpinfe.render_panel()

    # Show default page (tables) or saved page
    saved_page = app.storage.user.get('active_page', 'tables')
    show_page(saved_page)

@ui.page('/')
def index():
    build_app()

@ui.page('/remote')
def remote_page():
    remote.build()


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


def set_remote_launch_state(launching: bool, table_name: str = None):
    """Set the remote launch state (called by remote.py)."""
    global _remote_launch_state
    _remote_launch_state['launching'] = launching
    _remote_launch_state['table_name'] = table_name

# keep a reference to the running thread
_ui_thread = None

_ui_port = 8001

def _run_ui():
    STORAGE_SECRET = "verysecret" # The storatage is just to keep the active tab between sessions. Nothing sensitive.
    ui.run(title='VPinFE Manager UI',
           port=_ui_port,
           reload=False,
           show=False,
           storage_secret=STORAGE_SECRET)

def start_manager_ui(port=8001):
    global _ui_thread, _ui_port
    _ui_port = port
    if _ui_thread and _ui_thread.is_alive():
        print("Manager UI is already running")
        return _ui_thread
    _ui_thread = threading.Thread(target=_run_ui, daemon=True)
    _ui_thread.start()
    return _ui_thread

def stop_manager_ui():
    app.shutdown()
