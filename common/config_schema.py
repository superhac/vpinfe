"""Every setting VPinFE has, declared once.

One place says what a setting is called, what it accepts, what it defaults to and what
it means, so the config file, the Manager UI and anything reading us over HTTP describe
it the same way. Before this the answers were spread over three modules: defaults in the
config store, labels and help text hardcoded in the Manager UI page, and legal values
written into the widget that rendered them.

`default` is the string the ini writes today, so this file can be checked against the
store it replaces rather than trusted.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigOption:
    """One setting. `type` says how to read it, not how to store it."""

    section: str
    key: str
    type: str
    default: str
    label: str = ""
    description: str = ""
    choices: tuple[str, ...] = ()
    # Spellings a stored file or an old call site may still use. Canonical-plus-alias is
    # how VPinFE already renames ini keys, and how Visual Pinball does it upstream: the
    # file is rewritten to the canonical name, and the old one keeps resolving forever.
    aliases: tuple[str, ...] = ()
    # Runtime state that happens to live in the config file - a last-played pointer, a
    # cache marker. Nobody sets these, so nothing should offer them as settings.
    internal: bool = False


CONFIG_OPTIONS: tuple[ConfigOption, ...] = (
    ConfigOption("Displays", "bg_screen_id", "int", '',
                 label='Backglass Monitor ID',
                 aliases=('bgscreenid',)),
    ConfigOption("Displays", "dmd_screen_id", "int", '',
                 label='DMD Monitor ID',
                 aliases=('dmdscreenid',)),
    ConfigOption("Displays", "bg_window_override", "string", '',
                 label='Backglass Window Override (x,y,width,height)',
                 aliases=('bgwindowoverride',)),
    ConfigOption("Displays", "dmd_window_override", "string", '',
                 label='DMD Window Override (x,y,width,height)',
                 aliases=('dmdwindowoverride',)),
    ConfigOption("Displays", "playfield_screen_id", "int", '0',
                 label='Playfield Monitor ID',
                 aliases=('playfieldscreenid',)),
    ConfigOption("Displays", "playfield_orientation", "choice", 'landscape',
                 label='Playfield Monitor Mounting',
                 description='How the playfield screen is physically mounted. Portrait means it is '
                             'turned on its side in the cabinet. This does not rotate anything by '
                             'itself - it tells themes what shape to lay out for.',
                 choices=('landscape', 'portrait'),
                 aliases=('playfieldorientation',)),
    ConfigOption("Displays", "playfield_rotation", "choice", '0',
                 label='Rotate VPinFE Display',
                 description='How far VPinFE turns its own display so it faces the player. Leave '
                             'at 0 if your operating system already rotates this screen.',
                 choices=('0', '90', '180', '270'),
                 aliases=('playfieldrotation',)),
    ConfigOption("Displays", "cab_mode", "bool", 'false',
                 label='Cabinet Mode',
                 description='Presents VPinFE for playing standing at a cabinet: larger text and '
                             'targets, and no controls that need a mouse. It does not rotate '
                             'anything.',
                 aliases=('cabmode',)),
    ConfigOption("Settings", "vpx_bin_path", "string", '',
                 label='VPX Executable Path',
                 description='Full path to the Visual Pinball executable VPinFE launches.',
                 aliases=('vpxbinpath',)),
    ConfigOption("Settings", "vpx_launch_env", "string", '',
                 label='VPX Launch Environment',
                 aliases=('vpxlaunchenv',)),
    ConfigOption("Settings", "global_ini_override", "string", '',
                 label='Global ini Override (/home/test/mysuper.ini)',
                 aliases=('globalinioverride',)),
    ConfigOption("Settings", "global_game_ini_override_enabled", "bool", 'false',
                 label='Global tableini Override Enabled',
                 aliases=('globaltableinioverrideenabled',)),
    ConfigOption("Settings", "global_game_ini_override_mask", "string", '',
                 label='Global tableini Override Mask',
                 aliases=('globaltableinioverridemask',)),
    ConfigOption("Settings", "game_root_dir", "string", '',
                 label='Tables Directory',
                 description='The folder holding your table folders, one folder per game.',
                 aliases=('gamerootdir',)),
    ConfigOption("Settings", "vpx_ini_path", "string", '',
                 label='VPX Ini Path',
                 description='Path to VPinballX.ini, which VPinFE reads for the key mappings the '
                             'Remote page sends.',
                 aliases=('vpxinipath',)),
    ConfigOption("Settings", "rar_tool_path", "string", '',
                 label='RAR Tool Path (unar/unrar, blank = auto-detect)',
                 aliases=('rartoolpath',)),
    ConfigOption("Settings", "vpx_log_delete_on_start", "bool", 'false',
                 label='Delete VPinball Log On Table Start',
                 aliases=('vpxlogdeleteonstart',)),
    ConfigOption("Settings", "theme", "string", 'Revolution',
                 label='Active Theme'),
    ConfigOption("Settings", "startup_collection", "string", '',
                 label='Default Startup Collection'),
    ConfigOption("Settings", "auto_update_media_on_startup", "bool", 'false',
                 label='Auto Update Media On Startup',
                 aliases=('autoupdatemediaonstartup',)),
    ConfigOption("Settings", "splashscreen", "bool", 'false',
                 label='Enable splashscreen'),
    ConfigOption("Settings", "mute_audio", "bool", 'false',
                 label='Mute Frontend Audio',
                 aliases=('muteaudio',)),
    ConfigOption("Settings", "chrome_options", "string", '',
                 label='Additional Chrome Options',
                 aliases=('chromeoptions',)),
    ConfigOption("Settings", "chrome_options_exclude", "string", '',
                 aliases=('chromeoptionsexclude',)),
    ConfigOption("Settings", "disable_default_chrome_options", "bool", 'false',
                 label='Disable Default Chrome Options',
                 aliases=('disabledefaultchromeoptions',)),
    ConfigOption("Settings", "hide_quit_button", "bool", 'false',
                 label='Hide Quit from MainMenu',
                 aliases=('MMhideQuitButton',)),
    ConfigOption("Settings", "restore_last_game", "bool", 'true',
                 label='Restore Last Table',
                 aliases=('restorelastgame',)),
    ConfigOption("Input", "joyleft", "string", '',
                 label='Gamepad Left'),
    ConfigOption("Input", "keyleft", "string", 'ArrowLeft,ShiftLeft',
                 label='Keyboard Left'),
    ConfigOption("Input", "joyright", "string", '',
                 label='Gamepad Right'),
    ConfigOption("Input", "keyright", "string", 'ArrowRight,ShiftRight',
                 label='Keyboard Right'),
    ConfigOption("Input", "joyup", "string", '',
                 label='Gamepad Up'),
    ConfigOption("Input", "keyup", "string", 'ArrowUp',
                 label='Keyboard Up'),
    ConfigOption("Input", "joydown", "string", '',
                 label='Gamepad Down'),
    ConfigOption("Input", "keydown", "string", 'ArrowDown',
                 label='Keyboard Down'),
    ConfigOption("Input", "joypageup", "string", '',
                 label='Gamepad Page Up'),
    ConfigOption("Input", "keypageup", "string", 'PageUp',
                 label='Keyboard Page Up'),
    ConfigOption("Input", "joypagedown", "string", '',
                 label='Gamepad Page Down'),
    ConfigOption("Input", "keypagedown", "string", 'PageDown',
                 label='Keyboard Page Down'),
    ConfigOption("Input", "pagingtype", "choice", 'alpha',
                 label='Paging Type',
                 choices=('alpha', 'number')),
    ConfigOption("Input", "pagingsize", "int", '10',
                 label='Paging Size'),
    ConfigOption("Input", "joyselect", "string", '',
                 label='Gamepad Select'),
    ConfigOption("Input", "keyselect", "string", 'Enter',
                 label='Keyboard Select'),
    ConfigOption("Input", "joymenu", "string", '',
                 label='Gamepad Menu'),
    ConfigOption("Input", "keymenu", "string", 'm',
                 label='Keyboard Menu'),
    ConfigOption("Input", "joyback", "string", '',
                 label='Gamepad Back'),
    ConfigOption("Input", "keyback", "string", 'b',
                 label='Keyboard Back'),
    ConfigOption("Input", "joytutorial", "string", '',
                 label='Gamepad Tutorial'),
    ConfigOption("Input", "keytutorial", "string", 't',
                 label='Keyboard Tutorial'),
    ConfigOption("Input", "joyexit", "string", '',
                 label='Gamepad Exit'),
    ConfigOption("Input", "keyexit", "string", 'Escape,q',
                 label='Keyboard Exit'),
    ConfigOption("Input", "joycollectionmenu", "string", '',
                 label='Gamepad Collection Menu'),
    ConfigOption("Input", "keycollectionmenu", "string", 'c',
                 label='Keyboard Collection Menu'),
    ConfigOption("Logger", "level", "choice", 'debug',
                 label='Log Verbosity',
                 choices=('debug', 'info', 'warning', 'error')),
    ConfigOption("Logger", "console", "bool", 'true',
                 label='Console Logging'),
    ConfigOption("Media", "playfield_variant", "choice", 'table',
                 label='Table Type',
                 description='Which playfield artwork this library holds: table.png, or fss.png '
                             "for art captured in Visual Pinball's Full Single Screen mode.",
                 choices=('table', 'fss'),
                 aliases=('playfieldvariant',)),
    ConfigOption("Media", "playfield_resolution", "choice", '4k',
                 label='Default Table Resolution',
                 choices=('4k', '1k'),
                 aliases=('playfieldresolution',)),
    ConfigOption("Media", "playfield_video_resolution", "choice", '1k',
                 label='Default Table Video Resolution',
                 choices=('4k', '1k'),
                 aliases=('playfieldvideoresolution',)),
    ConfigOption("Media", "default_missing_media_image", "string", '',
                 label='Default Missing Media Image',
                 aliases=('defaultmissingmediaimg',)),
    ConfigOption("Media", "thumb_cache_max_mb", "int", '500',
                 label='Thumbnail Cache Max (MB)',
                 aliases=('thumbcachemaxmb',)),
    ConfigOption("Media", "playfield_media_priority", "choice", 'video',
                 label='Table Media Priority',
                 choices=('video', 'image'),
                 aliases=('playfieldmediapriority',)),
    ConfigOption("Media", "playfield_media_rotation", "choice", 'auto',
                 description='How far to turn playfield artwork so it fills the screen. auto '
                             'measures each image and turns only when it disagrees with the '
                             'surface.',
                 choices=('auto', '0', '90', '180', '270'),
                 aliases=('playfieldmediarotation',)),
    ConfigOption("Media", "bg_media_priority", "choice", 'video',
                 label='Backglass Media Priority',
                 choices=('video', 'image'),
                 aliases=('bgmediapriority',)),
    ConfigOption("Media", "dmd_media_priority", "choice", 'video',
                 label='DMD Media Priority',
                 choices=('video', 'image'),
                 aliases=('dmdmediapriority',)),
    ConfigOption("Media", "realdmd_media_priority", "choice", 'color',
                 label='Real DMD Priority',
                 choices=('color', 'video', 'image'),
                 aliases=('realdmdmediapriority',)),
    ConfigOption("VPSdb", "last", "string", '',
                 internal=True),
    ConfigOption("State", "last_game", "string", '',
                 aliases=('lastgame',),
                 internal=True),
    ConfigOption("pinmame-score-parser", "roms_update_sha", "string", '',
                 aliases=('romsupdatesha',),
                 internal=True),
    ConfigOption("Network", "theme_assets_port", "int", '8000',
                 label='Theme Server Port',
                 aliases=('themeassetsport',)),
    ConfigOption("Network", "manager_ui_port", "int", '8001',
                 label='Manager UI Port',
                 aliases=('manageruiport',)),
    ConfigOption("DOF", "enable_dof", "bool", 'false',
                 label='Enable DOF',
                 aliases=('enabledof',)),
    ConfigOption("DOF", "dof_config_tool_api_key", "string", '',
                 label='DOF Config Tool API Key',
                 aliases=('dofconfigtoolapikey',)),
    ConfigOption("libdmdutil", "enabled", "bool", 'false',
                 label='Enabled'),
    ConfigOption("libdmdutil", "pin2dmd_enabled", "bool", 'false',
                 label='Enable',
                 aliases=('pin2dmdenabled',)),
    ConfigOption("libdmdutil", "pixelcade_device", "string", '',
                 label='PixelcadeDevice',
                 aliases=('pixelcadedevice',)),
    ConfigOption("libdmdutil", "zedmd_device", "string", '',
                 label='ZeDMDDevice',
                 aliases=('zedmddevice',)),
    ConfigOption("libdmdutil", "zedmd_wifi_address", "string", '',
                 label='ZeDMDWiFiAddr',
                 aliases=('zedmdwifiaddr',)),
    ConfigOption("Mobile", "device_ip", "string", '',
                 label='Mobile Device IP',
                 aliases=('deviceip',)),
    ConfigOption("Mobile", "device_port", "int", '2112',
                 label='Mobile Device Port',
                 aliases=('deviceport',)),
    ConfigOption("Mobile", "chunk_size", "int", '1048576',
                 label='Mobile Chunk Size',
                 aliases=('chunksize',)),
    ConfigOption("Mobile", "rename_mask_to_default_ini", "bool", 'false',
                 label='Enable Rename Mask To Default INI',
                 aliases=('renamemasktodefaultini',)),
    ConfigOption("Mobile", "rename_mask_to_default_ini_mask", "string", '',
                 label='Rename Mask To Default INI Mask',
                 aliases=('renamemasktodefaultinimask',)),
    ConfigOption("vpinplay", "sync_on_exit", "bool", 'false',
                 label='Sync on Exit',
                 aliases=('synconexit',)),
    ConfigOption("vpinplay", "api_endpoint", "string", 'https://api.vpinplay.com:8888',
                 label='API Endpoint',
                 aliases=('apiendpoint',)),
    ConfigOption("vpinplay", "user_id", "string", '',
                 label='User ID',
                 aliases=('userid',)),
    ConfigOption("vpinplay", "initials", "string", '',
                 label='Initials'),
    ConfigOption("vpinplay", "machine_id", "string", '',
                 label='Machine ID',
                 aliases=('machineid',)),
)


def options() -> tuple[ConfigOption, ...]:
    """Every option, in declaration order."""
    return CONFIG_OPTIONS


def settable() -> tuple[ConfigOption, ...]:
    """Everything a person is meant to set - what a UI or a doc should show."""
    return tuple(option for option in CONFIG_OPTIONS if not option.internal)


def option(section: str, key: str) -> ConfigOption | None:
    for candidate in CONFIG_OPTIONS:
        if candidate.section == section and candidate.key == key:
            return candidate
    return None


def canonical(section: str, key: str) -> str:
    """The name this setting is stored under, given any spelling it has ever had."""
    wanted = str(key or "").strip().lower()
    for candidate in CONFIG_OPTIONS:
        if candidate.section != section:
            continue
        if candidate.key.lower() == wanted:
            return candidate.key
        if any(a.lower() == wanted for a in candidate.aliases):
            return candidate.key
    return key


def spellings(section: str, key: str) -> tuple[str, ...]:
    """Every name this setting has gone by, canonical first.

    A reader tries them in order because a parser is not always one the store filled:
    a caller can hand-build one, and a stored file written by an older build has the
    old names in it until the store rewrites them.
    """
    wanted = str(key or "").strip().lower()
    for candidate in CONFIG_OPTIONS:
        if candidate.section != section:
            continue
        names = (candidate.key, *candidate.aliases)
        if any(n.lower() == wanted for n in names):
            return names
    return (key,)


def by_key(key: str) -> ConfigOption | None:
    """Look up without knowing the section.

    Safe because no key is used in two sections, which a test pins - and needed because
    configparser lowercases option names on read, so a caller holding a key off the file
    has neither the section nor the original casing.
    """
    wanted = str(key or "").strip().lower()
    for candidate in CONFIG_OPTIONS:
        if candidate.key.lower() == wanted:
            return candidate
        if any(a.lower() == wanted for a in candidate.aliases):
            return candidate
    return None


def label_for(key: str) -> str:
    """What to call a setting on screen. Falls back to a readable form of the key."""
    entry = by_key(key)
    if entry is not None and entry.label:
        return entry.label
    return str(key or "").replace("_", " ").title()


def description_for(key: str) -> str:
    """One line explaining a setting, or "" when nobody has written one yet."""
    entry = by_key(key)
    return entry.description if entry is not None else ""


def defaults() -> dict[str, dict[str, str]]:
    """The nested section/key/value shape the config store fills a new file from."""
    out: dict[str, dict[str, str]] = {}
    for entry in CONFIG_OPTIONS:
        out.setdefault(entry.section, {})[entry.key] = entry.default
    return out
