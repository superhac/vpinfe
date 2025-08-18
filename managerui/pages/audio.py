
import subprocess
import re
import os
from nicegui import ui
from common.iniconfig import IniConfig

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


def build():
    ui.label("Audio Options").classes("text-xl font-bold")
    with ui.row().classes("w-full"):
        # Multi-Channel output
        with ui.card().classes("w-1/3"):
            ui.label("Multi-Channel output").classes("text-md font-bold")

            surround_modes = [
                "Standard 2 channel",
                "Surround (All effects to rear channels)",
                "Surround (Front is front of the cab)",
                "Surround (Front is rear of the cab)",
                "7.1 Surround (Front is rear, back is side, backbox is front)",
                "7.1 Surround Sound Feedback (enhanced)"
            ]
            sound3d_radio = ui.radio(surround_modes, value=surround_modes[0])

        # Sound Volumes
        with ui.card().classes("w-1/3"):
            ui.label("Sound Volumes").classes("text-md font-bold")

            play_sound_effects = ui.switch("Play Sound Effects", value=False)
            sfx_value = ui.label("Sound Effects Volume: 50")
            sound_volume = ui.slider(min=0, max=100, value=50, on_change=lambda e: sfx_value.set_text(f"Sound Effects Volume: {e.value}"))

            play_music = ui.switch("Play Music", value=False)
            music_value = ui.label("Music Volume: 70")
            music_volume = ui.slider(min=0, max=100, value=70, on_change=lambda e: music_value.set_text(f"Music Volume: {e.value}"))

        # Devices and AltSound
        with ui.card().classes("w-1/3"):
            ui.label("General Output Sound Device").classes("text-md font-bold")
            audio_devices = get_audio_devices()
            sound_device = ui.select(audio_devices, value=audio_devices[0])

            ui.label("Backglass Sound Device").classes("text-md font-bold")
            bg_device = ui.select(audio_devices, value=audio_devices[0])

            altsound = ui.switch("Enable Altsound", value=False)

            ui.button("💾 Save Changes", on_click=lambda: save_audio(
                sound3d_radio.value,
                play_sound_effects.value,
                play_music.value,
                sound_volume.value,
                music_volume.value,
                sound_device.value,
                bg_device.value,
                altsound.value
            )).props("color=primary")

def save_audio(sound3d_text, play_sound, play_music, sfx_vol, music_vol, device, bg_device, alt):
    # Map text to numeric value for .ini
    surround_map = {
        "Standard 2 channel": "0",
        "Surround (All effects to rear channels)": "1",
        "Surround (Front is front of the cab)": "2",
        "Surround (Front is rear of the cab)": "3",
        "7.1 Surround (Front is rear, back is side, backbox is front)": "4",
        "7.1 Surround Sound Feedback (enhanced)": "5"
    }

    #ini.set("Player", "Sound3D", surround_map[sound3d_text])
    #ini.set("Player", "PlaySound", "1" if play_sound else "0")
    #ini.set("Player", "PlayMusic", "1" if play_music else "0")
    #ini.set("Player", "SoundVolume", str(sfx_vol))
    #ini.set("Player", "MusicVolume", str(music_vol))
    #ini.set("Player", "SoundDevice", device)
    #ini.set("Player", "SoundDeviceBG", bg_device)
    #ini.set("Standalone", "AltSound", "1" if alt else "0")
    #ini.save()
    ui.notify("Audio settings saved!", type="positive")
