# app/schema.py
from __future__ import annotations
from typing import Dict, Tuple

# Set of fields that should be rendered as switches (toggles) in the UI
SWITCH_FIELDS = {
    # Plugin.B2S
    'Enable',
    'ScoreviewDMDOverlay',
    'ScoreviewDMDAutoPos',
    'BackglassDMDOverlay',
    'BackglassDMDAutoPos',

    # Plugin.B2SLegacy
    'B2SHideGrill',
    'B2SHideB2SDMD',
    'B2SHideB2SBackglass',
    'B2SHideDMD',
    'B2SDualMode',
    'B2SDMDFlipY',
    # Duplicated for B2SLegacy
    'BackglassDMDOverlay',
    'BackglassDMDAutoPos',
    'ScoreviewDMDOverlay',
    'ScoreviewDMDAutoPos',

    # Plugin.DMDUtil
    'ZeDMD',
    'ZeDMDDebug',
    'ZeDMDBrightness',
    'ZeDMDWiFi',
    'Pixelcade',
    'DumpDMDTxt',
    'DumpDMDRaw',
    'FindDisplays',

    # Plugin.PinMAME
    'Cheat',
    'Sound',
}

# AUDIO tab: ui_id -> (section, option)
AUDIO_FIELDS: Dict[str, Tuple[str, str]] = {
    'sound_volume':   ('Player', 'SoundVolume'),
    'music_volume':   ('Player', 'MusicVolume'),
    'sound_device':   ('Player', 'SoundDevice'),
    'backglass_device': ('Player', 'SoundDeviceBG'),
    'play_music':     ('Player', 'PlayMusic'),
    'play_sound':    ('Player', 'PlaySound'),
    'sound3d': ('Player', 'Sound3D'),

}

# VIDEO tab: ui_id -> (section, option)  (todas em [Player])
VIDEO_FIELDS = {
    # Display & Sync
    'BGSet': ('Player', 'BGSet'),
    'SyncMode': ('Player', 'SyncMode'),
    'MaxFramerate': ('Player', 'MaxFramerate'),
    'VisualLatencyCorrection': ('Player', 'VisualLatencyCorrection'),
    'MaxPrerenderedFrames': ('Player', 'MaxPrerenderedFrames'),

    # Anti-aliasing / Sharpen
    'FXAA': ('Player', 'FXAA'),
    'Sharpen': ('Player', 'Sharpen'),
    'AAFactor': ('Player', 'AAFactor'),
    'MSAASamples': ('Player', 'MSAASamples'),

    # AO & Reflections
    'DisableAO': ('Player', 'DisableAO'),
    'DynamicAO': ('Player', 'DynamicAO'),
    'SSRefl': ('Player', 'SSRefl'),
    'PFReflection': ('Player', 'PFReflection'),
    'MaxTexDimension': ('Player', 'MaxTexDimension'),

    # GPU / OS / HDR
    'DisableDWM': ('Player', 'DisableDWM'),
    'UseNVidiaAPI': ('Player', 'UseNVidiaAPI'),
    'HDRDisableToneMapper': ('Player', 'HDRDisableToneMapper'),
    'HDRGlobalExposure': ('Player', 'HDRGlobalExposure'),

    # Bloom / Motion blur
    'ForceBloomOff': ('Player', 'ForceBloomOff'),
    'ForceMotionBlurOff': ('Player', 'ForceMotionBlurOff'),

    # Textures / Vertex
    'ForceAnisotropicFiltering': ('Player', 'ForceAnisotropicFiltering'),
    'CompressTextures': ('Player', 'CompressTextures'),
    'GfxBackend': ('Player', 'GfxBackend'),

    # Ball options
    'DisableLightingForBalls': ('Player', 'DisableLightingForBalls'),
    'BallAntiStretch': ('Player', 'BallAntiStretch'),
    'OverwriteBallImage': ('Player', 'OverwriteBallImage'),
    'BallImage': ('Player', 'BallImage'),
    'DecalImage': ('Player', 'DecalImage'),
    'BallTrail': ('Player', 'BallTrail'),
    'BallTrailStrength': ('Player', 'BallTrailStrength'),

    # Emission / Day-Night
    'OverrideTableEmissionScale': ('Player', 'OverrideTableEmissionScale'),
    'EmissionScale': ('Player', 'EmissionScale'),
    'DynamicDayNight': ('Player', 'DynamicDayNight'),
    'Latitude': ('Player', 'Latitude'),
    'Longitude': ('Player', 'Longitude'),

    # Misc / HUD / Perf
    'NudgeStrength': ('Player', 'NudgeStrength'),
    'AlphaRampAccuracy': ('Player', 'AlphaRampAccuracy'),
    'CaptureExternalDMD': ('Player', 'CaptureExternalDMD'),
    'DMDSource': ('Player', 'DMDSource'),
    'CapturePUP': ('Player', 'CapturePUP'),
    'BGSource': ('Player', 'BGSource'),
    'NumberOfTimesToShowTouchMessage': ('Player', 'NumberOfTimesToShowTouchMessage'),
    'TouchOverlay': ('Player', 'TouchOverlay'),
    'CacheMode': ('Player', 'CacheMode'),
    'ShowFPS': ('Player', 'ShowFPS'),

    # Physical setup
    'ScreenWidth': ('Player', 'ScreenWidth'),
    'ScreenHeight': ('Player', 'ScreenHeight'),
    'ScreenInclination': ('Player', 'ScreenInclination'),
    'ScreenPlayerX': ('Player', 'ScreenPlayerX'),
    'ScreenPlayerY': ('Player', 'ScreenPlayerY'),
    'ScreenPlayerZ': ('Player', 'ScreenPlayerZ'),

     # Backglass
    'BackglassDisplay': ('Backglass', 'BackglassDisplay'), 
    'BackglassFullScreen': ('Backglass', 'BackglassFullScreen'), 
    'BackglassOutput': ('Backglass', 'BackglassOutput'), 
    'BackglassWndX': ('Backglass', 'BackglassWndX'),
    'BackglassWndY': ('Backglass', 'BackglassWndY'),
    'BackglassWidth': ('Backglass', 'BackglassWidth'),
    'BackglassHeight': ('Backglass', 'BackglassHeight'),
    'Priority_PUP': ('Backglass', 'Priority.PUP'),
    'Priority_B2S': ('Backglass', 'Priority.B2S'),
    'Priority_B2SLegacy': ('Backglass', 'Priority.B2SLegacy'),

    # Playfield Positioning and Size
    'PlayfieldDisplay': ('Player', 'PlayfieldDisplay'),
    'PlayfieldFullScreen': ('Player', 'PlayfieldFullScreen'),
    'PlayfieldWndX': ('Player', 'PlayfieldWndX'),
    'PlayfieldWndY': ('Player', 'PlayfieldWndY'),
    'PlayfieldAspectRatio': ('Player', 'PlayfieldAspectRatio'),
    'PlayfieldWidth': ('Player', 'PlayfieldWidth'),
    'PlayfieldHeight': ('Player', 'PlayfieldHeight'),
    'PlayfieldRender10Bit': ('Player', 'PlayfieldRender10Bit'),
    'PlayfieldColorDepth': ('Player', 'PlayfieldColorDepth'),
    'PlayfieldRefreshRate': ('Player', 'PlayfieldRefreshRate'),
}

# ===================== Plugins =====================

PLUGIN_ENABLE_FIELDS = {
    'AlphaDMD':       ('Plugin.AlphaDMD', 'Enable'),
    'B2S':            ('Plugin.B2S', 'Enable'),
    'B2SLegacy':      ('Plugin.B2SLegacy', 'Enable'),
    'DMDUtil':        ('Plugin.DMDUtil', 'Enable'),
    'DOF':            ('Plugin.DOF', 'Enable'),
    'FlexDMD':        ('Plugin.FlexDMD', 'Enable'),
    'PinMAME':        ('Plugin.PinMAME', 'Enable'),
    'PUP':            ('Plugin.PUP', 'Enable'),
    'RemoteControl':  ('Plugin.RemoteControl', 'Enable'),
    'Serum':          ('Plugin.Serum', 'Enable'),
    'ScoreView':      ('Plugin.ScoreView', 'Enable'),
    'WMP':            ('Plugin.WMP', 'Enable'),
}

PLUGIN_OPTIONS = {
    'AlphaDMD': [],

    'B2S': [
        # ScoreView DMD Overlay Settings
        ('Plugin.B2S', 'ScoreviewDMDOverlay'),
        ('Plugin.B2S', 'ScoreviewDMDAutoPos'),
        ('Plugin.B2S', 'ScoreviewDMDX'),
        ('Plugin.B2S', 'ScoreviewDMDY'),
        ('Plugin.B2S', 'ScoreviewDMDWidth'),
        ('Plugin.B2S', 'ScoreviewDMDHeight'),
        # Backglass DMD Overlay Settings
        ('Plugin.B2S', 'BackglassDMDOverlay'),
        ('Plugin.B2S', 'BackglassDMDAutoPos'),
        ('Plugin.B2S', 'BackglassDMDX'),
        ('Plugin.B2S', 'BackglassDMDY'),
        ('Plugin.B2S', 'BackglassDMDWidth'),
        ('Plugin.B2S', 'BackglassDMDHeight'),
    ],

    'B2SLegacy': [
        # toggles & sizes
        ('Plugin.B2SLegacy', 'B2SHideGrill'),
        ('Plugin.B2SLegacy', 'B2SHideB2SDMD'),
        ('Plugin.B2SLegacy', 'B2SHideB2SBackglass'),
        ('Plugin.B2SLegacy', 'B2SHideDMD'),
        ('Plugin.B2SLegacy', 'B2SDualMode'),
        ('Plugin.B2SLegacy', 'B2SDMDFlipY'),
        ('Plugin.B2SLegacy', 'B2SBackglassWidth'),
        ('Plugin.B2SLegacy', 'B2SBackglassHeight'),
        ('Plugin.B2SLegacy', 'B2SDMDWidth'),
        ('Plugin.B2SLegacy', 'B2SDMDHeight'),
        # Backglass DMD Overlay
        ('Plugin.B2SLegacy', 'BackglassDMDOverlay'),
        ('Plugin.B2SLegacy', 'BackglassDMDAutoPos'),
        ('Plugin.B2SLegacy', 'BackglassDMDX'),
        ('Plugin.B2SLegacy', 'BackglassDMDY'),
        ('Plugin.B2SLegacy', 'BackglassDMDWidth'),
        ('Plugin.B2SLegacy', 'BackglassDMDHeight'),
        # ScoreView DMD Overlay
        ('Plugin.B2SLegacy', 'ScoreviewDMDOverlay'),
        ('Plugin.B2SLegacy', 'ScoreviewDMDAutoPos'),
        ('Plugin.B2SLegacy', 'ScoreviewDMDX'),
        ('Plugin.B2SLegacy', 'ScoreviewDMDY'),
        ('Plugin.B2SLegacy', 'ScoreviewDMDWidth'),
        ('Plugin.B2SLegacy', 'ScoreviewDMDHeight'),
    ],

    'DMDUtil': [
        ('Plugin.DMDUtil', 'LumTintR'),
        ('Plugin.DMDUtil', 'LumTintG'),
        ('Plugin.DMDUtil', 'LumTintB'),
        ('Plugin.DMDUtil', 'ZeDMD'),
        ('Plugin.DMDUtil', 'ZeDMDDevice'),
        ('Plugin.DMDUtil', 'ZeDMDDebug'),
        ('Plugin.DMDUtil', 'ZeDMDBrightness'),
        ('Plugin.DMDUtil', 'ZeDMDWiFi'),
        ('Plugin.DMDUtil', 'ZeDMDWiFiAddr'),
        ('Plugin.DMDUtil', 'Pixelcade'),
        ('Plugin.DMDUtil', 'PixelcadeDevice'),
        ('Plugin.DMDUtil', 'DumpDMDTxt'),
        ('Plugin.DMDUtil', 'DumpDMDRaw'),
        ('Plugin.DMDUtil', 'FindDisplays'),
        ('Plugin.DMDUtil', 'DMDServer'),
        ('Plugin.DMDUtil', 'DMDServerAddr'),
        ('Plugin.DMDUtil', 'DMDServerPort'),
    ],

    'DOF': [],

    'FlexDMD': [],

    'PinMAME': [
        ('Plugin.PinMAME', 'PinMAMEPath'),
        ('Plugin.PinMAME', 'Cheat'),
        ('Plugin.PinMAME', 'Sound'),
    ],

    'PUP': [
        ('Plugin.PUP', 'PUPFolder'),
    ],

    'RemoteControl': [],

    'Serum': [
        ('Plugin.Serum', 'CRZFolder'),
    ],

    'ScoreView': [],  # its options live in [ScoreView] (below)

    'WMP': [],
}

# [ScoreView] options (shown when Plugin.ScoreView.Enable = 1)
SCOREVIEW_FIELDS = {
    'ScoreViewDisplay':        ('ScoreView', 'ScoreViewDisplay'),
    'ScoreViewFullScreen':     ('ScoreView', 'ScoreViewFullScreen'),
    'ScoreViewOutput':         ('ScoreView', 'ScoreViewOutput'),  # combobox 0..2
    'ScoreViewWndX':           ('ScoreView', 'ScoreViewWndX'),
    'ScoreViewWndY':           ('ScoreView', 'ScoreViewWndY'),
    'ScoreViewWidth':          ('ScoreView', 'ScoreViewWidth'),
    'ScoreViewHeight':         ('ScoreView', 'ScoreViewHeight'),
    'Priority.B2SLegacyDMD':   ('ScoreView', 'Priority.B2SLegacyDMD'),
    'Priority.ScoreView':      ('ScoreView', 'Priority.ScoreView'),
}

# ----- DOF / Controller routing (visible when Plugin.DOF.Enable = 1) -----
DOF_CONTROLLER_FIELDS = {
    'DOFContactors':   ('Controller', 'DOFContactors'),
    'DOFKnocker':      ('Controller', 'DOFKnocker'),
    'DOFChimes':       ('Controller', 'DOFChimes'),
    'DOFBell':         ('Controller', 'DOFBell'),
    'DOFGear':         ('Controller', 'DOFGear'),
    'DOFShaker':       ('Controller', 'DOFShaker'),
    'DOFFlippers':     ('Controller', 'DOFFlippers'),
    'DOFTargets':      ('Controller', 'DOFTargets'),
    'DOFDroptargets':  ('Controller', 'DOFDroptargets'),
}

# Combobox: 0=Sound FX, 1=DOF, 2=Both (store/read as INDEX string, e.g., '0','1','2')
DOF_ROUTING_OPTIONS = ['Sound FX', 'DOF', 'Both']


# NUDGE tab: ui_id -> (section, option)
NUDGE_FIELDS = {
    # Nudge
    'LRAxis':                 ('Player', 'LRAxis'),
    'LRAxisFlip':             ('Player', 'LRAxisFlip'),
    'UDAxis':                 ('Player', 'UDAxis'),
    'UDAxisFlip':             ('Player', 'UDAxisFlip'),
    'PBWEnabled':             ('Player', 'PBWEnabled'),
    'PBWNormalMount':         ('Player', 'PBWNormalMount'),
    'PBWDefaultLayout':       ('Player', 'PBWDefaultLayout'),
    'PBWRotationCB':          ('Player', 'PBWRotationCB'),
    'PBWRotationvalue':       ('Player', 'PBWRotationvalue'),
    'PBWAccelGainX':          ('Player', 'PBWAccelGainX'),
    'PBWAccelGainY':          ('Player', 'PBWAccelGainY'),
    'PBWAccelMaxX':           ('Player', 'PBWAccelMaxX'),
    'PBWAccelMaxY':           ('Player', 'PBWAccelMaxY'),
    'EnableNudgeFilter':      ('Player', 'EnableNudgeFilter'),
    'AccelVelocityInput':     ('Player', 'AccelVelocityInput'),

    # Tilt plumb
    'TiltSensCB':             ('Player', 'TiltSensCB'),
    'TiltSensValue':          ('Player', 'TiltSensValue'),
    'TiltInertia':            ('Player', 'TiltInertia'),

    # Plunger
    'PlungerAxis':            ('Player', 'PlungerAxis'),
    'ReversePlungerAxis':     ('Player', 'ReversePlungerAxis'),
    'DeadZone':               ('Player', 'DeadZone'),
    'PlungerRetract':         ('Player', 'PlungerRetract'),

    # Behavior while playing
    'EnableMouseInPlayer':        ('Player', 'EnableMouseInPlayer'),
    'EnableCameraModeFlyAround':  ('Player', 'EnableCameraModeFlyAround'),
}

# BUTTONS tab: ui_id -> (section, option)
# The tab splits into two groups: JOYSTICK_MAPPINGS and KEYBOARD_MAPPINGS.
# Since the INI names are exactly the ids, map 1:1 to ('Player', <key>).

JOYSTICK_MAPPINGS = [
    "JoyLFlipKey", "JoyRFlipKey", "JoyStagedLFlipKey", "JoyStagedRFlipKey",
    "JoyPlungerKey", "JoyAddCreditKey", "JoyAddCredit2Key", "JoyLMagnaSave",
    "JoyRMagnaSave", "JoyStartGameKey", "JoyExitGameKey", "JoyFrameCount",
    "JoyVolumeUp", "JoyVolumeDown", "JoyLTiltKey", "JoyCTiltKey",
    "JoyRTiltKey", "JoyMechTiltKey", "JoyDebugKey", "JoyDebuggerKey",
    "JoyCustom1", "JoyCustom2", "JoyCustom3", "JoyCustom4", "JoyPMBuyIn",
    "JoyPMCoin3", "JoyPMCoin4", "JoyPMCoinDoor", "JoyPMCancel", "JoyPMDown",
    "JoyPMUp", "JoyPMEnter", "JoyLockbarKey", "JoyTableRecenterKey",
    "JoyTableUpKey", "JoyTableDownKey", "JoyPauseKey", "JoyTweakKey",
]

KEYBOARD_MAPPINGS = [
    "DisableESC", "LFlipKey", "RFlipKey", "StagedLFlipKey", "StagedRFlipKey",
    "LTiltKey", "RTiltKey", "CTiltKey", "PlungerKey", "FrameCount",
    "AddCreditKey", "AddCredit2Key", "LMagnaSave", "RMagnaSave",
    "StartGameKey", "ExitGameKey", "DebugKey", "DebuggerKey",
    "Custom1", "Custom2", "Custom3", "Custom4", "PMBuyIn", "PMCoin3",
    "PMCoin4", "PMCoinDoor", "PMCancel", "PMDown", "PMUp", "PMEnter",
    "VolumeUp", "VolumeDown", "LockbarKey", "Enable3DKey", "TableRecenterKey",
    "TableUpKey", "TableDownKey", "EscapeKey", "PauseKey", "TweakKey",
]

BUTTONS_JOYSTICK_FIELDS = {name: ('Player', name) for name in JOYSTICK_MAPPINGS}
BUTTONS_KEYBOARD_FIELDS = {name: ('Player', name) for name in KEYBOARD_MAPPINGS}


# VR tab: ui_id -> (section, option) in [PlayerVR]
VR_FIELDS = {
    # VR device setting
    'AskToTurnOn': ('PlayerVR', 'AskToTurnOn'),

    # OpenXR settings
    'ResFactor': ('PlayerVR', 'ResFactor'),

    # OpenVR settings
    'ScaleToFixedWidth': ('PlayerVR', 'ScaleToFixedWidth'),
    'ScaleAbsolute': ('PlayerVR', 'ScaleAbsolute'),
    'ScaleRelative': ('PlayerVR', 'ScaleRelative'),
    'NearPlane': ('PlayerVR', 'NearPlane'),
    'EyeFBFormat': ('PlayerVR', 'EyeFBFormat'),

    # Table position
    'Slope': ('PlayerVR', 'Slope'),
    'Orientation': ('PlayerVR', 'Orientation'),
    'TableX': ('PlayerVR', 'TableX'),
    'TableY': ('PlayerVR', 'TableY'),
    'TableZ': ('PlayerVR', 'TableZ'),

    # Preview
    'VRPreviewDisabled': ('PlayerVR', 'VRPreviewDisabled'),
    'VRPreview': ('PlayerVR', 'VRPreview'),
    'ShrinkPreview': ('PlayerVR', 'ShrinkPreview'),
    'WindowPosX': ('PlayerVR', 'WindowPosX'),
    'WindowPosY': ('PlayerVR', 'WindowPosY'),
    'PreviewWidth': ('PlayerVR', 'PreviewWidth'),
    'PreviewHeight': ('PlayerVR', 'PreviewHeight'),
}
