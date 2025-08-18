import re
import subprocess
from nicegui import ui

def calc_ratio(width, height):
    from fractions import Fraction
    ratio = Fraction(width, height).limit_denominator()
    return f"{ratio.numerator}:{ratio.denominator}"

def get_display_resolutions():
    vpx_path = VPinballBin().get_filepath()
    try:
        scr_cmd_result = subprocess.run(f'"{vpx_path}" -listres', shell=True, capture_output=True, text=True)
    except Exception as e:
        return {"Display 1": []}

    displays_info = {}
    screen_regex = re.compile(r"display (\d+): (\d+)x(\d+) \(depth=(\d+), refreshRate=(\d+(?:\.\d+)?)\)")

    for line in scr_cmd_result.stdout.split("\n"):
        match = screen_regex.search(line)
        if match:
            display_id = f"Display {match.group(1)}"
            width, height = int(match.group(2)), int(match.group(3))
            depth = match.group(4)
            refresh_rate = match.group(5)
            ratio = calc_ratio(width, height)
            resolution_info = f"{width} x {height} ({refresh_rate}Hz {ratio}, depth={depth})"
            displays_info.setdefault(display_id, []).append(resolution_info)

    return displays_info

def build():
    ui.label("Video Options").classes("text-xl font-bold")
    resolutions = { "display 1": ["1920 x 1080 (60Hz 16:9, depth=24)", "2560 x 1440 (60Hz 16:9, depth=24)"]}

    # Display selection
    displays = list(resolutions.keys())
    selected_display = ui.select(displays, label='Display').classes('w-full').style("min-width: 200px")
    selected_resolution = ui.select([], label='Resolution').classes('w-full').style("min-width: 200px")

    def on_display_change(e):
        selected_resolution.options = resolutions.get(selected_display.value, [])

    selected_display.on('update:model-value', on_display_change)

    # UI Layout
    with ui.row().classes("w-full gap-8"):
        with ui.column().classes("gap-2").style("min-width: 260px"):
            ui.switch("Enable Altcolor")
            ui.label("Display Selection").classes("font-bold")
            selected_display
            selected_resolution
            ui.radio(["Window", "Exclusive Fullscreen"], value="Exclusive Fullscreen")
            ui.select(["Desktop", "Cabinet"], label="View Mode").classes("w-full").style("min-width: 200px")
            ui.checkbox("Override Table Global Lighting")
            ui.checkbox("Automatic Day/Night cycle")
            ui.label("Night/Day")
            ui.slider(min=0, max=100, value=50,)
            ui.input("Latitude")
            ui.input("Longitude")
            ui.select(["Default Renderer", "Alternative Renderer"], label="Renderer").style("min-width: 200px")
            ui.button("Set For Low End PC").props("outline")
            ui.button("Set For High End PC").props("outline")

        with ui.column().classes("gap-2").style("min-width: 260px"):
             ui.label("Ball Rendering").classes("font-bold")
             ui.checkbox("Ball Trails")
             ui.checkbox("Force Round Ball")
             ui.checkbox("Disable Lighting")
             ui.checkbox("Overwrite Ball Image")
             ui.input("Ball Image")
             ui.input("Ball Decal")
             ui.label("Strength")
             ui.slider(min=0, max=100)
             ui.label("3D Stereo Output").classes("font-bold")
             ui.select(["Disabled", "Top/Bottom", "Side-by-Side"], label="3D Stereo Output").style("min-width: 200px")
             ui.checkbox("Fake Stereo (Performance)")
             ui.select(["None", "Red/Cyan", "Green/Magenta"], label="Anaglyph Filter").style("min-width: 200px")
             ui.input("Anaglyph Brightness")
             ui.input("Anaglyph Saturation")
             ui.input("Eye Separation (mm)")
             ui.input("ZPD")
             ui.input("Offset")

        with ui.column().classes("gap-2").style("min-width: 260px"):
            ui.label("Performance and Troubleshooting").classes("font-bold")
            ui.select(["Static AO", "SSAO"], label="Max. Ambient Occlusion").style("min-width: 200px")
            ui.select(["Disable Reflections", "Static", "Dynamic"], label="Max. Reflection Mode").style("min-width: 200px")
            ui.select(["Unlimited", "2048", "1024"], label="Max. Texture Dimension").style("min-width: 200px")
            ui.checkbox("Compress Textures (Performance)")
            ui.checkbox("Force Anisotropic Texture (quality)")
            ui.checkbox("Force Bloom Filter Off (performance)")
            ui.checkbox("Use Alternative Depth Buffer processing (legacy)")
            ui.checkbox("Use Software Vertex processing (legacy)")
            ui.label("Elements Detail Level")
            ui.slider(min=0, max=100, value=75)

        with ui.column().classes("gap-2").style("min-width: 260px"):
            ui.label("Sync and AA").classes("font-bold").style("min-width: 200px")
            ui.select(["No Sync", "VRR", "VSync"], label="Synchronization Mode").style("min-width: 200px")
            ui.input("Maximum Framerate", value="-1.0")
            ui.input("Maximum pre-rendered Frames")
            ui.select(["Disabled", "2x", "4x", "8x"], label="MSAA Samples").style("min-width: 200px")
            ui.select(["Disabled", "2x", "4x"], label="Supersampling").style("min-width: 200px")
            ui.select(["Standard FXAA", "High Quality FXAA"], label="Post-processed AA").style("min-width: 200px")
            ui.select(["Disabled", "1", "2", "3"], label="Sharpen").style("min-width: 200px")
            ui.checkbox("Enable ScaleFX for Internal DMD")

            ui.label("Cabinet Layout").classes("font-bold")
            ui.input("Screen Width (cm)")
            ui.input("Screen Height (cm)")
            ui.input("Screen Inclination")
            ui.input("Player X (cm)")
            ui.input("Player Y (cm)")
            ui.input("Player Z (cm)")
            ui.input("Visual Nudge Strength")
            ui.checkbox("Additional Screen Space Reflections")

    ui.button("Save Changes").props("color=primary")