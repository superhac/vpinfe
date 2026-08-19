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

from dataclasses import dataclass, replace

from common import input_registry

# What a page press groups by. `sort` takes the groups from whatever the list is ordered
# by - the next letter, year or rating. `count` is a group of a fixed size, which is the
# one grouping that works whatever the order is, because it reads no values at all.
#
# `alpha` and `numeric` were the 2.x names, from when letters were the only groups, and
# they are on disk in configs users already have.
PAGING_GROUPS = ("sort", "count")
PAGING_GROUP_ALIASES = {"alpha": "sort", "numeric": "count"}
PAGING_GROUP_DEFAULT = "sort"


def _input_options() -> tuple[ConfigOption, ...]:
    """`[input]` comes from the action registry, so the two cannot disagree.

    One option per action holding an ordered list of bindings - not a key per input,
    because a binding names its own input and a chord names two.
    """
    out = [
        ConfigOption(
            action.name,
            type="list",
            default=",".join(action.bindings),
            label=action.label,
            legacy=tuple(("Input", old) for old in action.legacy),
        )
        for action in input_registry.actions()
    ]
    return in_section(input_registry.SECTION, *out)


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
    """One setting. `type` says how to read it, not how to store it.

    Declared inside `in_section(...)`, which fills the section in - so an entry names
    its key and nothing else, and the section is stated once for the whole block.
    """

    key: str
    type: str
    default: str
    # Filled in by `in_section`, so an entry never states it.
    section: str = ""
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


def in_section(section: str, *options: ConfigOption) -> tuple[ConfigOption, ...]:
    """Stamp a section onto the options declared under it.

    The section is written once, at the head of its block, rather than repeated on every
    entry - so what you scan down the left is the key, and a block cannot half-belong to
    two sections the way a comment header can drift.
    """
    return tuple(replace(option, section=section) for option in options)


CONFIG_OPTIONS: tuple[ConfigOption, ...] = (
    *in_section(
        "windows.backglass",
        ConfigOption(
            "screen_id",
            type="int",
            default="",
            label="Backglass Monitor ID",
            legacy=(("Displays", "bg_screen_id"), ("Displays", "bgscreenid")),
        ),
        ConfigOption(
            "window_override",
            type="string",
            default="",
            label="Backglass Window Override (x,y,width,height)",
            legacy=(("Displays", "bg_window_override"), ("Displays", "bgwindowoverride")),
        ),
        ConfigOption(
            "media_priority",
            type="choice",
            default="video",
            label="Backglass Media Priority",
            choices=("video", "image"),
            legacy=(("Media", "bg_media_priority"), ("Media", "bgmediapriority")),
        ),
    ),
    *in_section(
        "windows.scoreview",
        ConfigOption(
            "screen_id",
            type="int",
            default="",
            label="DMD Monitor ID",
            legacy=(("Displays", "dmd_screen_id"), ("Displays", "dmdscreenid")),
        ),
        ConfigOption(
            "window_override",
            type="string",
            default="",
            label="DMD Window Override (x,y,width,height)",
            legacy=(("Displays", "dmd_window_override"), ("Displays", "dmdwindowoverride")),
        ),
        ConfigOption(
            "media_priority",
            type="choice",
            default="video",
            label="DMD Media Priority",
            choices=("video", "image"),
            legacy=(("Media", "dmd_media_priority"), ("Media", "dmdmediapriority")),
        ),
    ),
    *in_section(
        "windows.playfield",
        ConfigOption(
            "screen_id",
            type="int",
            default="0",
            label="Playfield Monitor ID",
            legacy=(("Displays", "playfield_screen_id"), ("Displays", "playfieldscreenid")),
        ),
        ConfigOption(
            "orientation",
            type="choice",
            default="landscape",
            label="Playfield Monitor Mounting",
            description="How the playfield screen is physically mounted. Portrait means it is"
                        " turned on its side in the cabinet. This does not rotate anything by"
                        " itself - it tells themes what shape to lay out for.",
            choices=("landscape", "portrait"),
            legacy=(("Displays", "playfield_orientation"), ("Displays", "playfieldorientation")),
        ),
        ConfigOption(
            "rotation",
            type="choice",
            default="0",
            label="Rotate VPinFE Display",
            description="How far VPinFE turns its own display so it faces the player. Leave at 0"
                        " if your operating system already rotates this screen.",
            choices=("0", "90", "180", "270"),
            legacy=(("Displays", "playfield_rotation"), ("Displays", "playfieldrotation")),
        ),
        ConfigOption(
            "variant",
            type="choice",
            default="table",
            label="Table Type",
            description="Which playfield artwork this library holds: table.png, or fss.png for art"
                        " captured in Visual Pinball's Full Single Screen mode.",
            choices=("table", "fss"),
            legacy=(("Media", "playfield_variant"), ("Media", "playfieldvariant")),
        ),
        ConfigOption(
            "resolution",
            type="choice",
            default="4k",
            label="Default Table Resolution",
            choices=("4k", "1k"),
            legacy=(("Media", "playfield_resolution"), ("Media", "playfieldresolution")),
        ),
        ConfigOption(
            "video_resolution",
            type="choice",
            default="1k",
            label="Default Table Video Resolution",
            choices=("4k", "1k"),
            legacy=(("Media", "playfield_video_resolution"), ("Media", "playfieldvideoresolution")),
        ),
        ConfigOption(
            "media_priority",
            type="choice",
            default="video",
            label="Table Media Priority",
            choices=("video", "image"),
            legacy=(("Media", "playfield_media_priority"), ("Media", "playfieldmediapriority")),
        ),
        ConfigOption(
            "media_rotation",
            type="choice",
            default="auto",
            description="How far to turn playfield artwork so it fills the screen. auto measures"
                        " each image and turns only when it disagrees with the surface.",
            choices=("auto", "0", "90", "180", "270"),
            legacy=(("Media", "playfield_media_rotation"), ("Media", "playfieldmediarotation")),
        ),
    ),
    *in_section(
        "displays",
            # It lived in [Settings] before it was display context. Declared here
            # rather than chained through SettingsConfig, which is how a parser
            # that had not been migrated used to resolve it.
        ConfigOption(
            "cab_mode",
            type="bool",
            default="false",
            label="Cabinet Mode",
            description="Presents VPinFE for playing standing at a cabinet: larger text and"
                        " targets, and no controls that need a mouse. It does not rotate anything.",
            aliases=("cabmode",),
            legacy=(("Settings", "cabmode"), ("Settings", "cab_mode")),
        ),
    ),
    *in_section(
        "general",
        ConfigOption(
            "vpx_bin_path",
            type="string",
            default="",
            label="VPX Executable Path",
            description="Full path to the Visual Pinball executable VPinFE launches.",
            aliases=("vpxbinpath",),
        ),
        ConfigOption(
            "vpx_launch_env",
            type="string",
            default="",
            label="VPX Launch Environment",
            aliases=("vpxlaunchenv",),
        ),
        ConfigOption(
            "global_ini_override",
            type="string",
            default="",
            label="Global ini Override (/home/test/mysuper.ini)",
            aliases=("globalinioverride",),
        ),
        ConfigOption(
            "global_game_ini_override_enabled",
            type="bool",
            default="false",
            label="Global tableini Override Enabled",
            aliases=("globaltableinioverrideenabled",),
        ),
        ConfigOption(
            "global_game_ini_override_mask",
            type="string",
            default="",
            label="Global tableini Override Mask",
            aliases=("globaltableinioverridemask",),
        ),
        ConfigOption(
            "game_root_dir",
            type="string",
            default="",
            label="Tables Directory",
            description="The folder holding your table folders, one folder per game.",
            aliases=("gamerootdir",),
        ),
        ConfigOption(
            "vpx_ini_path",
            type="string",
            default="",
            label="VPX Ini Path",
            description="Path to VPinballX.ini, which VPinFE reads for the key mappings the Remote"
                        " page sends.",
            aliases=("vpxinipath",),
        ),
        ConfigOption(
            "assets_dir",
            type="string",
            default="",
            label="Shared Assets Directory",
            description="Root folder for assets shared across games rather than owned by one, such"
                        " as manufacturer logos. Served at /assets/ and defaults to assets/ under"
                        " the VPinFE config dir.",
            aliases=("assetsdir",),
        ),
        ConfigOption(
            "rar_tool_path",
            type="string",
            default="",
            label="RAR Tool Path (unar/unrar, blank = auto-detect)",
            aliases=("rartoolpath",),
        ),
        ConfigOption(
            "vpx_log_delete_on_start",
            type="bool",
            default="false",
            label="Delete VPinball Log On Table Start",
            aliases=("vpxlogdeleteonstart",),
        ),
        ConfigOption(
            "theme",
            type="string",
            default="Revolution",
            label="Active Theme",
        ),
        ConfigOption(
            "startup_collection",
            type="string",
            default="",
            label="Default Startup Collection",
        ),
        ConfigOption(
            "auto_update_media_on_startup",
            type="bool",
            default="false",
            label="Auto Update Media On Startup",
            aliases=("autoupdatemediaonstartup",),
        ),
        ConfigOption(
            "splashscreen",
            type="bool",
            default="false",
            label="Enable splashscreen",
        ),
        ConfigOption(
            "mute_audio",
            type="bool",
            default="false",
            label="Mute Frontend Audio",
            aliases=("muteaudio",),
        ),
        ConfigOption(
            "chrome_options",
            type="string",
            default="",
            label="Additional Chrome Options",
            aliases=("chromeoptions",),
        ),
        ConfigOption(
            "chrome_options_exclude",
            type="string",
            default="",
            aliases=("chromeoptionsexclude",),
        ),
        ConfigOption(
            "disable_default_chrome_options",
            type="bool",
            default="false",
            label="Disable Default Chrome Options",
            aliases=("disabledefaultchromeoptions",),
        ),
    ),
    # How the frontend behaves, as against `themes`, which is what is installed. Both of
    # these were in `general` beside genuinely global settings, on a Manager UI page
    # nobody looks at for wheel behaviour.
    *in_section(
        "frontend",
        # How far a page press moves the wheel. Not in `input`, which is which button
        # does what: these say what the frontend does when one is pressed.
        ConfigOption(
            "paging_group",
            type="choice",
            default=PAGING_GROUP_DEFAULT,
            label="Page by",
            choices=PAGING_GROUPS,
            legacy=(("Input", "pagingtype"),),
        ),
        ConfigOption(
            "paging_size",
            type="int",
            default="10",
            label="Paging Size",
            legacy=(("Input", "pagingsize"),),
        ),
        ConfigOption(
            "confirm",
            type="bool",
            default="false",
            label="Confirm Before Exit",
            description="Ask before quitting VPinFE or powering off the machine. Closing the"
                        " frontend never asks - the windows reopen from the Manager UI, so"
                        " there is nothing to lose. Off is how VPinFE has always behaved, and"
                        " the question is put to whichever surface asked.",
        ),
        ConfigOption(
            "hide_quit_button",
            type="bool",
            default="false",
            label="Hide Quit from MainMenu",
            aliases=("MMhideQuitButton",),
            # The 2.x location, then the one 3.0 briefly used. The second is not
            # compatibility for a shipped release - 3.0 has none - it is so an install
            # that already ran a 3.0 build keeps the setting instead of silently
            # defaulting. It can go once no such install is left.
            legacy=(("Settings", "MMhideQuitButton"), ("general", "hide_quit_button")),
        ),
        ConfigOption(
            "restore_last_table",
            type="bool",
            default="true",
            label="Restore Last Table",
            # `restorelastgame` was 3.0's and never shipped; 2.x wrote `restorelasttable`,
            # which is also what this restores - a row is a table.
            aliases=("restorelasttable",),
            # As above: 2.x's location first, then the two spellings a 3.0 build wrote -
            # `restore_last_game` into the JSON, and `restorelastgame` into the ini it
            # converted from.
            legacy=(("Settings", "restorelasttable"),
                    ("general", "restore_last_game"),
                    ("Settings", "restorelastgame")),
        ),
    ),
    *in_section(
        "themes",
        ConfigOption(
            "registries",
            type="list",
            default="https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json",
            label="Theme Registries",
            description="Catalogs to offer themes from, most trusted first. The stock registry is"
                        " an entry like any other, so a mirrored or offline install can replace or"
                        " drop it.",
        ),
        ConfigOption(
            "repositories",
            type="list",
            default="",
            label="Theme Repositories",
            description="Individual theme repos, each one a theme in its own right. Resolved"
                        " before the registries, and named for the repo with any vpinfe-theme-"
                        " prefix removed.",
        ),
    ),
    *in_section(
        "logger",
        ConfigOption(
            "level",
            type="choice",
            default="debug",
            label="Log Verbosity",
            choices=("debug", "info", "warning", "error"),
        ),
        ConfigOption(
            "console",
            type="bool",
            default="true",
            label="Console Logging",
        ),
    ),
    *in_section(
        "media",
        ConfigOption(
            "default_missing_media_image",
            type="string",
            default="",
            label="Default Missing Media Image",
            aliases=("defaultmissingmediaimg",),
        ),
        ConfigOption(
            "thumb_cache_max_mb",
            type="int",
            default="500",
            label="Thumbnail Cache Max (MB)",
            aliases=("thumbcachemaxmb",),
        ),
        ConfigOption(
            "wheelset",
            type="string",
            default="",
            label="Wheel Set",
            description="Name of the wheel art set to use library-wide, a folder under a game's"
                        " medias/wheels/. The reserved name logo shows each game's logo instead."
                        " Blank means plain wheels, and the active theme can override this with its"
                        " own wheelSet option.",
        ),
        ConfigOption(
            "realdmd_media_priority",
            type="choice",
            default="color",
            label="Real DMD Priority",
            choices=("color", "video", "image"),
            aliases=("realdmdmediapriority",),
        ),
    ),
    *in_section(
        "install",
        ConfigOption(
            "id",
            type="string",
            default="",
            description="Written by VPinFE on first start, and not meant to be edited."
                        " A hub tells its installs apart by this, so changing it makes"
                        " this a different install.",
            # Minted on first read, never by a person, and never edited afterwards.
            internal=True,
        ),
        ConfigOption(
            "display_name",
            type="string",
            default="",
            label="Install Name",
            description="What to call this install where one is listed. Defaults to this"
                        " machine's hostname. Nothing is addressed by it, so renaming is"
                        " safe.",
        ),
        ConfigOption(
            "roles",
            type="list",
            default="hub,device",
            label="Roles",
            description="What this install serves: the shared library half (hub), the"
                        " machine games launch on (device), or both.",
        ),
    ),
    *in_section(
        "vpsdb",
        ConfigOption(
            "last",
            type="string",
            default="",
            internal=True,
        ),
    ),
    *in_section(
        "state",
        ConfigOption(
            "last_table",
            type="string",
            default="",
            aliases=("lasttable",),
            internal=True,
        ),
    ),
    *in_section(
        "pinmame_score_parser",
        ConfigOption(
            "roms_update_sha",
            type="string",
            default="",
            aliases=("romsupdatesha",),
            internal=True,
        ),
    ),
    *in_section(
        "network",
        ConfigOption(
            "theme_assets_port",
            type="int",
            default="8000",
            label="Theme Server Port",
            aliases=("themeassetsport",),
        ),
        ConfigOption(
            "theme_assets_bind",
            type="string",
            default="127.0.0.1",
            label="Theme Server Address",
            description="Which address to serve theme packages and table media on. The"
                        " default answers this machine only. An address rather than a"
                        " switch, so a single interface can be named; 0.0.0.0 is every"
                        " one. This port serves the table library, so opening it shares"
                        " read access to it.",
        ),
        ConfigOption(
            "ws_port",
            type="int",
            default="8002",
            label="WebSocket Bridge Port",
            description="Port the frontend windows and the theme talk to VPinFE over. Loopback"
                        " only.",
            aliases=("wsport",),
        ),
        ConfigOption(
            "hub_port",
            type="int",
            default="8001",
            label="Hub Port",
            description="Port the hub answers on: the HTTP API, the Manager UI, and the"
                        " remote and mobile pages. Named for the role rather than any one"
                        " thing listening on it - all four are hub-side.",
            aliases=("manager_ui_port", "manageruiport"),
        ),
        ConfigOption(
            "hub_url",
            type="string",
            default="",
            label="Hub URL",
            description="Read the library from a hub on another machine, for example"
                        " http://cabinet.local:8001. Empty - the default - means this"
                        " install holds its own library, which is every single-machine"
                        " setup.",
        ),
        ConfigOption(
            "verify_shared_library",
            type="bool",
            default="false",
            label="Verify Shared Library",
            description="On startup, check that this player's library really is the"
                        " hub's, by comparing file hashes rather than paths. Reports"
                        " what does not match and changes nothing else. Off by default,"
                        " and ignored entirely without a Hub URL.",
        ),
        ConfigOption(
            "hub_bind",
            type="string",
            default="0.0.0.0",
            label="Hub Address",
            description="Which address to serve the hub on. The default answers every"
                        " interface, which is what it has always done - set 127.0.0.1 to"
                        " reach it only from this machine.",
            aliases=("manager_ui_bind",),
        ),
    ),
    *in_section(
        "dof",
        ConfigOption(
            "enable_dof",
            type="bool",
            default="false",
            label="Enable DOF",
            aliases=("enabledof",),
        ),
        ConfigOption(
            "dof_config_tool_api_key",
            type="string",
            default="",
            label="DOF Config Tool API Key",
            aliases=("dofconfigtoolapikey",),
        ),
    ),
    *in_section(
        "libdmdutil",
        ConfigOption(
            "enabled",
            type="bool",
            default="false",
            label="Enabled",
        ),
        ConfigOption(
            "pin2dmd_enabled",
            type="bool",
            default="false",
            label="Enable",
            aliases=("pin2dmdenabled",),
        ),
        ConfigOption(
            "pixelcade_serial_port",
            type="string",
            default="",
            label="Pixelcade serial port",
            aliases=("pixelcadedevice",),
        ),
        ConfigOption(
            "zedmd_serial_port",
            type="string",
            default="",
            label="ZeDMD serial port",
            aliases=("zedmddevice",),
        ),
        ConfigOption(
            "zedmd_wifi_address",
            type="string",
            default="",
            label="ZeDMDWiFiAddr",
            aliases=("zedmdwifiaddr",),
        ),
    ),
    *in_section(
        "mobile",
        ConfigOption(
            "device_ip",
            type="string",
            default="",
            label="Mobile Device IP",
            aliases=("deviceip",),
        ),
        ConfigOption(
            "device_port",
            type="int",
            default="2112",
            label="Mobile Device Port",
            aliases=("deviceport",),
        ),
        ConfigOption(
            "chunk_size",
            type="int",
            default="1048576",
            label="Mobile Chunk Size",
            aliases=("chunksize",),
        ),
        ConfigOption(
            "rename_mask_to_default_ini",
            type="bool",
            default="false",
            label="Enable Rename Mask To Default INI",
            aliases=("renamemasktodefaultini",),
        ),
        ConfigOption(
            "rename_mask_to_default_ini_mask",
            type="string",
            default="",
            label="Rename Mask To Default INI Mask",
            aliases=("renamemasktodefaultinimask",),
        ),
    ),
    *in_section(
        "vpinplay",
        ConfigOption(
            "sync_on_exit",
            type="bool",
            default="false",
            label="Sync on Exit",
            aliases=("synconexit",),
        ),
        ConfigOption(
            "api_endpoint",
            type="string",
            default="https://api.vpinplay.com:8888",
            label="API Endpoint",
            aliases=("apiendpoint",),
        ),
        ConfigOption(
            "user_id",
            type="string",
            default="",
            label="User ID",
            aliases=("userid",),
        ),
        ConfigOption(
            "initials",
            type="string",
            default="",
            label="Initials",
        ),
        ConfigOption(
            "machine_id",
            type="string",
            default="",
            label="Machine ID",
            aliases=("machineid",),
        ),
    ),
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
