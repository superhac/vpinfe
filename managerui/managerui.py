from __future__ import annotations
from pathlib import Path
from nicegui import ui, app
from .ini_store import IniStore
from .pages import audio as tab_audio
from .pages import video as tab_video
from .pages import nudge as tab_nudge
from .pages import buttons as tab_buttons
from .pages import tables as tab_tables
from .pages import vpinfe_config as tab_vpinfe
from .pages import plugins as tab_plugins
from .pages import remote
from .pages import highscores as tab_highscores
import threading

def init_store(path: Path) -> IniStore:
    if not path.exists():
        path.write_text('', encoding='utf-8')
    return IniStore(path)

def header(store: IniStore):
    with ui.header().style('background-color: #000').classes('items-center justify-between'):
        dark = ui.dark_mode()
        with ui.avatar():
                ui.image('static/img/vpinball.png')
        ui.label('VPINFE Manager UI').classes('text-lg font-semibold')
        with ui.row().classes('gap-2'):
            ui.switch('Dark Mode').bind_value(dark)
            ui.button('Reload', on_click=lambda: (store.reload(), ui.notify('Reloaded', type='info')))
            ui.button('Save', color='primary', on_click=lambda: confirm_and_save(store))

def confirm_and_save(store: IniStore):
    diffs = store.diff()
    if not diffs:
        ui.notify('No changes to save.', type='info')
        return

    rows = [{'Field': f'[{d.section}] {d.option}', 'Current': d.old, 'New': d.new} for d in diffs]

    with ui.dialog() as dialog, ui.card().classes('min-w-[900px]'):
        ui.label('Review changes').classes('text-xl font-semibold')
        ui.separator()
        ui.table(
            columns=[
                {'name': 'Field', 'label': 'Field', 'field': 'Field'},
                {'name': 'Current', 'label': 'Current', 'field': 'Current'},
                {'name': 'New', 'label': 'New', 'field': 'New'},
            ],
            rows=rows,
            row_key='Field',
            pagination=10,
        ).classes('max-h-[420px]')
        with ui.row().classes('justify-end w-full gap-2'):
            ui.button('Cancel', on_click=dialog.close)
            def do_save():
                store.save()
                dialog.close()
                ui.notify('Saved.', type='positive')
            ui.button('Confirm & Save', color='primary', on_click=do_save)
    dialog.open()

def footer():
    ui.footer().style('background-color: #000').classes('items-center justify-between')

def build_app(store: IniStore):

    header(store)
    with ui.tabs().classes('w-full') as tabs:
        t_audio   = tab_audio.create_tab()
        t_video   = tab_video.create_tab()
        t_plugins = tab_plugins.create_tab()
        t_nudge   = tab_nudge.create_tab()
        t_btns    = tab_buttons.create_tab()
        t_tb      = tab_tables.create_tab()
        t_hs      = tab_highscores.create_tab()
        t_vpinfe  = tab_vpinfe.create_tab()

        tab_map = {
            'audio': t_audio,
            'video': t_video,
            'plugins': t_plugins,
            'nudge': t_nudge,
            'buttons': t_btns,
            'tables': t_tb,
            'hiscores': t_hs,
            'vpinfe': t_vpinfe,
        }

        saved_key = app.storage.user.get('active_tab_key', 'audio')
        tabs.set_value(tab_map.get(saved_key, t_audio))

        def on_tab_change(e):
            for key, tab in tab_map.items():
                if tab == e.value:
                    app.storage.user['active_tab_key'] = key
                    return
        tabs.on_value_change(on_tab_change)

    ui.separator()
    with ui.tab_panels(tabs).classes('w-full'):
        tab_audio.render_panel(t_audio, store)
        tab_video.render_panel(t_video, store)
        tab_plugins.render_panel(t_plugins, store)
        tab_nudge.render_panel(t_nudge, store)
        tab_buttons.render_panel(t_btns, store)
        tab_tables.render_panel(t_tb)
        tab_highscores.render_panel(t_hs)
        tab_vpinfe.render_panel(t_vpinfe)

    footer()

store = IniStore(Path('VPinballX.ini'))

@ui.page('/')
def index():
    build_app(store)

@ui.page('/remote')
def remote_page():
    remote.build()

# keep a reference to the running thread
_ui_thread = None

def _run_ui():
    STORAGE_SECRET = "verysecret"
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
    app.shutdown()   # tells uvicorn to shut down gracefully
