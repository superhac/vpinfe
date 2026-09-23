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

from common import i18n, input_registry, setting_groups
from common.i18n import t
from common.labels import humanize

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
            label_key=f"input.{action.name}",
            group=action.group,
            # A list of selectors is what it *is*; typing `pad:0/button:3` is not how
            # anybody wants to say which button they pressed.
            editor=EDITOR_BINDING,
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
    'Mobile': 'vpxmobile',
    'Network': 'network',
    'State': 'state',
    'VPSdb': 'vpsdb',
    'DOF': 'dof',
    'libdmdutil': 'real_dmd',
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
    # Where this setting's words live, for the settings generated from another registry:
    # the `[input]` block is one option per action, and the action already owns the word.
    # Empty means the key follows the section and the key, which is every other setting.
    label_key: str = ""
    choices: tuple[str, ...] = ()
    # How many rows a `text` setting gets. A paragraph and a one-line name want
    # different controls, and only the setting knows which it is.
    lines: int = 0
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
    # What this string names on disk, when it names something: `file`, `dir`, or `exe`.
    # Declared rather than inferred from the key - `vpx_bin_path` and `vpx_ini_path` end
    # the same way and want different answers, and a surface that guesses from a name is
    # one rename away from validating the wrong thing.
    path: str = ""
    # A heading to gather this setting under, within its section. Empty means it sits
    # above the first heading, which is where the ones that need no explaining go.
    #
    # Only on a page that draws one section: a page drawing several already heads each
    # of them, and a second level of identical headings would say which is which by
    # position alone.
    group: str = ""
    # A set of values worth offering that this file cannot hold, because it is not known
    # until the install is running - which installs are on the network, say. Declared
    # here rather than matched on the key by a surface, so the same rename that moves the
    # setting moves the control with it. Suggestions, not choices: the list is offered
    # and anything may still be typed, because the thing that produces it can be wrong.
    suggest: str = ""
    # A named tool this setting is edited with, where a control cannot do the job. The
    # type still says what the value *is*, so anything that only reads the setting is
    # unaffected and a surface with no such editor falls back to the control for its
    # type rather than showing nothing.
    editor: str = ""

    @property
    def keys(self) -> str:
        """Where this setting's words live in the catalog."""
        return self.label_key or f"config.{self.section}.{self.key}"

    @property
    def label(self) -> str:
        """What to call this setting on screen, or "" where it has no name of its own.

        A setting nobody sets - an install id, a last-played pointer - is never shown,
        so it has no entry and no translator is asked for one.
        """
        said = t(f"{self.keys}.label")
        return "" if said.endswith(".label") else said

    @property
    def choice_labels(self) -> dict[str, str]:
        """What to call each choice on screen, for the choices the catalog names."""
        found = {}
        for value in self.choices:
            said = t(f"{self.keys}.choice.{value}")
            if not said.endswith(f".choice.{value}"):
                found[value] = said
        return found

    @property
    def description(self) -> str:
        """One line explaining it, or "" where nobody has written one.

        Prose, so a locale may leave it in English while the label is translated.
        """
        said = t(f"{self.keys}.description")
        return "" if said.endswith(".description") else said

    @property
    def group_label(self) -> str:
        """The heading this setting gathers under, or "" where it has none."""
        return t(f"config.group.{self.group}") if self.group else ""


PATH_KINDS = ("file", "dir", "exe")

# What an `editor` may name. Closed for the same reason `suggest` is: a typo should be a
# setting drawn with its ordinary control, not a surface silently asking for a tool
# nobody registered.
EDITOR_BINDING = "binding"
# A palette is picked by looking at it. The names carry almost nothing on their own -
# "Synthwave" means something only once you have seen it - so the control shows each one.
EDITOR_CONSOLE_THEME = "console_theme"
# Shown in Settings, chosen on the Themes page.
EDITOR_FRONTEND_THEME = "frontend_theme"
EDITORS = (EDITOR_BINDING, EDITOR_CONSOLE_THEME, EDITOR_FRONTEND_THEME)

# What a `suggest` may name. Closed, so a typo is a setting with no suggestions rather
# than a surface quietly asking for a list nobody serves.
SUGGEST_LIBRARIES = "libraries"
SUGGEST_THEMES = "themes"
SUGGEST_COLLECTIONS = "collections"
SUGGESTIONS = (SUGGEST_LIBRARIES, SUGGEST_THEMES, SUGGEST_COLLECTIONS)


def in_section(section: str, *options: ConfigOption) -> tuple[ConfigOption, ...]:
    """Stamp a section onto the options declared under it.

    The section is written once, at the head of its block, rather than repeated on every
    entry - so what you scan down the left is the key, and a block cannot half-belong to
    two sections the way a comment header can drift.
    """
    return tuple(replace(option, section=section) for option in options)


CONFIG_OPTIONS: tuple[ConfigOption, ...] = (
    *in_section(
        "windows.playfield",
        ConfigOption(
            "screen_id",
            type="int",
            default="0",
            legacy=(("Displays", "playfieldscreenid"),),
        ),
        ConfigOption(
            "orientation",
            type="choice",
            default="landscape",
            choices=("landscape", "portrait"),
            legacy=(("Displays", "playfieldorientation"),),
        ),
        ConfigOption(
            "rotation",
            type="choice",
            default="0",
            choices=("0", "90", "180", "270"),
            legacy=(("Displays", "playfieldrotation"),),
        ),
    ),
    *in_section(
        "windows.backglass",
        ConfigOption(
            "screen_id",
            type="int",
            default="",
            legacy=(("Displays", "bgscreenid"),),
        ),
        ConfigOption(
            "override",
            type="string",
            default="",
            legacy=(("Displays", "bgwindowoverride"),),
        ),
    ),
    *in_section(
        "windows.score_view",
        ConfigOption(
            "screen_id",
            type="int",
            default="",
            legacy=(("Displays", "dmdscreenid"),),
        ),
        ConfigOption(
            "override",
            type="string",
            default="",
            legacy=(("Displays", "dmdwindowoverride"),),
        ),
    ),
    # Seven Visual Pinball settings left this section for the launcher that owns them:
    # the binary, its ini, the environment, the log-delete switch and the three override
    # keys. They are not settings an install has, they are fields of a way of running an
    # app, and a second way of running it would have collided with every one of them.
    # `launchers.json` holds them now; `launcher_migration` reads them out of an older
    # file once. What is left here belongs to the install itself.
    *in_section(
        "general",
        # Runtime state that happens to live in the config file. Nothing settable is left
        # here. `locations.json` holds the library root now, and this seeds it on first
        # run.
        ConfigOption(
            "game_root_dir",
            type="string",
            path="dir",
            default="",
            aliases=("gamerootdir",),
            internal=True,
        ),
        ConfigOption(
            "hidden_media_kinds",
            type="list",
            default="",
            # The library's, not this install's - it moved to library.json, where one
            # answer serves every install reading this library. Declared and internal so a
            # value still in a config file keeps resolving for a build that reads it.
            internal=True,
        ),
        ConfigOption(
            "hidden_asset_kinds",
            type="list",
            default="",
            # The library's, not this install's - it moved to library.json, where one
            # answer serves every install reading this library. Declared and internal so a
            # value still in a config file keeps resolving for a build that reads it.
            internal=True,
        ),
    ),
    # Commands the install runs around itself. `table_commands` below is the same, around
    # a table, and a launcher's own are in `launchers.json`.
    *in_section(
        "commands",
        # Declared first because it governs every command here and in `table_commands`.
        ConfigOption(
            "timeout",
            type="int",
            default="15",
            legacy=(),
        ),
        ConfigOption(
            "on_vpinfe_start",
            type="text",
            lines=3,
            default="",
            legacy=(),
        ),
        ConfigOption(
            "on_vpinfe_exit",
            type="text",
            lines=3,
            default="",
            legacy=(),
        ),
    ),
    # The same, around a table, and run by whichever launcher plays it.
    *in_section(
        "table_commands",
        ConfigOption(
            "on_start",
            type="text",
            lines=3,
            default="",
            legacy=(),
        ),
        ConfigOption(
            "on_exit",
            type="text",
            lines=3,
            default="",
            legacy=(),
        ),
        ConfigOption(
            "start_required",
            type="bool",
            default="false",
            legacy=(),
        ),
    ),
    # The browser the frontend runs in.
    *in_section(
        "chromium",
        ConfigOption(
            "options",
            # One flag per line, which is what the help beside it has always said and
            # what a one-line box could not take. Parsed with shell-style quoting, so a
            # newline is whitespace and nothing about the stored value changes.
            type="text",
            lines=3,
            default="",
            legacy=(("general", "chromeoptions"),),
        ),
        ConfigOption(
            "options_exclude",
            type="text",
            lines=3,
            default="",
            legacy=(("general", "chromeoptionsexclude"),),
        ),
        ConfigOption(
            "disable_defaults",
            type="bool",
            default="false",
            legacy=(("general", "disabledefaultchromeoptions"),),
        ),
    ),
    # What the Console looks like, as against what the frontend shows a player.
    *in_section(
        "console",
        ConfigOption(
            "theme",
            type="choice",
            # Not `auto` like `install.language`: this one defers to the operating system
            # rather than to a language the OS names outright, and the two neutral
            # palettes are the only answers an OS preference can give.
            default="synthwave",
            choices=("synthwave", "dark", "light", "system"),
            editor=EDITOR_CONSOLE_THEME,
            legacy=(),
        ),
        ConfigOption(
            "dates",
            type="choice",
            default="language",
            choices=("language", "iso", "mm/dd/yyyy", "dd/mm/yyyy", "dd.mm.yyyy",
                     "yyyy/mm/dd"),
        ),
        ConfigOption(
            "times",
            type="choice",
            default="24h",
            choices=("24h", "12h"),
        ),
        ConfigOption(
            "relative_dates",
            type="bool",
            default="true",
        ),
    ),
    # Programs on this machine VPinFE shells out to. Each is discovered first, and set
    # here only where discovery finds nothing or picks the wrong one.
    *in_section(
        "tools",
        ConfigOption(
            "rar_path",
            type="string",
            path="exe",
            default="",
            legacy=(("general", "rartoolpath"),),
        ),
    ),
    # Art a theme or the frontend draws that is not a game's own.
    *in_section(
        "assets",
        ConfigOption(
            "dir",
            group=setting_groups.LOCAL_SOURCES,
            type="string",
            path="dir",
            default="",
            legacy=(("general", "assetsdir"),),
        ),
    ),
    # The library as something this install reads, as against `media`, which is what it
    # collects.
    *in_section(
        "updates",
        ConfigOption(
            "refresh_minutes",
            type="int",
            default="0",
            legacy=(),
        ),
        ConfigOption(
            "auto_update_media",
            type="bool",
            default="false",
            legacy=(("general", "autoupdatemediaonstartup"),),
        ),
        ConfigOption(
            "ask_where_new_games_go",
            type="bool",
            default="true",
            legacy=(),
        ),
    ),
    # What the frontend shows, as against what it does. Every one is served to themes
    # over the bridge, so renaming a key here changes what a published theme reads.
    *in_section(
        "presentation",
        ConfigOption(
            "cab_mode",
            type="bool",
            default="false",
            aliases=("cabmode",),
            legacy=(("displays", "cabmode"), ("Settings", "cabmode")),
        ),
        ConfigOption(
            "playfield_media_rotation",
            type="choice",
            default="auto",
            choices=("auto", "0", "90", "180", "270"),
            legacy=(("Media", "playfieldmediarotation"),),
        ),
        ConfigOption(
            "playfield_media_priority",
            type="choice",
            default="video",
            choices=("video", "image"),
            legacy=(("Media", "playfieldmediapriority"),),
        ),
        ConfigOption(
            "backglass_media_priority",
            type="choice",
            default="video",
            choices=("video", "image"),
            legacy=(("Media", "bgmediapriority"),),
        ),
        ConfigOption(
            "score_view_media_priority",
            type="choice",
            default="video",
            choices=("video", "image"),
            legacy=(("Media", "dmdmediapriority"),),
        ),
        ConfigOption(
            "real_dmd_media_priority",
            type="choice",
            default="color",
            choices=("color", "video", "image"),
            legacy=(("media", "realdmdmediapriority"),),
        ),
    ),
    # How the frontend behaves, as against `themes`, which is what is installed. Both of
    # these were in `general` beside genuinely global settings, on a Manager UI page
    # nobody looks at for wheel behavior.
    *in_section(
        "behavior",
        # How far a page press moves the wheel. Not in `input`, which is which button
        # does what: these say what the frontend does when one is pressed.
        ConfigOption(
            "paging_group",
            group=setting_groups.NAVIGATION,
            type="choice",
            default=PAGING_GROUP_DEFAULT,
            choices=PAGING_GROUPS,
            legacy=(("Input", "pagingtype"),),
        ),
        ConfigOption(
            "paging_size",
            group=setting_groups.NAVIGATION,
            type="int",
            default="10",
            legacy=(("Input", "pagingsize"),),
        ),
        ConfigOption(
            "startup_collection",
            group=setting_groups.STARTUP,
            type="string",
            default="",
            # Only a collection that exists can be opened on, but the list is not closed:
            # a cabinet can be set up before the collection it will open on is made.
            suggest=SUGGEST_COLLECTIONS,
            legacy=(("general", "startup_collection"),),
        ),
        ConfigOption(
            "restore_last_table",
            group=setting_groups.STARTUP,
            type="bool",
            default="true",
            # `restorelastgame` was 3.0's and never shipped; 2.x wrote `restorelasttable`,
            # which is also what this restores - a row is a table.
            aliases=("restorelasttable",),
            # As above: 2.x's location first, then the two spellings a 3.0 build wrote -
            # `restore_last_game` into the JSON, and `restorelastgame` into the ini it
            # converted from.
            legacy=(("Settings", "restorelasttable"), ("Settings", "restorelastgame")),
        ),
        ConfigOption(
            "splashscreen",
            group=setting_groups.STARTUP,
            type="bool",
            default="false",
            legacy=(("general", "splashscreen"),),
        ),
        ConfigOption(
            "confirm",
            group=setting_groups.EXIT,
            type="bool",
            default="false",
        ),
        ConfigOption(
            "hide_quit_button",
            group=setting_groups.EXIT,
            type="bool",
            default="false",
            aliases=("MMhideQuitButton",),
            # The 2.x location, then the one 3.0 briefly used. The second is not
            # compatibility for a shipped release - 3.0 has none - it is so an install
            # that already ran a 3.0 build keeps the setting instead of silently
            # defaulting. It can go once no such install is left.
            legacy=(("Settings", "MMhideQuitButton"),),
        ),
        ConfigOption(
            "mute_audio",
            group=setting_groups.AUDIO,
            type="bool",
            default="false",
            legacy=(("general", "muteaudio"),),
        ),
    ),
    *in_section(
        "themes",
        # Which one is running, as against the two lists below, which say where themes
        # are found.
        ConfigOption(
            "active",
            type="string",
            default="Revolution",
            suggest=SUGGEST_THEMES,
            editor=EDITOR_FRONTEND_THEME,
            legacy=(("general", "theme"),),
        ),
        ConfigOption(
            "registries",
            type="list",
            default="https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json",
        ),
        ConfigOption(
            "repositories",
            type="list",
            default="",
        ),
        ConfigOption(
            "refresh",
            type="choice",
            default="daily",
            choices=("never", "daily", "weekly", "monthly"),
        ),
        ConfigOption(
            "last_read",
            type="string",
            default="",
            internal=True,
        ),
    ),
    *in_section(
        "logger",
        ConfigOption(
            "level",
            type="choice",
            default="debug",
            choices=("debug", "info", "warning", "error"),
        ),
        ConfigOption(
            "terminal",
            type="bool",
            default="true",
            aliases=("console",),
        ),
    ),
    *in_section(
        "media",
        ConfigOption(
            "playfield_variant",
            group=setting_groups.PLAYFIELD_ARTWORK,
            type="choice",
            default="table",
            choices=("table", "fss"),
            legacy=(("Media", "playfieldvariant"),),
        ),
        ConfigOption(
            "playfield_resolution",
            group=setting_groups.PLAYFIELD_ARTWORK,
            type="choice",
            default="4k",
            choices=("4k", "1k"),
            legacy=(("Media", "playfieldresolution"),),
        ),
        ConfigOption(
            "playfield_video_resolution",
            group=setting_groups.PLAYFIELD_ARTWORK,
            type="choice",
            default="1k",
            choices=("4k", "1k"),
            legacy=(("Media", "playfieldvideoresolution"),),
        ),
        ConfigOption(
            "browse_dirs",
            group=setting_groups.LOCAL_SOURCES,
            type="list",
            default="",
            legacy=(),
        ),
        ConfigOption(
            "wheelset",
            group=setting_groups.WHEELS,
            type="string",
            default="",
        ),
        ConfigOption(
            "default_missing_image",
            type="string",
            default="",
            aliases=("defaultmissingmediaimg",),
        ),
        ConfigOption(
            "thumb_cache_max_mb",
            type="int",
            default="500",
            aliases=("thumbcachemaxmb",),
        ),
        ConfigOption(
            "asset_sources",
            type="list",
            default="",
            # Moved to library.json with the two kind lists, for the same reason.
            internal=True,
        ),
    ),
    *in_section(
        "install",
        ConfigOption(
            "id",
            type="string",
            default="",
            # Minted on first read, never by a person, and never edited afterwards.
            internal=True,
        ),
        ConfigOption(
            "display_name",
            type="string",
            default="",
        ),
        ConfigOption(
            "features",
            type="list",
            default="library,frontend,devices",
            aliases=("roles",),
        ),
        ConfigOption(
            "language",
            type="choice",
            # `auto` reads the operating system, which is right on a cabinet somebody
            # set up in their own language and never opened this page.
            default="auto",
            choices=("auto",) + i18n.available(),
            legacy=(("general", "language"),),
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
        # When the catalog was last asked, not when it last changed - `last` above is
        # the version we hold. Without this the only way to know a check is due is to
        # make one, which is the check.
        ConfigOption(
            "checked",
            type="string",
            default="",
            internal=True,
        ),
        ConfigOption(
            "download",
            group=setting_groups.VPS,
            type="choice",
            default="daily",
            choices=("never", "daily", "weekly", "monthly"),
        ),
        # Separate from `download`: a machine can want current data for matching
        # without wanting its games rewritten.
        ConfigOption(
            "update_matched_games",
            group=setting_groups.VPS,
            type="choice",
            default="never",
            choices=("never", "daily", "weekly", "monthly"),
        ),
        # The spreadsheet version the games were last brought up to.
        ConfigOption(
            "games_updated_to",
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
            group=setting_groups.LOCAL_SERVICES,
            type="int",
            default="8000",
            aliases=("themeassetsport",),
        ),
        ConfigOption(
            "theme_assets_bind",
            group=setting_groups.LOCAL_SERVICES,
            type="string",
            default="127.0.0.1",
        ),
        ConfigOption(
            "ws_port",
            group=setting_groups.LOCAL_SERVICES,
            type="int",
            default="8002",
            aliases=("wsport",),
        ),
        ConfigOption(
            "http_port",
            group=setting_groups.LOCAL_SERVICES,
            type="int",
            default="8001",
            aliases=("hub_port", "manager_ui_port", "manageruiport"),
        ),
        ConfigOption(
            "library_url",
            group=setting_groups.REMOTE_SERVICES,
            type="string",
            default="",
            suggest=SUGGEST_LIBRARIES,
        ),
        ConfigOption(
            "verify_shared_library",
            group=setting_groups.REMOTE_SERVICES,
            type="bool",
            default="false",
        ),
        ConfigOption(
            "http_bind",
            group=setting_groups.LOCAL_SERVICES,
            type="string",
            default="0.0.0.0",
            aliases=("hub_bind", "manager_ui_bind"),
        ),
    ),
    *in_section(
        "dof",
        ConfigOption(
            "enabled",
            group=setting_groups.DOF,
            type="bool",
            default="false",
            aliases=("enabledof",),
        ),
        ConfigOption(
            "config_tool_api_key",
            group=setting_groups.DOF,
            type="string",
            default="",
            aliases=("dofconfigtoolapikey",),
        ),
    ),
    *in_section(
        "real_dmd",
        ConfigOption(
            "enabled",
            type="bool",
            default="false",
        ),
        ConfigOption(
            "pin2dmd_enabled",
            type="bool",
            default="false",
            aliases=("pin2dmdenabled",),
        ),
        ConfigOption(
            "pixelcade_serial_port",
            type="string",
            default="",
            aliases=("pixelcadedevice",),
        ),
        ConfigOption(
            "zedmd_serial_port",
            type="string",
            default="",
            aliases=("zedmddevice",),
        ),
        ConfigOption(
            "zedmd_wifi_address",
            type="string",
            default="",
            aliases=("zedmdwifiaddr",),
        ),
    ),
    *in_section(
        "vpxmobile",
        ConfigOption(
            "device_ip",
            type="string",
            default="",
            aliases=("deviceip",),
        ),
        ConfigOption(
            "device_port",
            type="int",
            default="2112",
            aliases=("deviceport",),
        ),
        ConfigOption(
            "chunk_size",
            type="int",
            default="1048576",
            aliases=("chunksize",),
        ),
        ConfigOption(
            "send_masked_config",
            type="bool",
            default="false",
            aliases=("renamemasktodefaultini",),
        ),
        ConfigOption(
            "config_mask",
            type="string",
            default="",
            aliases=("renamemasktodefaultinimask",),
        ),
    ),
    *in_section(
        "vpinplay",
        # The extension owns these. Declared here so a 2.x file converts, and read
        # once by the handover. Nothing else in core reads or writes them.
        ConfigOption(
            "sync_on_exit",
            type="bool",
            default="false",
            aliases=("synconexit",),
            internal=True,
        ),
        ConfigOption(
            "api_endpoint",
            type="string",
            default="https://api.vpinplay.com:8888",
            aliases=("apiendpoint",),
            internal=True,
        ),
        ConfigOption(
            "user_id",
            type="string",
            default="",
            aliases=("userid",),
            internal=True,
        ),
        ConfigOption(
            "initials",
            type="string",
            default="",
            internal=True,
        ),
        ConfigOption(
            "machine_id",
            type="string",
            default="",
            aliases=("machineid",),
            internal=True,
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

    Needed because configparser lowercases option names on read, so a caller holding a
    key off the file has neither the section nor the original casing.

    A key is not unique across sections - `screen_id` and `media_priority` are each in
    several - so this answers with the first declared. Pass the section wherever you have
    it; `label_for` says the same.
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
    return humanize(key)


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
