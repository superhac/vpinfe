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
    # Runtime state that happens to live in the config file - a last-played pointer, a
    # cache marker. Nobody sets these, so nothing should offer them as settings.
    internal: bool = False


CONFIG_OPTIONS: tuple[ConfigOption, ...] = (
    ConfigOption("Displays", "bgscreenid", "int", '',
                 label='Backglass Monitor ID'),
    ConfigOption("Displays", "dmdscreenid", "int", '',
                 label='DMD Monitor ID'),
    ConfigOption("Displays", "bgwindowoverride", "string", '',
                 label='Backglass Window Override (x,y,width,height)'),
    ConfigOption("Displays", "dmdwindowoverride", "string", '',
                 label='DMD Window Override (x,y,width,height)'),
    ConfigOption("Displays", "playfieldscreenid", "int", '0',
                 label='Playfield Monitor ID'),
    ConfigOption("Displays", "playfieldorientation", "choice", 'landscape',
                 label='Playfield Monitor Mounting',
                 description='How the playfield screen is physically mounted. Portrait means it is '
                             'turned on its side in the cabinet. This does not rotate anything by '
                             'itself - it tells themes what shape to lay out for.',
                 choices=('landscape', 'portrait')),
    ConfigOption("Displays", "playfieldrotation", "choice", '0',
                 label='Rotate VPinFE Display',
                 description='How far VPinFE turns its own display so it faces the player. Leave '
                             'at 0 if your operating system already rotates this screen.',
                 choices=('0', '90', '180', '270')),
    ConfigOption("Displays", "cabmode", "bool", 'false',
                 label='Cabinet Mode',
                 description='Presents VPinFE for playing standing at a cabinet: larger text '
                             'and targets, and no controls that need a mouse. It does not '
                             'rotate anything.'),
    ConfigOption("Settings", "vpxbinpath", "string", '',
                 label='VPX Executable Path',
                 description='Full path to the Visual Pinball executable VPinFE launches.'),
    ConfigOption("Settings", "vpxlaunchenv", "string", '',
                 label='VPX Launch Environment'),
    ConfigOption("Settings", "globalinioverride", "string", '',
                 label='Global ini Override (/home/test/mysuper.ini)'),
    ConfigOption("Settings", "globaltableinioverrideenabled", "bool", 'false',
                 label='Global tableini Override Enabled'),
    ConfigOption("Settings", "globaltableinioverridemask", "string", '',
                 label='Global tableini Override Mask'),
    ConfigOption("Settings", "gamerootdir", "string", '',
                 label='Tables Directory',
                 description='The folder holding your table folders, one folder per game.'),
    ConfigOption("Settings", "vpxinipath", "string", '',
                 label='VPX Ini Path',
                 description='Path to VPinballX.ini, which VPinFE reads for the key mappings '
                             'the Remote page sends.'),
    ConfigOption("Settings", "rartoolpath", "string", '',
                 label='RAR Tool Path (unar/unrar, blank = auto-detect)'),
    ConfigOption("Settings", "vpxlogdeleteonstart", "bool", 'false',
                 label='Delete VPinball Log On Table Start'),
    ConfigOption("Settings", "theme", "string", 'Revolution',
                 label='Active Theme'),
    ConfigOption("Settings", "startup_collection", "string", '',
                 label='Default Startup Collection'),
    ConfigOption("Settings", "autoupdatemediaonstartup", "bool", 'false',
                 label='Auto Update Media On Startup'),
    ConfigOption("Settings", "splashscreen", "bool", 'false',
                 label='Enable splashscreen'),
    ConfigOption("Settings", "muteaudio", "bool", 'false',
                 label='Mute Frontend Audio'),
    ConfigOption("Settings", "chromeoptions", "string", '',
                 label='Additional Chrome Options'),
    ConfigOption("Settings", "chromeoptionsexclude", "string", ''),
    ConfigOption("Settings", "disabledefaultchromeoptions", "bool", 'false',
                 label='Disable Default Chrome Options'),
    ConfigOption("Settings", "MMhideQuitButton", "bool", 'false',
                 label='Hide Quit from MainMenu'),
    ConfigOption("Settings", "restorelastgame", "bool", 'true',
                 label='Restore Last Table'),
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
    ConfigOption("Media", "playfieldvariant", "choice", 'table',
                 label='Table Type',
                 description="Which playfield artwork this library holds: table.png, or "
                             "fss.png for art captured in Visual Pinball's Full Single "
                             "Screen mode.",
                 choices=('table', 'fss')),
    ConfigOption("Media", "playfieldresolution", "choice", '4k',
                 label='Default Table Resolution',
                 choices=('4k', '1k')),
    ConfigOption("Media", "playfieldvideoresolution", "choice", '1k',
                 label='Default Table Video Resolution',
                 choices=('4k', '1k')),
    ConfigOption("Media", "defaultmissingmediaimg", "string", '',
                 label='Default Missing Media Image'),
    ConfigOption("Media", "thumbcachemaxmb", "int", '500',
                 label='Thumbnail Cache Max (MB)'),
    ConfigOption("Media", "playfieldmediapriority", "choice", 'video',
                 label='Table Media Priority',
                 choices=('video', 'image')),
    ConfigOption("Media", "playfieldmediarotation", "choice", 'auto',
                 description='How far to turn playfield artwork so it fills the screen. auto '
                             'measures each image and turns only when it disagrees with the '
                             'surface.',
                 choices=('auto', '0', '90', '180', '270')),
    ConfigOption("Media", "bgmediapriority", "choice", 'video',
                 label='Backglass Media Priority',
                 choices=('video', 'image')),
    ConfigOption("Media", "dmdmediapriority", "choice", 'video',
                 label='DMD Media Priority',
                 choices=('video', 'image')),
    ConfigOption("Media", "realdmdmediapriority", "choice", 'color',
                 label='Real DMD Priority',
                 choices=('color', 'video', 'image')),
    ConfigOption("VPSdb", "last", "string", '',
                 internal=True),
    ConfigOption("State", "lastgame", "string", '',
                 internal=True),
    ConfigOption("pinmame-score-parser", "romsupdatesha", "string", '',
                 internal=True),
    ConfigOption("Network", "themeassetsport", "int", '8000',
                 label='Theme Server Port'),
    ConfigOption("Network", "manageruiport", "int", '8001',
                 label='Manager UI Port'),
    ConfigOption("DOF", "enabledof", "bool", 'false',
                 label='Enable DOF'),
    ConfigOption("DOF", "dofconfigtoolapikey", "string", '',
                 label='DOF Config Tool API Key'),
    ConfigOption("libdmdutil", "enabled", "bool", 'false',
                 label='Enabled'),
    ConfigOption("libdmdutil", "pin2dmdenabled", "bool", 'false',
                 label='Enable'),
    ConfigOption("libdmdutil", "pixelcadedevice", "string", '',
                 label='PixelcadeDevice'),
    ConfigOption("libdmdutil", "zedmddevice", "string", '',
                 label='ZeDMDDevice'),
    ConfigOption("libdmdutil", "zedmdwifiaddr", "string", '',
                 label='ZeDMDWiFiAddr'),
    ConfigOption("Mobile", "deviceip", "string", '',
                 label='Mobile Device IP'),
    ConfigOption("Mobile", "deviceport", "int", '2112',
                 label='Mobile Device Port'),
    ConfigOption("Mobile", "chunksize", "int", '1048576',
                 label='Mobile Chunk Size'),
    ConfigOption("Mobile", "renamemasktodefaultini", "bool", 'false',
                 label='Enable Rename Mask To Default INI'),
    ConfigOption("Mobile", "renamemasktodefaultinimask", "string", '',
                 label='Rename Mask To Default INI Mask'),
    ConfigOption("vpinplay", "synconexit", "bool", 'false',
                 label='Sync on Exit'),
    ConfigOption("vpinplay", "apiendpoint", "string", 'https://api.vpinplay.com:8888',
                 label='API Endpoint'),
    ConfigOption("vpinplay", "userid", "string", '',
                 label='User ID'),
    ConfigOption("vpinplay", "initials", "string", '',
                 label='Initials'),
    ConfigOption("vpinplay", "machineid", "string", '',
                 label='Machine ID'),)


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


def defaults() -> dict[str, dict[str, str]]:
    """The nested section/key/value shape the config store fills a new file from."""
    out: dict[str, dict[str, str]] = {}
    for entry in CONFIG_OPTIONS:
        out.setdefault(entry.section, {})[entry.key] = entry.default
    return out
