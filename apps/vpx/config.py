"""Visual Pinball's settings, at the scope somebody is editing them.

Two layers, not three. VPX gives a table's settings one parent - the application's - and
the *table layer* is one file whose name is resolved by existence: `<table>.ini` beside
the game file if there is one, otherwise `<folder>.ini`. They do not stack. Setting a
value for a table where a folder file exists moves that table onto a file that does not
carry the folder's other keys, and they fall through to the application rather than to
the folder. That is the trap this reports as `in_effect` being false, because it is
invisible otherwise and is the bug report we would get.
"""

from __future__ import annotations

import math
import os
import re
import struct
import sys
import threading
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from common.apps.contract import (
    SCOPE_ENTRY,
    SCOPE_FOLDER,
    SCOPE_LAUNCHER,
    ConfigGroup,
    ConfigValue,
    Field,
    Heading,
)

from . import areas, displays, plugins
from . import ini as vini
from .setting_types import CONTEXTUAL, LABELS, REGISTERED, TYPES

REST = areas.REST

# Read but never offered. `[Version]` is what the program wrote about itself rather than
# something to set; the rest is state the program keeps in the same file - key bindings
# written per device as somebody binds them, and the order plugins render in, worked out
# when they load. None of it is a setting, and a page of raw input bindings in a
# settings editor is noise somebody has to read past.
HIDDEN_SECTIONS = frozenset({"Version", "RecentDir"})
# `Plugin.vpx` is the program itself, and turning it off stops the program.
HIDDEN_PREFIXES = ("Input.Mapping", "Input.Device", "Plugin.vpx.")
# A trailing part rather than a whole section: `[Backglass.Priority.PUP]` is one of
# several, one per plugin, and they arrive as plugins do.
HIDDEN_PARTS = ("Priority",)
# The table editor's: default properties for new parts, its script editor's colors, and
# the physics sets its physics dialog keeps. Nothing a table plays with.
EDITOR_SECTIONS = ("DefaultProps\\", "CVEdit")
EDITOR_PHYSICS = re.compile(r"Player\.(FlipperPhysics|TablePhysics|PhysicsSetName).*\d")
POINT_OF_VIEW = areas.POINT_OF_VIEW_KEYS

# VPX sizes a window left blank from its screen, never by the 16384 it declares.
_WINDOWS = (("Player", "Playfield"), ("Backglass", "Backglass"), ("ScoreView", "ScoreView"),
            ("Topper", "Topper"), ("PlayerVR", "Preview"))
FROM_THE_SCREEN = frozenset(f"{section}.{window}{mode}{side}" for section, window in _WINDOWS
                            for mode in ("", "FS") for side in ("Width", "Height"))
# And a view's mode from the table, never by the mode it declares.
FROM_THE_TABLE = areas.VIEW_MODES
NAMED_VALUES = {"Player.MaxFramerate": (("-1", "match_the_display"), ("0", "no_limit"))}
DISPLAYS = frozenset(f"{section}.{window}Display" for section, window in _WINDOWS)

# The views a table starts in, by its View Mode. At 0 a flag inside the table picks
# Full Single Screen or Desktop.
_VIEWS_AT = {"0": ("DT", "FSS"), "1": ("Cab",), "2": ("DT",)}
BGSET = "Player.BGSet"

# What the program keeps for all tables only: the pages of its own menu that save
# globally (input, plunger, nudge and tilt, cabinet, stereo), the table editor's, and the
# items any page writes straight to the global file. The playfield window is read from the global file
# alone, whatever its page saves.
ALL_TABLES_ONLY_SECTIONS = frozenset({"Input", "Editor"})
ALL_TABLES_ONLY_PREFIXES = ("Player.Stereo3D", "Player.Anaglyph", "Controller.DOF",
                            "Plugin.DMDUtil.")
_SAVED_DIRECTLY = ("FullScreen", "FSWidth", "FSHeight", "RefreshRate", "ColorDepth")
ALL_TABLES_ONLY = frozenset({
    "Player.PlayfieldDisplay", "Player.PlayfieldWndX", "Player.PlayfieldWndY",
    "Player.PlayfieldWidth", "Player.PlayfieldHeight",
    *(f"{section}.{window}{part}" for section, window in
      (("Player", "Playfield"), ("Backglass", "Backglass"), ("ScoreView", "ScoreView"),
       ("Topper", "Topper")) for part in _SAVED_DIRECTLY),
    "Player.PlungerRetract", "Player.PlungerLinearSensor",
    "Player.KeyboardNudgeMode", "Player.KeyboardNudgeStrength", "Player.NudgeStrength",
    "Player.EnableLegacyNudge", "Player.LegacyNudgeStrength", "Player.NudgeFilter0",
    "Player.NudgeFilter1", "Player.NudgeOrientation0", "Player.NudgeOrientation1",
    "Player.PlumbInertia", "Player.PlumbThresholdAngle", "Player.SimulatedPlumb",
    "Player.RumbleMode",
    "Player.ScreenWidth", "Player.ScreenHeight", "Player.ScreenInclination",
    "Player.LockbarWidth", "Player.LockbarHeight",
    "Player.ScreenPlayerX", "Player.ScreenPlayerY", "Player.ScreenPlayerZ",
    "Player.GfxBackend", "Player.MaxPrerenderedFrames", "Player.AAFactor",
    "Player.MSAASamples", "Player.DisableAO", "Player.DynamicAO", "Player.MaxTexDimension",
    "Player.PFReflection", "Player.AlphaRampAccuracy", "Player.HDRGlobalExposure",
    "Player.CompressTextures", "Player.UseNVidiaAPI", "Player.SoftwareVertexProcessing",
    "Player.ShowFPS", "Player.TouchOverlay", "Player.SecurityLevel",
    "Player.NumberOfTimesToShowTouchMessage",
    "Controller.ForceDisableB2S",
    "Plugin.ScoreView.LayoutFolder", "Plugin.PinMAME.PinMAMEPath",
    "Plugin.AltSound.Folder", "Plugin.Serum.SerumPath", "Plugin.VNI.VniPath",
    "Plugin.PUP.PUPFolder", "Plugin.UpscaleDMD.UpscaleMode",
    "Standalone.Haptics",
})
# The editor's settings the player reads through the table's.
BALL_CONTROL = frozenset({"Editor.ThrowBallSize", "Editor.ThrowBallMass",
                          "Editor.ThrowBallsAlwaysOn", "Editor.BallControlAlwaysOn"})

# Of those, what a table starting still reads through the table's settings, so a value
# already in its file is the one in force there. Only the playfield window is built from
# the application's alone.
READ_AT_TABLE_START = frozenset({
    *(f"{window}.{window}{part}" for window in ("Backglass", "ScoreView", "Topper")
      for part in _SAVED_DIRECTLY),
    "Player.AAFactor", "Player.PFReflection", "Player.MSAASamples", "Player.DisableAO",
    "Player.DynamicAO", "Player.MaxTexDimension", "Player.CompressTextures",
})

# What it keeps for one table only. The comment above `[TableOverride]` in the file says
# its keys are not meant for the application's; `[TableOption]` is whatever a table's
# script offers.
TABLE_ONLY_SECTIONS = frozenset({"TableOverride", "TableOption"})
TABLE_ONLY = frozenset({"Player.OverrideTableEmissionScale", "Player.EmissionScale"})


def _all_tables_only(qualified: str) -> bool:
    # A plugin's switch is read from the table's settings when a table starts.
    if qualified.startswith("Plugin.") and qualified.endswith(".Enable"):
        return False
    if qualified in BALL_CONTROL:
        return False
    return (qualified in ALL_TABLES_ONLY
            or qualified.split(".", 1)[0] in ALL_TABLES_ONLY_SECTIONS
            or qualified.startswith(ALL_TABLES_ONLY_PREFIXES))


def _read_at_table(qualified: str) -> bool:
    return not _all_tables_only(qualified) or qualified in READ_AT_TABLE_START


def _table_only(qualified: str) -> bool:
    return (qualified in TABLE_ONLY
            or qualified.split(".", 1)[0] in TABLE_ONLY_SECTIONS)


def _offered(qualified: str) -> bool:
    """Judged on the whole name rather than the section, because the file does not put
    these in sections of their own: `[Input]` holds `Mapping.LeftFlipper`, so the thing
    that says it is a binding is the key and not the heading above it."""
    parts = qualified.split(".")
    if parts[0] in HIDDEN_SECTIONS or qualified.startswith(HIDDEN_PREFIXES):
        return False
    if qualified.startswith(EDITOR_SECTIONS) or EDITOR_PHYSICS.fullmatch(qualified):
        return False
    return not any(part in parts for part in HIDDEN_PARTS)


SETTINGS_FILE = "VPinballX.ini"
_VERSION_FOLDER = re.compile(r"(\d+)\.(\d+)")


def _machine_folders() -> tuple[Path | None, Path | None]:
    """Visual Pinball's preferences folder as SDL names it per platform, and the folder
    the standalone build used before that."""
    if sys.platform == "win32":
        roaming = os.environ.get("APPDATA", "")
        return (Path(roaming) / "VPinballX" if roaming else None), None
    old = Path.home() / ".vpinball"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "VPinballX", old
    shared = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(shared) / "VPinballX", old


def own_file(bin_path: str = "") -> Path | None:
    """The settings file Visual Pinball uses when it is not given one, or None where
    there is none yet.

    Visual Pinball looks in its own version's folder, and which version a launcher runs
    is not known here, so the newest folder holding a file stands in for it.
    """
    base, old = _machine_folders()
    found = [folder / SETTINGS_FILE for folder in _version_folders(base)]
    program = Path(str(bin_path or "").strip())
    if program.name and not any(part.lower().endswith(".app") for part in program.parts):
        found.append(program.parent / SETTINGS_FILE)
    found += [folder / SETTINGS_FILE for folder in (base, old) if folder is not None]
    return next((one for one in found if one.is_file()), None)


def own_log() -> Path | None:
    """The log Visual Pinball writes, or None where there is none yet. It is in the
    preferences folder whichever settings file VPX is given."""
    base, old = _machine_folders()
    found = [*_version_folders(base), *(one for one in (base, old) if one is not None)]
    return next((one / displays.LOG_FILE for one in found
                 if (one / displays.LOG_FILE).is_file()), None)


def _version_folders(base: Path | None) -> list[Path]:
    """Visual Pinball's per-version preferences folders, the newest first."""
    if base is None:
        return []
    try:
        folders = [one for one in base.iterdir()
                   if one.is_dir() and _VERSION_FOLDER.fullmatch(one.name)]
    except OSError:
        return []
    return sorted(folders, key=lambda one: tuple(int(part) for part in one.name.split(".")),
                  reverse=True)


def settings_file(settings: Mapping[str, Any]) -> Path | None:
    """The application layer: the launcher's Settings File, or Visual Pinball's own."""
    named = str(settings.get("ini_path") or "").strip()
    if named:
        return Path(named).expanduser()
    return own_file(str(settings.get("bin_path") or ""))


def table_layer(table: str) -> Path | None:
    """The one file VPX reads for a table, resolved the way VPX resolves it.

    `<table>.ini` if it is there, else `<folder>.ini` matched without regard to case,
    else nothing yet - and `<table>.ini` is what a write would create.
    """
    game_file = Path(str(table or "").strip())
    if not game_file.name:
        return None
    beside = game_file.with_suffix(".ini")
    if beside.is_file():
        return beside
    return _game_layer(game_file)


def _game_layer(game_file: Path) -> Path | None:
    """`<folder>.ini` beside a table, matched without regard to case."""
    folder = game_file.parent
    wanted = f"{folder.name}.ini".lower()
    try:
        with os.scandir(folder) as entries:   # the return below exits part way through
            for entry in entries:
                if entry.is_file() and entry.name.lower() == wanted:
                    return Path(entry.path)
    except OSError:
        return None
    return None


def path_for(scope: str, target: str, settings: Mapping[str, Any]) -> Path | None:
    """The file a scope writes to, whether or not it exists yet."""
    if scope == SCOPE_LAUNCHER:
        return settings_file(settings)
    game_file = Path(str(target or "").strip())
    if not game_file.name:
        return None
    if scope == SCOPE_ENTRY:
        return game_file.with_suffix(".ini")
    if scope == SCOPE_FOLDER:
        return game_file.parent / f"{game_file.parent.name}.ini"
    return None


# A file is rewritten in place, so a read in the middle of a write finds it empty.
_FILES = threading.RLock()


def _read(path: Path | None) -> vini.Ini:
    if path is None or not path.is_file():
        return vini.Ini()
    try:
        with _FILES:
            text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return vini.Ini()
    return vini.parse(text)


_STORED_COLOR = re.compile(r"-?\d+")
_WEB_COLOR = re.compile(r"#([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})")


def _as_web(color: int) -> str:
    return f"#{color & 0xFF:02X}{color >> 8 & 0xFF:02X}{color >> 16 & 0xFF:02X}"


def web_color(stored: str) -> str:
    """`#RRGGBB` for a color as the file holds it, read as the program reads it; "" for
    one the program cannot read, which leaves it the default."""
    found = _STORED_COLOR.match(stored.strip())
    return _as_web(int(found.group())) if found else ""


def stored_color(written: str) -> str:
    """The number the program stores for `#RRGGBB`; anything else as it came."""
    found = _WEB_COLOR.fullmatch(written.strip())
    if found is None:
        return written
    red, green, blue = (int(part, 16) for part in found.groups())
    return str(red | green << 8 | blue << 16)


def _default_color(said: str) -> str:
    try:
        return _as_web(int(said, 16))
    except ValueError:
        return ""


def _single(said: str) -> float | None:
    """A number as the float32 the program holds it in; None where it is not one."""
    try:
        held: float = struct.unpack("f", struct.pack("f", float(said)))[0]
    except (ValueError, OverflowError):
        return None
    return held if math.isfinite(held) else None


def _shortest(said: str) -> str:
    """The fewest digits that read back as the same float32; anything else as it came."""
    held = _single(said)
    if held is None:
        return said
    for digits in range(1, 10):
        shown = f"{held:.{digits}g}"
        if _single(shown) == held:
            return "0" if held == 0 else format(Decimal(shown), "f")
    return said


def _registered(one: vini.Setting) -> vini.Setting:
    """A setting as the file describes it, or as its plugin registers it where the file
    writes it bare."""
    said = REGISTERED.get(one.qualified)
    if said is None or one.default or one.choices:
        return one
    return replace(one, default=said.default, choices=said.choices, minimum=said.minimum,
                   maximum=said.maximum,
                   kind=vini.KIND_CHOICE if said.choices else one.kind)


def _unwritten(app: vini.Ini,
               installed: Mapping[str, plugins.Plugin] | None) -> list[vini.Setting]:
    """What each plugin the program has registers that the file does not hold yet.
    Where what is installed cannot be read, a plugin the file has a section for."""
    held = {areas.plugin_of(key) for key in app.settings}
    return [_registered(vini.Setting(section, key, "", label=key))
            for qualified in REGISTERED if qualified not in app.settings
            for section, key in (vini.section_and_key(qualified),)
            if areas.plugin_of(qualified) in (held if installed is None else installed)]


def _colors(app: vini.Ini) -> frozenset[str]:
    return frozenset(key for key, one in app.settings.items()
                     if _type_of(one) == vini.KIND_COLOR)


def _numbers(app: vini.Ini) -> frozenset[str]:
    return frozenset(key for key, one in app.settings.items()
                     if _type_of(one) == vini.KIND_NUMBER) | frozenset(
        key for key, kind in TYPES.items()
        if kind == vini.KIND_NUMBER and key not in app.settings)


def _type_of(one: vini.Setting) -> str:
    """What the program says it is, and what the file implies only where it has not said.

    The ini cannot tell a switch from a number: `Enable Log` and `ImageMngPosX` both
    default to a bare 0 or 1. A setting the map does not carry - a plugin registers its
    own at runtime, and they are never in it - keeps what the file implied.
    """
    said = TYPES.get(one.qualified, "")
    if not said:
        return one.kind
    # An enumerated setting keeps what the file said, because the file is where the
    # answers and their labels are. The map only agrees that it is a choice.
    if said == "choice" and one.kind != vini.KIND_CHOICE:
        return one.kind
    # A color is a number to the program and a color here; the file is the only place
    # that says so, and it says so in the shape of the default.
    if one.kind == vini.KIND_COLOR:
        return one.kind
    return said


class VPXConfig:
    """The settings surface for one launcher, and for one table under it."""

    def scopes(self) -> tuple[str, ...]:
        return (SCOPE_LAUNCHER, SCOPE_FOLDER, SCOPE_ENTRY)

    def scopes_for(self, qualified: str) -> tuple[str, ...]:
        """The scopes one setting can be set at."""
        if _all_tables_only(qualified):
            return (SCOPE_LAUNCHER,)
        if _table_only(qualified):
            return (SCOPE_FOLDER, SCOPE_ENTRY)
        return self.scopes()

    def groups(self, settings: Mapping[str, Any]) -> tuple[ConfigGroup, ...]:
        """What the file itself says every setting is, by area.

        Read from the application ini rather than declared here: VPX writes each
        setting's label, description, default and - where the answers are a closed set -
        what each value means, into a comment above it. A setting a later build adds
        appears without this file changing, in the rest if no area names it.
        """
        schema = _read(settings_file(settings))
        installed = plugins.installed(str(settings.get("bin_path") or ""))
        by_area: dict[str, list[Field]] = {}
        for one in (*map(_registered, schema.settings.values()),
                    *_unwritten(schema, installed)):
            if _offered(one.qualified):
                area = areas.area_of(one.qualified)
                if (area == areas.PLUGINS and installed is not None
                        and areas.plugin_of(one.qualified) not in installed):
                    area = REST
                by_area.setdefault(area, []).append(_field(one))
        offered = {f.key for held in by_area.values() for f in held}
        by_area.get(areas.PLUGINS, []).sort(
            key=lambda f: areas.plugin_order(areas.plugin_of(f.key), installed))
        return tuple(
            ConfigGroup(key=key, settings=tuple(by_area[key]),
                        curated=_curated(key, offered, installed),
                        summarized=key == areas.POINT_OF_VIEW)
            for key in (*areas.AREAS, areas.POINT_OF_VIEW, REST) if by_area.get(key))

    def read(self, scope: str, target: str,
             settings: Mapping[str, Any]) -> dict[str, ConfigValue]:
        """Every setting as it stands, seen from one scope.

        `value` is what VPX will use, never what this scope happens to hold - you should
        not be shown a number that is not the one in force.
        """
        app = _read(settings_file(settings))
        table = _read(table_layer(target)) if target else vini.Ini()
        mine_path = path_for(scope, target, settings)
        mine = _read(mine_path)
        # The table layer is one file. Which of the two spellings it is decides whether
        # a folder file is reaching this table at all - and where a game folder is named
        # after the table it holds, which is the ordinary case, both spellings are the
        # same file and the two scopes coincide.
        winning = table_layer(target) if target else None
        table_scope = _scope_of(winning, target, settings)
        beneath = _beneath(target, winning)
        colors = _colors(app)
        numbers = _numbers(app)

        found: dict[str, ConfigValue] = {}
        for qualified in sorted(set(app.settings) | set(table.settings) | set(mine.settings)):
            if not _offered(qualified):
                continue
            read_by_vpx = table if _read_at_table(qualified) else vini.Ini()
            from_table = read_by_vpx.value(qualified)
            from_app = app.value(qualified)
            if from_table is not None:
                effective, source = from_table, table_scope
            elif from_app is not None:
                effective, source = from_app, SCOPE_LAUNCHER
            else:
                effective, source = "", ""
            set_here = mine.value(qualified) is not None
            last = read_by_vpx is table and set(table.settings) == {qualified}
            fallback, fallback_scope = _without(scope, qualified, app, read_by_vpx,
                                                table_scope, beneath if last else vini.Ini())
            if qualified in colors:
                effective, fallback = web_color(effective), web_color(fallback)
            elif qualified in numbers:
                effective, fallback = _shortest(effective), _shortest(fallback)
            found[qualified] = ConfigValue(
                value=effective, scope=source, set_here=set_here,
                # Three ways it is the one in force: nothing is set here to be
                # shadowed; this scope is the layer that answered; or this scope and
                # the one that answered are the same file, which is what a game folder
                # named after its table makes of the two table-layer spellings.
                in_effect=(not set_here or source == scope
                           or (read_by_vpx is table and _same(mine_path, winning))),
                fallback=fallback, fallback_scope=fallback_scope)
        return found

    def write(self, scope: str, target: str, values: Mapping[str, str],
              settings: Mapping[str, Any]) -> frozenset[str]:
        """Set values at one scope, in place. Written the way the program writes it.

        The file keeps its own shape - a value is replaced on the line it is on. The
        comments are the only documentation these settings have, and rewriting the file
        from a parse would throw all of them away.

        **A table layer is not the same as the application layer, and the program does
        not write them the same way.** Saving a table's settings removes a key it has no
        value for and one whose value equals the application's, and the file once no key
        is left; saving the application's
        writes every key, blank where it has no value. Doing it our own way would leave a
        file the program rewrites differently the first time it saves - and the parts it
        rewrote would be the parts somebody had set here.

        Returns the keys it cleared instead of writing, for holding the application's
        own value.
        """
        path = path_for(scope, target, settings)
        if path is None:
            raise ValueError(f"There is no {scope} file to write.")
        with _FILES:
            colors = _colors(_read(settings_file(settings)))
            values = {key: stored_color(str(value)) if key in colors else value
                      for key, value in values.items()}
            cleared = _inherited(scope, values, settings)
            drop = ([key for key, value in values.items()
                     if str(value) == "" or key in cleared]
                    if scope != SCOPE_LAUNCHER else [])
            keep = {key: value for key, value in values.items() if key not in drop}
            held = _read(path)
            text = vini.written(held, keep, remove=drop)
            if scope != SCOPE_LAUNCHER and held.settings and not vini.parse(text).settings:
                path.unlink(missing_ok=True)
            elif keep or path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        return cleared

    def files(self, settings: Mapping[str, Any]) -> dict[str, str]:
        """The files this launcher's settings live in.

        The application layer only. A table's own file sits beside its game file and
        travels with it; this is the one that belongs to the launcher and would be lost
        with it.
        """
        found = settings_file(settings)
        return {"application": str(found)} if found else {}

    def left_empty(self, settings: Mapping[str, Any]) -> dict[str, str]:
        """By launcher field, what an empty one stands for on this machine."""
        found = own_file(str(settings.get("bin_path") or ""))
        return {"ini_path": str(found)} if found else {}

    def blank_words(self) -> dict[str, str]:
        """By key, the word in this app's catalog for what a blank value does, where that
        is not the declared default."""
        return {**dict.fromkeys(FROM_THE_SCREEN, "from_the_screen"),
                **dict.fromkeys(FROM_THE_TABLE, "the_tables_own")}

    def label_word(self, key: str) -> str:
        """The word in this app's catalog that names a setting with no words of its own,
        or "" for one that has them."""
        return "enable" if areas.is_plugin_switch(key) else ""

    def named_values(self) -> dict[str, tuple[tuple[str, str], ...]]:
        """By key, the values the program gives a meaning of their own, each with the word
        for it in this app's catalog."""
        return dict(NAMED_VALUES)

    def reported(self) -> dict[str, tuple[str, ...]]:
        """By key, the values the program last reported it could use, the most recent
        first. A key it has reported nothing for is left out."""
        names = displays.reported_in(own_log())
        return dict.fromkeys(DISPLAYS, names) if names else {}

    def summary_rows(self, group: str, values: Mapping[str, ConfigValue]) -> tuple[str, ...]:
        """Of a summarized group, the settings drawn as rows of their own: the mode of
        each view the table starts in, then any other its settings name."""
        if group != areas.POINT_OF_VIEW:
            return ()
        held = values.get(BGSET)
        views = _VIEWS_AT.get((held.value if held else "") or "0",
                              tuple(code for _view, code in areas.VIEWS))
        used = [areas.view_mode(code) for code in views]
        named = [areas.view_mode(code) for _view, code in areas.VIEWS
                 if (one := values.get(areas.view_mode(code))) is not None
                 and one.set_here and areas.view_mode(code) not in used]
        return tuple(used + named)

    def held_groups(self, target: str) -> tuple[ConfigGroup, ...]:
        """The table options a table's settings hold. The table's script declares them
        while it runs, so this ini says nothing of their range or meaning."""
        held = _read(table_layer(target))
        options = tuple(
            Field(key=qualified, label=qualified[len(areas.TABLE_OPTION_KEYS):]
                  .replace("_", " ").strip(), type="text")
            for qualified in sorted(held.settings)
            if qualified.startswith(areas.TABLE_OPTION_KEYS)
            and held.value(qualified) is not None)
        return ((ConfigGroup(key=areas.TABLE_OPTIONS, settings=options, read_only=True),)
                if options else ())

    def shared_with_game(self, target: str) -> bool:
        """Whether this table's own settings file is also its game's."""
        return _same(path_for(SCOPE_ENTRY, target, {}), path_for(SCOPE_FOLDER, target, {}))

    def from_game(self, target: str, settings: Mapping[str, Any]) -> dict[str, str]:
        """By key, what the game's own file sets that does not reach this table because
        the table has a file of its own: each value the table's file does not hold, that
        can be set for one table and would change what it uses."""
        own = path_for(SCOPE_ENTRY, target, settings)
        if own is None or not own.is_file():
            return {}
        game = _game_layer(own)
        if game is None or _same(own, game):
            return {}
        mine, theirs = _read(own), _read(game)
        app = _read(settings_file(settings))
        return {key: value for key in sorted(theirs.settings)
                if (value := theirs.value(key)) is not None and mine.value(key) is None
                and _offered(key) and SCOPE_ENTRY in self.scopes_for(key)
                and not _alike(key, _given(app, key), value)}

    def held_for_table(self, target: str) -> dict[str, Any]:
        """What the one file VPX reads for this table sets: which scope that file is,
        which settings it changes for the table and how many, and whether it holds a
        camera."""
        winning = table_layer(target)
        held = _read(winning)
        setting = [q for q in held.settings if held.value(q) is not None]
        keys = sorted(q for q in setting if _offered(q) and _read_at_table(q)
                      and not q.startswith(POINT_OF_VIEW))
        return {
            "scope": _scope_of(winning, target, {}),
            "settings": len(keys),
            "keys": keys,
            "point_of_view": any(q.startswith(POINT_OF_VIEW) for q in setting),
        }


def _curated(area: str, offered: set[str],
             installed: Mapping[str, plugins.Plugin] | None) -> tuple[Heading, ...]:
    """An area's curated rows that this file has, under their headings."""
    if area == areas.PLUGINS:
        return areas.plugin_headings(offered, installed)
    if area == areas.POINT_OF_VIEW:
        return areas.view_headings(offered)
    kept = (Heading(one.key, tuple(key for key in one.keys if key in offered),
                    one.enabled_by,
                    pairs=tuple(pair for pair in one.pairs if set(pair.keys) <= offered),
                    switched=areas.kept_switched(one.switched, offered))
            for one in areas.CURATED.get(area, ()))
    return tuple(one for one in kept if one.keys)


def _inherited(scope: str, values: Mapping[str, str],
               settings: Mapping[str, Any]) -> frozenset[str]:
    """The keys given the application's own value at a table's scope, contextual ones
    excepted."""
    if scope == SCOPE_LAUNCHER:
        return frozenset()
    app = _read(settings_file(settings))
    return frozenset(key for key, value in values.items()
                     if str(value) != "" and not _contextual(key)
                     and _alike(key, _given(app, key), str(value)))


def _contextual(key: str) -> bool:
    return key in CONTEXTUAL or areas.is_plugin_switch(key)


def _given(app: vini.Ini, key: str) -> str | None:
    """What the application gives a key: its own value, or the default its file states
    or its plugin registers where it leaves the key blank. None where neither is
    known."""
    held = app.value(key)
    if held is not None:
        return held
    one = app.settings.get(key)
    said = _registered(one) if one is not None else REGISTERED.get(key)
    return said.default if said is not None and said.default != "" else None


def _alike(key: str, one: str | None, two: str | None) -> bool:
    """Equal the way the program compares them: as numbers, except a text setting."""
    if one is None or two is None:
        return False
    if one == two or TYPES.get(key) == "string":
        return one == two
    if TYPES.get(key) == vini.KIND_NUMBER:
        return _single(one) is not None and _single(one) == _single(two)
    try:
        return float(one) == float(two)
    except ValueError:
        return False


def _without(scope: str, qualified: str, app: vini.Ini, table: vini.Ini,
             table_scope: str, after: vini.Ini) -> tuple[str, str]:
    """What would answer if this scope stopped naming it.

    Clearing a value has to be able to say what it will follow, or somebody has to
    change it to find out what it was following. `after` is the file VPX reads for the
    table once clearing this removes the one it reads now.
    """
    if scope != SCOPE_LAUNCHER and table_scope == scope:
        from_game = after.value(qualified)
        if from_game is not None:
            return from_game, SCOPE_FOLDER
        from_app = app.value(qualified)
        return (from_app, SCOPE_LAUNCHER) if from_app is not None else ("", "")
    if scope == SCOPE_LAUNCHER:
        # Nothing is under the application layer but the program's own default, which
        # the field carries rather than the file.
        return "", ""
    # A scope that is not the one in force changes nothing by clearing.
    from_table = table.value(qualified)
    if from_table is not None:
        return from_table, table_scope
    from_app = app.value(qualified)
    return (from_app, SCOPE_LAUNCHER) if from_app is not None else ("", "")


def _beneath(target: str, winning: Path | None) -> vini.Ini:
    """The game's `<folder>.ini` where the table's own file is the one VPX reads."""
    if not target or winning is None:
        return vini.Ini()
    game = _game_layer(Path(str(target).strip()))
    return vini.Ini() if game is None or _same(game, winning) else _read(game)


def _same(one: Path | None, two: Path | None) -> bool:
    """Two paths naming one file. Compared resolved, because a game folder named after
    the table it holds makes `<table>.ini` and `<folder>.ini` the same file."""
    if one is None or two is None:
        return False
    try:
        return one.resolve() == two.resolve()
    except OSError:
        return str(one) == str(two)


def _scope_of(winning: Path | None, target: str,
              settings: Mapping[str, Any]) -> str:
    """Which scope the winning table-layer file belongs to. Entry where both spellings
    name it, because that is the one a write would create."""
    if winning is None:
        return ""
    if _same(winning, path_for(SCOPE_ENTRY, target, settings)):
        return SCOPE_ENTRY
    return SCOPE_FOLDER


def _field(one: vini.Setting) -> Field:
    """One setting as the control grammar wants it. The key is qualified, because a key
    is only unique inside its section - `Width` is in eight of them."""
    return Field(
        key=one.qualified,
        # The file gives the key where it has no label. A plugin's declaration may have
        # one, and the catalog has the words for the rest.
        label=one.label if one.label != one.key else LABELS.get(one.qualified, ""),
        type=_type_of(one),
        default=("" if one.qualified in FROM_THE_SCREEN | FROM_THE_TABLE
                 else _default_color(one.default) if _type_of(one) == vini.KIND_COLOR
                 else _shortest(one.default) if _type_of(one) == vini.KIND_NUMBER
                 else one.default),
        description="" if areas.is_plugin_switch(one.qualified) else one.description,
        choices=one.choices,
        minimum=one.minimum,
        maximum=one.maximum,
        per_table=one.qualified in areas.PER_TABLE or (
            areas.is_curated(one.qualified) and not _all_tables_only(one.qualified)),
    )
