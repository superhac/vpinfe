from __future__ import annotations
import os
import re
import subprocess
from typing import Tuple
from nicegui import ui
from ..ini_store import IniStore
from ..schema import AUDIO_FIELDS
from common.iniconfig import IniConfig
from ..binders import _bind_indexed_select, _bind_select, _bind_switch


SOUND3D_OPTIONS = [
    'Standard 2 channel',                                   # 0
    'Surround (All effects to rear channels)',              # 1
    'Surround (Front is rear of cab)',                      # 2
    'Surround (Front is front of cab)',                     # 3
    '7.1 Surround (Front is rear, back is side, backbox is front)',  # 4
    '7.1 Surround SSF',       # 5
]

def get_audio_devices():

    config = IniConfig("./vpinfe.ini")
    vpxbinpath = config.config.get('Settings', 'vpxbinpath', fallback='').strip()
    if not vpxbinpath:
        ui.notify("VPX Binary not found on vpinfe.ini.", type="warning")
        return ["No Audio device detected"]

    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    try:
        result = subprocess.run([
            vpxbinpath, "-listsnd"
        ], capture_output=True, text=True, check=True, env=env)
        output = result.stdout + result.stderr  
        devices = re.findall(r"^.*?\. ([^,]+), channels=", output, re.MULTILINE)
        return devices if devices else ["No Audio device detected"]
    except Exception as e:
        ui.notify(f"Error listing devices: {e}", type="warning")
        return ["No Audio device detected"]

def _bind_slider_string(store: IniStore, slider, sec_opt: Tuple[str, str], default=0):
    """Slider UI (number) ↔ store (string)."""
    sec, opt = sec_opt

    def push(val: str):
        try:
            slider.value = float(val)
        except Exception:
            slider.value = default
    push(store.get(sec, opt))
    store.on_change(sec, opt, push)

    slider.on('update:model-value', lambda e: store.set(sec, opt, str(slider.value))).props('label-always')


def create_tab():
    return ui.tab('Audio',icon='volume_up').props('icon-color=primary')

audio_devices = get_audio_devices()
def render_panel(tab, store):
    """Registers the 'Audio' tab and its panel content."""
    with ui.tab_panel(tab):
        ui.label('Audio Settings').classes('text-xl font-semibold')
        with ui.card().classes('max-w-3xl w-full'):
            # NEW: Multi-Channel Output (Sound3D)
            with ui.row().classes('w-full items-center gap-6'):
                ui.label('Multi-Channel Output').classes('w-40')
                sound3d = ui.select(options=SOUND3D_OPTIONS).classes('flex-1')
            with ui.column().classes('w-full gap-4'):
                with ui.row().classes('w-full items-center gap-6'):
                    ui.label('Play Sounds Effects').classes('w-40')
                    play_sound= ui.switch()
                # Master
                with ui.row().classes('w-full items-center gap-6'):
                    ui.label('Sound Effects Volume').classes('w-40')
                    vol_sound = ui.slider(min=0, max=100).props('clearable').classes('flex-1')
                # Music
                with ui.row().classes('w-full items-center gap-6'):
                    ui.label('Play Music').classes('w-40')
                    play_music = ui.switch()
                with ui.row().classes('w-full items-center gap-6'):
                    ui.label('Music Volume').classes('w-40')
                    vol_music = ui.slider(min=0, max=100).props('clearable').classes('flex-1')
                ui.separator()
                # Devices
                with ui.row().classes('w-full items-center gap-6'):
                    ui.label('General Audio Device').classes('w-40')
                    sound_dev = ui.select(audio_devices).classes('flex-1')
                with ui.row().classes('w-full items-center gap-6'):
                    ui.label('Backglass Audio Device').classes('w-40')
                    bg_sound_dev = ui.select(audio_devices).classes().classes('flex-1')
        
        # sliders (store remains string)
        _bind_slider_string(store, vol_sound,  AUDIO_FIELDS['sound_volume'])
        _bind_slider_string(store, vol_music,   AUDIO_FIELDS['music_volume'])

        # switches (store '1'/'0')
        _bind_switch(store, play_music,  AUDIO_FIELDS['play_music'])
        _bind_switch(store, play_sound,  AUDIO_FIELDS['play_sound'])

        # selects / comboboxes (store string label)
        _bind_select(store, sound_dev,   AUDIO_FIELDS['sound_device'])
        _bind_select(store, bg_sound_dev, AUDIO_FIELDS['backglass_device'])

        # Sound3D
        _bind_indexed_select(store, sound3d, AUDIO_FIELDS['sound3d'], SOUND3D_OPTIONS)
