from __future__ import annotations
from pathlib import Path
from nicegui import ui, app
from .pages import tables as tab_tables
from .pages import vpinfe_config as tab_vpinfe
from .pages import remote
import threading

def header():
    with ui.header().style('background-color: #000').classes('items-center justify-between'):
        dark = ui.dark_mode()
        with ui.avatar():
                ui.image('static/img/vpinball.png')
        ui.label('VPINFE Manager UI').classes('text-lg font-semibold')
        with ui.row().classes('gap-2'):
            ui.switch('Dark Mode').bind_value(dark)

def build_app():
    header()

    # Left drawer for navigation
    with ui.left_drawer(value=True).classes('bg-gray-800') as drawer:
        ui.label('Navigation').classes('text-white text-lg font-semibold p-4')
        ui.separator()

        # Navigation menu items
        with ui.column().classes('w-full p-2'):
            tables_btn = ui.button('Tables', icon='list', on_click=lambda: show_page('tables')).classes('w-full text-white').style('justify-content: flex-start;').props('flat align=left')
            config_btn = ui.button('VPinFE Config', icon='settings', on_click=lambda: show_page('vpinfe')).classes('w-full text-white').style('justify-content: flex-start;').props('flat align=left')

    # Main content area - only render the active page
    content_container = ui.column().classes('w-full p-4')

    current_page = {'value': None}

    def show_page(page_key: str):
        app.storage.user['active_page'] = page_key

        # Update button styles
        if page_key == 'tables':
            tables_btn.classes(add='bg-gray-700')
            config_btn.classes(remove='bg-gray-700')
        else:
            tables_btn.classes(remove='bg-gray-700')
            config_btn.classes(add='bg-gray-700')

        # Only re-render if page changed
        if current_page['value'] == page_key:
            return

        current_page['value'] = page_key
        content_container.clear()

        with content_container:
            if page_key == 'tables':
                tab_tables.render_panel()
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
