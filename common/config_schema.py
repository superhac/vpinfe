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

from common import input_actions


def _input_options() -> tuple[ConfigOption, ...]:
    """`[input]` comes from the action registry, so the two cannot disagree.

    One option per action holding an ordered list of bindings - not a key per device,
    because a binding names its own device and a chord names two.
    """
    out = [ConfigOption(input_actions.SECTION, action.name, "list",
                        ",".join(action.bindings), label=action.label,
                        legacy=tuple(("Input", old) for old in action.legacy))
           for action in input_actions.actions()]
    # Not actions: how the paging actions step, which is a setting about them.
    out.append(ConfigOption(input_actions.SECTION, "paging_type", "choice", 'alpha',
                            label='Paging Type', choices=('alpha', 'numeric'),
                            legacy=(("Input", "pagingtype"),)))
    out.append(ConfigOption(input_actions.SECTION, "paging_size", "int", '10',
                            label='Paging Size', legacy=(("Input", "pagingsize"),)))
    return tuple(out)


# Sections renamed wholesale, old name to new. A section rename is not the same thing as
# `legacy` below: that records a setting moving between sections, this records every
# setting in a section staying put while the section itself is respelled, so one entry
# here covers keys and aliases alike.
SECTION_RENAMES = {
    'Settings': 'general',
    'Displays': 'displays',
    'Logger': 'logger',
    'Media': 'media',
    'Mobile': 'mobile',
    'Network': 'network',
    'State': 'state',
    'VPSdb': 'vpsdb',
    'DOF': 'dof',
    'pinmame-score-parser': 'pinmame_score_parser',
}


def canonical_section(section: str) -> str:
    """The section this one is called now. Any current name is returned unchanged."""
    return SECTION_RENAMES.get(str(section or ""), str(section or ""))


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
    # Whole former locations, section and key, for a setting that moved between sections.
    # `aliases` covers a key that only changed spelling; this covers one that also moved,
    # which is what per-window config did to the fourteen prefix-simulated keys.
    legacy: tuple[tuple[str, str], ...] = ()
    # Runtime state that happens to live in the config file - a last-played pointer, a
    # cache marker. Nobody sets these, so nothing should offer them as settings.
    internal: bool = False


CONFIG_OPTIONS: tuple[ConfigOption, ...] = (
    ConfigOption("windows.backglass", "screen_id", "int", '',
                 label='Backglass Monitor ID',
                 legacy=(('Displays', 'bg_screen_id'), ('Displays', 'bgscreenid'))),
    ConfigOption("windows.scoreview", "screen_id", "int", '',
                 label='DMD Monitor ID',
                 legacy=(('Displays', 'dmd_screen_id'), ('Displays', 'dmdscreenid'))),
    ConfigOption("windows.backglass", "window_override", "string", '',
                 label='Backglass Window Override (x,y,width,height)',
                 legacy=(('Displays', 'bg_window_override'), ('Displays', 'bgwindowoverride'))),
    ConfigOption("windows.scoreview", "window_override", "string", '',
                 label='DMD Window Override (x,y,width,height)',
                 legacy=(('Displays', 'dmd_window_override'), ('Displays', 'dmdwindowoverride'))),
    ConfigOption("windows.playfield", "screen_id", "int", '0',
                 label='Playfield Monitor ID',
                 legacy=(('Displays', 'playfield_screen_id'), ('Displays', 'playfieldscreenid'))),
    ConfigOption("windows.playfield", "orientation", "choice", 'landscape',
                 label='Playfield Monitor Mounting',
                 description='How the playfield screen is physically mounted. Portrait means it is '
                             'turned on its side in the cabinet. This does not rotate anything by '
                             'itself - it tells themes what shape to lay out for.',
                 choices=('landscape', 'portrait'),
                 legacy=(
                     ('Displays', 'playfield_orientation'),
                     ('Displays', 'playfieldorientation'),
                 )),
    ConfigOption("windows.playfield", "rotation", "choice", '0',
                 label='Rotate VPinFE Display',
                 description='How far VPinFE turns its own display so it faces the player. Leave '
                             'at 0 if your operating system already rotates this screen.',
                 choices=('0', '90', '180', '270'),
                 legacy=(('Displays', 'playfield_rotation'), ('Displays', 'playfieldrotation'))),
    ConfigOption("displays", "cab_mode", "bool", 'false',
                 label='Cabinet Mode',
                 description='Presents VPinFE for playing standing at a cabinet: larger text and '
                             'targets, and no controls that need a mouse. It does not rotate '
                             'anything.',
                 aliases=('cabmode',)),
    ConfigOption("general", "vpx_bin_path", "string", '',
                 label='VPX Executable Path',
                 description='Full path to the Visual Pinball executable VPinFE launches.',
                 aliases=('vpxbinpath',)),
    ConfigOption("general", "vpx_launch_env", "string", '',
                 label='VPX Launch Environment',
                 aliases=('vpxlaunchenv',)),
    ConfigOption("general", "global_ini_override", "string", '',
                 label='Global ini Override (/home/test/mysuper.ini)',
                 aliases=('globalinioverride',)),
    ConfigOption("general", "global_game_ini_override_enabled", "bool", 'false',
                 label='Global tableini Override Enabled',
                 aliases=('globaltableinioverrideenabled',)),
    ConfigOption("general", "global_game_ini_override_mask", "string", '',
                 label='Global tableini Override Mask',
                 aliases=('globaltableinioverridemask',)),
    ConfigOption("general", "game_root_dir", "string", '',
                 label='Tables Directory',
                 description='The folder holding your table folders, one folder per game.',
                 aliases=('gamerootdir',)),
    ConfigOption("general", "vpx_ini_path", "string", '',
                 label='VPX Ini Path',
                 description='Path to VPinballX.ini, which VPinFE reads for the key mappings the '
                             'Remote page sends.',
                 aliases=('vpxinipath',)),
    ConfigOption("general", "rar_tool_path", "string", '',
                 label='RAR Tool Path (unar/unrar, blank = auto-detect)',
                 aliases=('rartoolpath',)),
    ConfigOption("general", "vpx_log_delete_on_start", "bool", 'false',
                 label='Delete VPinball Log On Table Start',
                 aliases=('vpxlogdeleteonstart',)),
    ConfigOption("general", "theme", "string", 'Revolution',
                 label='Active Theme'),
    ConfigOption("themes", "registries", "list",
                 'https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json',
                 label='Theme Registries',
                 description='Catalogs to offer themes from, most trusted first. The '
                             'stock registry is an entry like any other, so a mirrored '
                             'or offline install can replace or drop it.'),
    ConfigOption("themes", "repositories", "list", '',
                 label='Theme Repositories',
                 description='Individual theme repos, each one a theme in its own right. '
                             'Resolved before the registries, and named for the repo with '
                             'any vpinfe-theme- prefix removed.'),
    ConfigOption("general", "startup_collection", "string", '',
                 label='Default Startup Collection'),
    ConfigOption("general", "auto_update_media_on_startup", "bool", 'false',
                 label='Auto Update Media On Startup',
                 aliases=('autoupdatemediaonstartup',)),
    ConfigOption("general", "splashscreen", "bool", 'false',
                 label='Enable splashscreen'),
    ConfigOption("general", "mute_audio", "bool", 'false',
                 label='Mute Frontend Audio',
                 aliases=('muteaudio',)),
    ConfigOption("general", "chrome_options", "string", '',
                 label='Additional Chrome Options',
                 aliases=('chromeoptions',)),
    ConfigOption("general", "chrome_options_exclude", "string", '',
                 aliases=('chromeoptionsexclude',)),
    ConfigOption("general", "disable_default_chrome_options", "bool", 'false',
                 label='Disable Default Chrome Options',
                 aliases=('disabledefaultchromeoptions',)),
    ConfigOption("general", "hide_quit_button", "bool", 'false',
                 label='Hide Quit from MainMenu',
                 aliases=('MMhideQuitButton',)),
    ConfigOption("general", "restore_last_game", "bool", 'true',
                 label='Restore Last Table',
                 aliases=('restorelastgame',)),
    ConfigOption("logger", "level", "choice", 'debug',
                 label='Log Verbosity',
                 choices=('debug', 'info', 'warning', 'error')),
    ConfigOption("logger", "console", "bool", 'true',
                 label='Console Logging'),
    ConfigOption("windows.playfield", "variant", "choice", 'table',
                 label='Table Type',
                 description='Which playfield artwork this library holds: table.png, or fss.png '
                             "for art captured in Visual Pinball's Full Single Screen mode.",
                 choices=('table', 'fss'),
                 legacy=(('Media', 'playfield_variant'), ('Media', 'playfieldvariant'))),
    ConfigOption("windows.playfield", "resolution", "choice", '4k',
                 label='Default Table Resolution',
                 choices=('4k', '1k'),
                 legacy=(('Media', 'playfield_resolution'), ('Media', 'playfieldresolution'))),
    ConfigOption("windows.playfield", "video_resolution", "choice", '1k',
                 label='Default Table Video Resolution',
                 choices=('4k', '1k'),
                 legacy=(
                     ('Media', 'playfield_video_resolution'),
                     ('Media', 'playfieldvideoresolution'),
                 )),
    ConfigOption("media", "default_missing_media_image", "string", '',
                 label='Default Missing Media Image',
                 aliases=('defaultmissingmediaimg',)),
    ConfigOption("media", "thumb_cache_max_mb", "int", '500',
                 label='Thumbnail Cache Max (MB)',
                 aliases=('thumbcachemaxmb',)),
    ConfigOption("windows.playfield", "media_priority", "choice", 'video',
                 label='Table Media Priority',
                 choices=('video', 'image'),
                 legacy=(
                     ('Media', 'playfield_media_priority'),
                     ('Media', 'playfieldmediapriority'),
                 )),
    ConfigOption("windows.playfield", "media_rotation", "choice", 'auto',
                 description='How far to turn playfield artwork so it fills the screen. auto '
                             'measures each image and turns only when it disagrees with the '
                             'surface.',
                 choices=('auto', '0', '90', '180', '270'),
                 legacy=(
                     ('Media', 'playfield_media_rotation'),
                     ('Media', 'playfieldmediarotation'),
                 )),
    ConfigOption("windows.backglass", "media_priority", "choice", 'video',
                 label='Backglass Media Priority',
                 choices=('video', 'image'),
                 legacy=(('Media', 'bg_media_priority'), ('Media', 'bgmediapriority'))),
    ConfigOption("windows.scoreview", "media_priority", "choice", 'video',
                 label='DMD Media Priority',
                 choices=('video', 'image'),
                 legacy=(('Media', 'dmd_media_priority'), ('Media', 'dmdmediapriority'))),
    ConfigOption("media", "realdmd_media_priority", "choice", 'color',
                 label='Real DMD Priority',
                 choices=('color', 'video', 'image'),
                 aliases=('realdmdmediapriority',)),
    ConfigOption("vpsdb", "last", "string", '',
                 internal=True),
    ConfigOption("state", "last_game", "string", '',
                 aliases=('lastgame',),
                 internal=True),
    ConfigOption("pinmame_score_parser", "roms_update_sha", "string", '',
                 aliases=('romsupdatesha',),
                 internal=True),
    ConfigOption("network", "theme_assets_port", "int", '8000',
                 label='Theme Server Port',
                 aliases=('themeassetsport',)),
    ConfigOption("network", "manager_ui_port", "int", '8001',
                 label='Manager UI Port',
                 aliases=('manageruiport',)),
    ConfigOption("dof", "enable_dof", "bool", 'false',
                 label='Enable DOF',
                 aliases=('enabledof',)),
    ConfigOption("dof", "dof_config_tool_api_key", "string", '',
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
    ConfigOption("mobile", "device_ip", "string", '',
                 label='Mobile Device IP',
                 aliases=('deviceip',)),
    ConfigOption("mobile", "device_port", "int", '2112',
                 label='Mobile Device Port',
                 aliases=('deviceport',)),
    ConfigOption("mobile", "chunk_size", "int", '1048576',
                 label='Mobile Chunk Size',
                 aliases=('chunksize',)),
    ConfigOption("mobile", "rename_mask_to_default_ini", "bool", 'false',
                 label='Enable Rename Mask To Default INI',
                 aliases=('renamemasktodefaultini',)),
    ConfigOption("mobile", "rename_mask_to_default_ini_mask", "string", '',
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
) + _input_options()


def options() -> tuple[ConfigOption, ...]:
    """Every option, in declaration order."""
    return CONFIG_OPTIONS


def settable() -> tuple[ConfigOption, ...]:
    """Everything a person is meant to set - what a UI or a doc should show."""
    return tuple(option for option in CONFIG_OPTIONS if not option.internal)


def option(section: str, key: str) -> ConfigOption | None:
    section = canonical_section(section)
    for candidate in CONFIG_OPTIONS:
        if candidate.section == section and candidate.key == key:
            return candidate
    return None


def canonical(section: str, key: str) -> str:
    """The name this setting is stored under, given any spelling it has ever had."""
    wanted = str(key or "").strip().lower()
    section = canonical_section(section)
    for candidate in CONFIG_OPTIONS:
        if candidate.section != section:
            continue
        if candidate.key.lower() == wanted:
            return candidate.key
        if any(a.lower() == wanted for a in candidate.aliases):
            return candidate.key
    return key


def locate(section: str, key: str) -> tuple[str, str]:
    """Where a setting lives now, given any section and key it has ever lived at.

    Per-window config moved fourteen settings out of `[Displays]` and `[Media]` into a
    section each, so a caller can be wrong about the section as well as the spelling.
    """
    wanted = (canonical_section(section), str(key or "").strip().lower())
    for candidate in CONFIG_OPTIONS:
        here = [(candidate.section, candidate.key.lower())]
        here += [(candidate.section, a.lower()) for a in candidate.aliases]
        # A former location names the section as it was spelled then, and some of those
        # sections have since been renamed too - so both sides are normalized or a
        # setting that moved out of a renamed section stops resolving.
        here += [(canonical_section(s), k.lower()) for s, k in candidate.legacy]
        if wanted in here:
            return candidate.section, candidate.key
    return canonical_section(section), key


def spellings(section: str, key: str) -> tuple[str, ...]:
    """Every name this setting has gone by, canonical first.

    A reader tries them in order because a parser is not always one the store filled:
    a caller can hand-build one, and a stored file written by an older build has the
    old names in it until the store rewrites them.
    """
    wanted = str(key or "").strip().lower()
    section = canonical_section(section)
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


def label_for(key: str, section: str = "") -> str:
    """What to call a setting on screen. Falls back to a readable form of the key.

    Pass the section when you have it: since each window got a section of its own,
    `screen_id` exists three times with a different label each, and a key-only lookup
    cannot tell a backglass monitor from a playfield one.
    """
    entry = option(section, key) if section else None
    if entry is None:
        entry = by_key(key)
    if entry is not None and entry.label:
        return entry.label
    return str(key or "").replace("_", " ").title()


def description_for(key: str, section: str = "") -> str:
    """One line explaining a setting, or "" when nobody has written one yet."""
    entry = (option(section, key) if section else None) or by_key(key)
    return entry.description if entry is not None else ""


def defaults() -> dict[str, dict[str, str]]:
    """The nested section/key/value shape the config store fills a new file from."""
    out: dict[str, dict[str, str]] = {}
    for entry in CONFIG_OPTIONS:
        out.setdefault(entry.section, {})[entry.key] = entry.default
    return out
