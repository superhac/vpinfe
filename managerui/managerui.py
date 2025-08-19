import threading
from nicegui import ui
from .pages import audio, nudge, video, buttons, tables, global_options, vr, plugins, cabinet_editor, vpinfe_config, remote

@ui.page('/')
def main_page():
    with ui.header(elevated=True).style('background-color: #424242').classes('items-center justify-between'):
        dark = ui.dark_mode()
        with ui.avatar():
            ui.image('static/img/vpinball.png')
        ui.label('Visual Pinball X - Remote Config').classes("text-md font-bold")
        ui.switch('Dark Mode').bind_value(dark)
    with ui.column().classes("w-full"):
        with ui.tabs().props('dense') as tabs:
            audio_tab = ui.tab('Audio', icon='volume_up')
            video_tab = ui.tab('Video', icon='monitor')
            plugins_tab = ui.tab('Plugins', icon='extension')
            buttons_tab = ui.tab('Buttons', icon='sports_esports')
            tables_tab = ui.tab('Tables', icon='list')
            dof_tab = ui.tab('DOF', icon='lightbulb')
            global_options_tab = ui.tab('Global Options', icon='public')
            vr_tab = ui.tab('VR', icon='360')
            backup_tab = ui.tab('Backup', icon='backup')
            dof_editor_tab = ui.tab('DOF Editor', icon='edit')
            vpinfe_config_tab = ui.tab('VPINFE Config', icon='settings')

        with ui.tab_panels(tabs, value=audio_tab).classes("w-full"):
            with ui.tab_panel(audio_tab):
                audio.build()
            with ui.tab_panel(video_tab):
                video.build()
            with ui.tab_panel(buttons_tab):
                buttons.build()
            with ui.tab_panel(tables_tab):
                tables.build()
            with ui.tab_panel(dof_tab):
                nudge.build()
            with ui.tab_panel(global_options_tab):
                global_options.build()
            with ui.tab_panel(vr_tab):
                vr.build()
            with ui.tab_panel(plugins_tab):
                plugins.build()
            with ui.tab_panel(dof_editor_tab):
                cabinet_editor.build()
            with ui.tab_panel(vpinfe_config_tab):
                vpinfe_config.build()

@ui.page('/table_details_ini/{table_name}')
def table_details_ini_page(table_name: str):
    all_table_data = tables.load_metadata_from_ini()
    current_table_data_row = next(
        (item for item in all_table_data if item.get('filename') == table_name or item.get('name') == table_name),
        None,
    )
    if current_table_data_row:
        tables.build_table_details_page_content(current_table_data_row)
    else:
        ui.label(f"Table '{table_name}' not found. 😕").classes("text-negative text-xl")

@ui.page('/remote')
def remote_page():
    remote.build()

# keep a reference to the running thread
_ui_thread = None

def _run_ui():
    ui.run(title='VPinFE Manager UI', port=8001, reload=False, show=False)

def start_manager_ui():
    global _ui_thread
    if _ui_thread and _ui_thread.is_alive():
        print("Manager UI is already running")
        return _ui_thread
    _ui_thread = threading.Thread(target=_run_ui, daemon=True)
    _ui_thread.start()
    return _ui_thread

def stop_manager_ui():
    from nicegui import app
    app.shutdown()   # tells uvicorn to shut down gracefully

