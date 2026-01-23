from __future__ import annotations
from pathlib import Path
from nicegui import ui, app
from .pages import tables as tab_tables
from .pages import vpinfe_config as tab_vpinfe
from .pages import collections as tab_collections
from .pages import remote
import threading

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
        'overflow: hidden;'
    )

    # Track expanded/collapsed state and UI element references
    nav_state = {'expanded': True, 'nav_content': None, 'nav_label': None}

    def toggle_nav():
        nav_state['expanded'] = not nav_state['expanded']
        if nav_state['expanded']:
            nav_panel.style(add='width: 220px;', remove='width: 56px;')
            nav_state['nav_content'].set_visibility(True)
            nav_state['nav_label'].set_visibility(True)
            content_container.style(add='margin-left: 220px; width: calc(100vw - 220px); max-width: calc(100vw - 220px);', remove='margin-left: 56px; width: calc(100vw - 56px); max-width: calc(100vw - 56px);')
        else:
            nav_panel.style(add='width: 56px;', remove='width: 220px;')
            nav_state['nav_content'].set_visibility(False)
            nav_state['nav_label'].set_visibility(False)
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
            config_btn = (
                ui.button('Configuration', icon='tune', on_click=lambda: show_page('vpinfe'))
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
        config_btn.classes(remove='nav-btn-active')

        # Set active button
        if page_key == 'tables':
            tables_btn.classes(add='nav-btn-active')
        elif page_key == 'collections':
            collections_btn.classes(add='nav-btn-active')
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

# keep a reference to the running thread
_ui_thread = None

def _run_ui():
    STORAGE_SECRET = "verysecret" # The storatage is just to keep the active tab between sessions. Nothing sensitive.
    ui.run(title='VPinFE Manager UI',
           port=8001,
           reload=False,
           show=False,
           storage_secret=STORAGE_SECRET)

def start_manager_ui():
    global _ui_thread
    if _ui_thread and _ui_thread.is_alive():
        print("Manager UI is already running")
        return _ui_thread
    _ui_thread = threading.Thread(target=_run_ui, daemon=True)
    _ui_thread.start()
    return _ui_thread

def stop_manager_ui():
    app.shutdown()
