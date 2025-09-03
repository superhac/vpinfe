# app/tabs/video.py
from __future__ import annotations
from typing import Tuple, List, Callable, Optional
from nicegui import ui
from ..ini_store import IniStore
from ..schema import VIDEO_FIELDS
from ..binders import _bind_input, _bind_indexed_select, _bind_switch

# ---------- bindings (always string) ----------
def _apply_preset_high_end(store: IniStore):
    """High End Profile."""
    # Indexed comboboxes:
    store.set(*VIDEO_FIELDS['FXAA'], '3')          # Quality FXAA
    store.set(*VIDEO_FIELDS['Sharpen'], '2')       # Bilateral CAS
    store.set(*VIDEO_FIELDS['DynamicAO'], '1')     # Dynamic
    store.set(*VIDEO_FIELDS['SSRefl'], '1')        # Enable
    store.set(*VIDEO_FIELDS['PFReflection'], '5')  # Dynamic

    # Switch:
    store.set(*VIDEO_FIELDS['ForceAnisotropicFiltering'], '1')  # Enabled

    # Simple input:
    store.set(*VIDEO_FIELDS['AlphaRampAccuracy'], '10')

def _apply_preset_low_end(store: IniStore):
    """Low End Profile."""
    # Indexed comboboxes:
    store.set(*VIDEO_FIELDS['FXAA'], '0')          # Quality FXAA
    store.set(*VIDEO_FIELDS['Sharpen'], '0')       # Bilateral CAS
    store.set(*VIDEO_FIELDS['DynamicAO'], '0')     # Dynamic
    store.set(*VIDEO_FIELDS['SSRefl'], '0')        # Enable
    store.set(*VIDEO_FIELDS['PFReflection'], '3')  # Dynamic

    # Switch:
    store.set(*VIDEO_FIELDS['ForceAnisotropicFiltering'], '0')  # Enabled

    store.set(*VIDEO_FIELDS['AlphaRampAccuracy'], '5')


def _row_slider_int(label_text: str, min_val: int = 0, max_val: int = 10, step: int = 1):
    r = ui.row().classes('w-full items-center gap-3')
    with r:
        ui.label(label_text).classes('w-56')
        # label & label-always mostram o valor sobre o knob
        s = ui.slider(min=min_val, max=max_val, step=step).props('label label-always').classes('flex-1')
    return s

def _bind_slider_int(store: IniStore, slider, sec_opt: Tuple[str, str], min_val: int = 0, max_val: int = 10):
    """Integer slider 0..10: read string from INI, convert to int, clamp, and save as string."""
    sec, opt = sec_opt

    def _to_int(val) -> int:
        if val is None or str(val).strip() == '':
            return min_val
        try:
            return int(float(str(val).strip()))
        except Exception:
            return min_val

    def _clamp(x: int) -> int:
        return max(min_val, min(max_val, x))

    def push(val: str):
        new_v = _clamp(_to_int(val))
        # avoid unnecessary reentrancy
        if int(getattr(slider, 'value', min_val) or min_val) != new_v:
            slider.value = new_v

    push(store.get(sec, opt))
    store.on_change(sec, opt, push)

    slider.on_value_change(lambda e: store.set(sec, opt, str(int(slider.value)) if slider.value is not None else str(min_val)))


def _bind_select_value(store: IniStore, sel, sec_opt: Tuple[str, str], options: List[str]):
    """Select that shows labels and saves the value (string) in the INI."""
    sec, opt = sec_opt
    sel.options = options

    def push(val: str):
        # If the value from the INI is not in options, fallback to the first
        if val in options:
            sel.value = val
        else:
            sel.value = options[0]

    push(store.get(sec, opt))
    store.on_change(sec, opt, push)
    sel.on_value_change(lambda e: store.set(sec, opt, str(sel.value) if sel.value else ''))





def _bind_select_map(store: IniStore, sel, sec_opt: Tuple[str, str], label_to_value: dict, default_label: str):
    """
    Select that shows friendly labels and saves mapped values (string) in the INI.
    - label_to_value: { '50%': '0.500000', ... }
    - default_label: label used when INI is empty/invalid.
    Performs tolerant matching for different formats (e.g., '1', '1.0', '1.000000').
    """
    import math

    sec, opt = sec_opt
    labels = list(label_to_value.keys())
    values = list(label_to_value.values())
    # populate visible options
    sel.options = labels

    # reverse: value -> label (float comparison with tolerance)
    target = [(float(v), lbl) for lbl, v in label_to_value.items()]

    def _nearest_label_for(value_str: str) -> str:
        if not value_str:
            return default_label
        try:
            fv = float(value_str)
        except Exception:
            return default_label
        # 1) try exact match (up to 1e-6)
        for tv, lbl in target:
            if math.isclose(fv, tv, rel_tol=0, abs_tol=1e-6):
                return lbl
        # 2) if no exact match, choose the nearest
        lbl = min(target, key=lambda p: abs(p[0] - fv))[1]
        return lbl

    def push(val: str):
        sel.value = _nearest_label_for(val)

    # initial
    push(store.get(sec, opt))
    store.on_change(sec, opt, push)

    # always save the mapped value of the selected label
    sel.on_value_change(lambda e: store.set(sec, opt, label_to_value.get(sel.value, label_to_value[default_label])))

AA_PERCENT_TO_VALUE = {
    '50%':      '0.5000000',
    '75%':      '0.7500000',
    'Disabled': '1.0000000',
    '125%':     '1.2500000',
    '133%':     '1.3333330',  # 4/3 with 6 decimal places
    '150%':     '1.5000000',
    '175%':     '1.7500000',
    '200%':     '2.0000000',
}

def _enable(w, yes: bool):
    try:
        w.enable() if yes else w.disable()
    except Exception:
        w.props('disable' if not yes else '')

# ---------- small UI helpers ----------
def _row_select(label_text: str):  # select (indexed)
    r = ui.row().classes('w-full items-center gap-3')
    with r:
        ui.label(label_text).classes('w-56')
        comp = ui.select(options=[]).props('dense').classes('flex-1')
    return comp

def _row_switch(label_text: str):  # 1/0 switch
    r = ui.row().classes('w-full items-center gap-3')
    with r:
        ui.label(label_text).classes('w-56')
        comp = ui.switch().classes('flex-none')
    return comp

def _row_input(label_text: str):   # plain string input
    r = ui.row().classes('w-full items-center gap-3')
    with r:
        ui.label(label_text).classes('w-56')
        comp = ui.input().props('clearable dense').classes('flex-1')
    return comp

# ---------- tab API ----------
def create_tab():
    return ui.tab('Video', icon='monitor')

def render_panel(tab, store: IniStore):
    with ui.tab_panel(tab):
        ui.label('Video Settings').classes('text-xl font-semibold')
        with ui.row().classes('w-full gap-4 mb-4'):
            ui.button('High End PC', icon='arrow_circle_up', on_click=lambda: _apply_preset_high_end(store))
            ui.button('Low End PC', icon='arrow_circle_down', on_click=lambda: _apply_preset_low_end(store))
        
        # ================================= ROW 1 =================================
        with ui.grid(columns=2).classes('w-full gap-0'):
            # Display & Sync
            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Playfield Positioning and Size').classes('text-base font-medium')
                PlayfieldDisplay = _row_input("Playfield Display")
                _bind_input(store, PlayfieldDisplay, VIDEO_FIELDS['PlayfieldDisplay'])
                PlayfieldFullScreen = _row_input("Playfield FullScreen")
                _bind_input(store, PlayfieldFullScreen, VIDEO_FIELDS['PlayfieldFullScreen'])
                PlayfieldWndX = _row_input("Playfield WndX")
                _bind_input(store, PlayfieldWndX, VIDEO_FIELDS['PlayfieldWndX'])
                PlayfieldWndY = _row_input("Playfield WndY")
                _bind_input(store, PlayfieldWndY, VIDEO_FIELDS['PlayfieldWndY'])
                PlayfieldAspectRatio =_row_input("Playfield AspectRatio") 
                _bind_input(store, PlayfieldAspectRatio, VIDEO_FIELDS['PlayfieldAspectRatio'])
                PlayfieldWidth = _row_input("Playfield Width")
                _bind_input(store, PlayfieldWidth, VIDEO_FIELDS['PlayfieldWidth'])
                PlayfieldHeight = _row_input("Playfield Height")
                _bind_input(store, PlayfieldHeight, VIDEO_FIELDS['PlayfieldHeight'])
                PlayfieldRender10Bit = _row_input("Playfield Render10Bit")
                _bind_input(store, PlayfieldRender10Bit, VIDEO_FIELDS['PlayfieldRender10Bit'])
                PlayfieldColorDepth = _row_input('Playfield ColorDepth')
                _bind_input(store, PlayfieldColorDepth, VIDEO_FIELDS['PlayfieldColorDepth'])
                PlayfieldRefreshRate =_row_input("Playfield RefreshRate")
                _bind_input(store, PlayfieldRefreshRate, VIDEO_FIELDS['PlayfieldRefreshRate'])

            # Backglass
            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Backglass Positioning and Size').classes('text-base font-medium')
                BackglassDisplay = _row_input("Backglass Display")
                _bind_input(store, BackglassDisplay, VIDEO_FIELDS['BackglassDisplay'])
                BackglassFullScreen = _row_input("Backglass FullScreen")
                _bind_input(store, BackglassFullScreen, VIDEO_FIELDS['BackglassFullScreen'])
                BackglassOutput = _row_input("Backglass Output")
                _bind_input(store, BackglassOutput, VIDEO_FIELDS['BackglassOutput'])
                BackglassWndX = _row_input("Backglass WndX")
                _bind_input(store, BackglassWndX, VIDEO_FIELDS['BackglassWndX'])
                BackglassWndY = _row_input("Backglass WndY")
                _bind_input(store, BackglassWndY, VIDEO_FIELDS['BackglassWndY'])
                BackglassWidth = _row_input("Backglass Width")
                _bind_input(store, BackglassWidth, VIDEO_FIELDS['BackglassWidth'])
                BackglassHeight = _row_input("Backglass Height")
                _bind_input(store, BackglassHeight, VIDEO_FIELDS['BackglassHeight'])
                Priority_PUP = _row_input("Priority PUP")
                _bind_input(store, Priority_PUP, VIDEO_FIELDS['Priority_PUP'])
                Priority_B2S = _row_input("Priority B2S")
                _bind_input(store, Priority_B2S, VIDEO_FIELDS['Priority_B2S'])
                Priority_B2SLegacy = _row_input("Priority B2SLegacy")
                _bind_input(store, Priority_B2SLegacy, VIDEO_FIELDS['Priority_B2SLegacy'])
        ui.separator()

        with ui.grid(columns=3).classes('w-full gap-0'):
            # Display & Sync
            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Display & Sync').classes('text-base font-medium')
                BGSet = _row_select('View Mode (BGSet)')
                _bind_indexed_select(store, BGSet, VIDEO_FIELDS['BGSet'], [
                    'Desktop',                  # 0
                    'Fullscreen - Cabinet',               # 1
                    'Full Single Screen (FSS)', # 2
                ])

                SyncMode = _row_select('Sync Mode')
                _bind_indexed_select(store, SyncMode, VIDEO_FIELDS['SyncMode'], [
                    'None',            # 0
                    'Vertical Sync',   # 1
                    'Adaptive Sync',   # 2
                    'Frame Pacing',    # 3
                ])

                MaxFramerate = _row_input('Max Framerate')
                _bind_input(store, MaxFramerate, VIDEO_FIELDS['MaxFramerate'])

                VisualLatencyCorrection = _row_input('Visual Latency Correction (ms)')
                _bind_input(store, VisualLatencyCorrection, VIDEO_FIELDS['VisualLatencyCorrection'])

                MaxPrerenderedFrames = _row_input('Max Prerendered Frames')
                _bind_input(store, MaxPrerenderedFrames, VIDEO_FIELDS['MaxPrerenderedFrames'])

            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Anti-Aliasing & Sharpen').classes('text-base font-medium')

                FXAA = _row_select('FXAA Mode')
                _bind_indexed_select(store, FXAA, VIDEO_FIELDS['FXAA'], [
                    'Disabled',       # 0
                    'Fast FXAA',      # 1
                    'Standard FXAA',  # 2
                    'Quality FXAA',   # 3
                    'Fast NFAA',      # 4
                    'Standard DLLA',  # 5
                    'Quality SMAA',   # 6
                ])

                Sharpen = _row_select('Sharpen')
                _bind_indexed_select(store, Sharpen, VIDEO_FIELDS['Sharpen'], [
                    'Disabled',     # 0
                    'CAS',          # 1
                    'Bilateral CAS' # 2
                ])

                AAFactor = _row_select('AA Supersampling')
                _bind_select_map(store, AAFactor, VIDEO_FIELDS['AAFactor'], AA_PERCENT_TO_VALUE, default_label='Disabled')

                MSAASamples = _row_select('MSAA Samples')
                _bind_indexed_select(store, MSAASamples, VIDEO_FIELDS['MSAASamples'], [
                    'None',      # 0
                    '4 samples', # 1 -> (value 4)
                    '6 samples', # 2 -> (value 6)
                    '8 samples', # 3 -> (value 8)
                ])

            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Ambient Occlusion & Reflections').classes('text-base font-medium')

                DisableAO = _row_select('Ambient Occlusion')
                _bind_indexed_select(store, DisableAO, VIDEO_FIELDS['DisableAO'], [
                    'Enabled',   # 0
                    'Disabled',  # 1
                ])

                DynamicAO = _row_select('AO Settings')
                _bind_indexed_select(store, DynamicAO, VIDEO_FIELDS['DynamicAO'], [
                    'Static',   # 0
                    'Dynamic',  # 1
                ])

                SSRefl = _row_select('Screen Space Reflections')
                _bind_indexed_select(store, SSRefl, VIDEO_FIELDS['SSRefl'], [
                    'Disable',  # 0
                    'Enable',   # 1
                ])

                PFReflection = _row_select('Playfield Reflection')
                _bind_indexed_select(store, PFReflection, VIDEO_FIELDS['PFReflection'], [
                    'Disable reflections',           # 0
                    'Balls only',                    # 1
                    'Static only',                   # 2
                    'Static and balls',              # 3
                    'Static and unsynced dynamics',  # 4
                    'Dynamic',                       # 5
                ])

                MaxTexDimension = _row_input('Max Texture Dimension (0 = Unlimited)')
                _bind_input(store, MaxTexDimension, VIDEO_FIELDS['MaxTexDimension'])
        
        ui.separator()

        # ================================= ROW 2 =================================
        with ui.grid(columns=3).classes('w-full gap-0'):

            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Ball Options').classes('text-base font-medium')

                DisableLightingForBalls = _row_switch('Disable Lighting for Balls')
                _bind_switch(store, DisableLightingForBalls, VIDEO_FIELDS['DisableLightingForBalls'])

                BallAntiStretch = _row_switch('Ball Anti-Stretch')
                _bind_switch(store, BallAntiStretch, VIDEO_FIELDS['BallAntiStretch'])

                OverwriteBallImage = _row_switch('Overwrite Ball Image')
                BallImage = _row_input('Ball Image')
                DecalImage = _row_input('Ball Decal')

                def _ballimg_toggle(on: bool):
                    _enable(BallImage, on)
                    _enable(DecalImage, on)

                _bind_switch(store, OverwriteBallImage, VIDEO_FIELDS['OverwriteBallImage'], on_toggle=_ballimg_toggle)
                _bind_input(store, BallImage, VIDEO_FIELDS['BallImage'])
                _bind_input(store, DecalImage, VIDEO_FIELDS['DecalImage'])

                BallTrail = _row_switch('Ball Trail')
                _bind_switch(store, BallTrail, VIDEO_FIELDS['BallTrail'])

                BallTrailStrength = _row_input('Ball Trail Strength')
                _bind_input(store, BallTrailStrength, VIDEO_FIELDS['BallTrailStrength'])

            # Bloom & Motion Blur
            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Bloom & Motion Blur').classes('text-base font-medium')

                ForceBloomOff = _row_switch('Bloom Effects')
                _bind_switch(store, ForceBloomOff, VIDEO_FIELDS['ForceBloomOff'])

                ForceMotionBlurOff = _row_switch('Ball Motion Blur')
                _bind_switch(store, ForceMotionBlurOff, VIDEO_FIELDS['ForceMotionBlurOff'])

                ForceAnisotropicFiltering = _row_switch('Anisotropic Filtering')
                _bind_switch(store, ForceAnisotropicFiltering, VIDEO_FIELDS['ForceAnisotropicFiltering'])

                CompressTextures = _row_switch('Compress Textures')
                _bind_switch(store, CompressTextures, VIDEO_FIELDS['CompressTextures'])

            # Emission / Day-Night
            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Emission & Day/Night').classes('text-base font-medium')

                OverrideTableEmissionScale = _row_switch('Override Table Emission Scale')
                EmissionScale = _row_input('Emission Scale')

                def _emission_toggle(on: bool):
                    _enable(EmissionScale, on)

                _bind_switch(store, OverrideTableEmissionScale, VIDEO_FIELDS['OverrideTableEmissionScale'], on_toggle=_emission_toggle)
                _bind_input(store, EmissionScale, VIDEO_FIELDS['EmissionScale'])

                DynamicDayNight = _row_switch('Dynamic Day/Night')
                Latitude = _row_input('Latitude')
                Longitude = _row_input('Longitude')

                def _daynight_toggle(on: bool):
                    _enable(Latitude, on)
                    _enable(Longitude, on)

                _bind_switch(store, DynamicDayNight, VIDEO_FIELDS['DynamicDayNight'], on_toggle=_daynight_toggle)
                _bind_input(store, Latitude, VIDEO_FIELDS['Latitude'])
                _bind_input(store, Longitude, VIDEO_FIELDS['Longitude'])

        ui.separator()
        with ui.grid(columns=3).classes('w-full gap-0'):

            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('System / GPU / HDR').classes('text-base font-medium')

                DisableDWM = _row_switch('Disable DWM')
                _bind_switch(store, DisableDWM, VIDEO_FIELDS['DisableDWM'])

                UseNVidiaAPI = _row_switch('Use NVidia API')
                _bind_switch(store, UseNVidiaAPI, VIDEO_FIELDS['UseNVidiaAPI'])

                HDRDisableToneMapper = _row_switch('HDR: Disable Tone Mapper')
                _bind_switch(store, HDRDisableToneMapper, VIDEO_FIELDS['HDRDisableToneMapper'])

                HDRGlobalExposure = _row_switch('HDR: Global Exposure')
                _bind_switch(store, HDRGlobalExposure, VIDEO_FIELDS['HDRGlobalExposure'])

                ui.label('Gfx Backend').classes('w-56')
                GfxBackend = ui.select(['Noop', 'Agc', 'Gnm', 'Metal', 'Nvn', 'OpenGLES', 'OpenGL', 'Vulkan']).props('dense').classes('w-full')
                _bind_select_value(store, GfxBackend, VIDEO_FIELDS['GfxBackend'], [
                    'Noop', 'Agc', 'Gnm', 'Metal', 'Nvn', 'OpenGLES', 'OpenGL', 'Vulkan'
                ])

            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Misc & Performance').classes('text-base font-medium')

                NudgeStrength = _row_input('Visual Nudge Strength')
                _bind_input(store, NudgeStrength, VIDEO_FIELDS['NudgeStrength'])

                AlphaRampAccuracy = _row_slider_int('Alpha Ramp Accuracy', 0, 10, 1)
                _bind_slider_int(store, AlphaRampAccuracy, VIDEO_FIELDS['AlphaRampAccuracy'], 0, 10)

                CaptureExternalDMD = _row_input('Capture External DMD')
                _bind_input(store, CaptureExternalDMD, VIDEO_FIELDS['CaptureExternalDMD'])

                DMDSource = _row_input('DMD Source')
                _bind_input(store, DMDSource, VIDEO_FIELDS['DMDSource'])

                CapturePUP = _row_input('Capture PUP')
                _bind_input(store, CapturePUP, VIDEO_FIELDS['CapturePUP'])

                BGSource = _row_input('Backglass Source')
                _bind_input(store, BGSource, VIDEO_FIELDS['BGSource'])

                NumberOfTimesToShowTouchMessage = _row_input('Times to Show Touch Message')
                _bind_input(store, NumberOfTimesToShowTouchMessage, VIDEO_FIELDS['NumberOfTimesToShowTouchMessage'])

                TouchOverlay = _row_input('Touch Overlay')
                _bind_input(store, TouchOverlay, VIDEO_FIELDS['TouchOverlay'])

                CacheMode = _row_input('Cache Mode')
                _bind_input(store, CacheMode, VIDEO_FIELDS['CacheMode'])

                ShowFPS = _row_select('Performance Overlay (ShowFPS)')
                _bind_indexed_select(store, ShowFPS, VIDEO_FIELDS['ShowFPS'], [
                    'Disable',  # 0
                    'FPS',      # 1
                    'Full',     # 2
                ])
            
            # Physical setup
            with ui.card():#.classes('w-full md:w-1/2'):
                ui.label('Display Physical Setup').classes('text-base font-medium')

                ScreenWidth = _row_input('Screen Width')
                _bind_input(store, ScreenWidth, VIDEO_FIELDS['ScreenWidth'])

                ScreenHeight = _row_input('Screen Height')
                _bind_input(store, ScreenHeight, VIDEO_FIELDS['ScreenHeight'])

                ScreenInclination = _row_input('Screen Inclination')
                _bind_input(store, ScreenInclination, VIDEO_FIELDS['ScreenInclination'])

                ScreenPlayerX = _row_input('Player X')
                _bind_input(store, ScreenPlayerX, VIDEO_FIELDS['ScreenPlayerX'])

                ScreenPlayerY = _row_input('Player Y')
                _bind_input(store, ScreenPlayerY, VIDEO_FIELDS['ScreenPlayerY'])

                ScreenPlayerZ = _row_input('Player Z')
                _bind_input(store, ScreenPlayerZ, VIDEO_FIELDS['ScreenPlayerZ'])
       
