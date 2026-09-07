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

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from common.apps.contract import (
    SCOPE_ENTRY,
    SCOPE_FOLDER,
    SCOPE_LAUNCHER,
    ConfigGroup,
    ConfigValue,
    Field,
)

from . import ini as vini

# Which sections feed which group. Declared rather than derived from section names,
# because they do not line up: the backglass DMD overlay keys sit with the B2S plugin
# while the score view has a section of its own, so a group spans sections and a section
# can feed two groups.
GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("backglass", "Backglass", ("Backglass", "Plugin.B2S", "Plugin.B2SLegacy")),
    # VPX's `[DMD]` and its dot-matrix plugins belong here: the window VPX called the
    # DMD is the one this project calls the score view, and translating its section
    # names into our words is the point of declaring groups at all.
    ("scoreview", "Score View", ("ScoreView", "Plugin.ScoreView", "DMD",
                                 "Plugin.FlexDMD", "Plugin.DMDUtil", "Plugin.AlphaDMD",
                                 "Plugin.UpscaleDMD")),
    ("rom", "ROM", ("Plugin.PinMAME", "Plugin.AltSound", "Plugin.Serum", "Plugin.VNI")),
    ("play", "Playing", ("Player", "Standalone")),
)

# Everything the groups above do not name. Not fifty groups named after fifty sections:
# an editor over a thousand keys is a browser, and the way through it is search rather
# than a rail nobody can hold in their head.
REST = ("more", "More settings")

_GROUPED = {section for _key, _label, sections in GROUPS for section in sections}

# Read but never offered. `[Version]` is what VPX wrote about itself, not something to
# set, and the per-table one carries a table's own version.
HIDDEN_SECTIONS = frozenset({"Version", "RecentDir", "TableOverride"})


def _app_ini(settings: Mapping[str, Any]) -> Path | None:
    """The application layer. An override wins, because that is what it is for."""
    for key in ("ini_override", "ini_path"):
        named = str(settings.get(key) or "").strip()
        if named:
            return Path(named).expanduser()
    return None


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
    folder = game_file.parent
    wanted = f"{folder.name}.ini".lower()
    try:
        for entry in os.scandir(folder):
            if entry.is_file() and entry.name.lower() == wanted:
                return Path(entry.path)
    except OSError:
        return None
    return None


def path_for(scope: str, target: str, settings: Mapping[str, Any]) -> Path | None:
    """The file a scope writes to, whether or not it exists yet."""
    if scope == SCOPE_LAUNCHER:
        return _app_ini(settings)
    game_file = Path(str(target or "").strip())
    if not game_file.name:
        return None
    if scope == SCOPE_ENTRY:
        return game_file.with_suffix(".ini")
    if scope == SCOPE_FOLDER:
        return game_file.parent / f"{game_file.parent.name}.ini"
    return None


def _read(path: Path | None) -> vini.Ini:
    if path is None or not path.is_file():
        return vini.Ini()
    try:
        return vini.parse(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return vini.Ini()


class VPXConfig:
    """The settings surface for one launcher, and for one table under it."""

    def scopes(self) -> tuple[str, ...]:
        return (SCOPE_LAUNCHER, SCOPE_FOLDER, SCOPE_ENTRY)

    def groups(self, settings: Mapping[str, Any]) -> tuple[ConfigGroup, ...]:
        """What the file itself says every setting is.

        Read from the application ini rather than declared here: VPX writes each
        setting's label, description, default and - where the answers are a closed set -
        what each value means, into a comment above it. A setting a later build adds
        appears without this file changing.
        """
        schema = _read(_app_ini(settings))
        by_section: dict[str, list[Field]] = {}
        for one in schema.settings.values():
            if one.section in HIDDEN_SECTIONS:
                continue
            by_section.setdefault(one.section, []).append(_field(one))

        built: list[ConfigGroup] = []
        for key, label, sections in GROUPS:
            held = [f for section in sections for f in by_section.get(section, ())]
            if held:
                built.append(ConfigGroup(key=key, label=label, settings=tuple(held)))
        rest = [f for section, held in sorted(by_section.items())
                if section not in _GROUPED for f in held]
        if rest:
            built.append(ConfigGroup(key=REST[0], label=REST[1], settings=tuple(rest)))
        return tuple(built)

    def read(self, scope: str, target: str,
             settings: Mapping[str, Any]) -> dict[str, ConfigValue]:
        """Every setting as it stands, seen from one scope.

        `value` is what VPX will use, never what this scope happens to hold - you should
        not be shown a number that is not the one in force.
        """
        app = _read(_app_ini(settings))
        table = _read(table_layer(target)) if target else vini.Ini()
        mine_path = path_for(scope, target, settings)
        mine = _read(mine_path)
        # The table layer is one file. Which of the two spellings it is decides whether
        # a folder file is reaching this table at all - and where a game folder is named
        # after the table it holds, which is the ordinary case, both spellings are the
        # same file and the two scopes coincide.
        winning = table_layer(target) if target else None
        table_scope = _scope_of(winning, target, settings)

        found: dict[str, ConfigValue] = {}
        for qualified in sorted(set(app.settings) | set(table.settings) | set(mine.settings)):
            if qualified.split(".", 1)[0] in HIDDEN_SECTIONS:
                continue
            from_table = table.value(qualified)
            from_app = app.value(qualified)
            if from_table is not None:
                effective, source = from_table, table_scope
            elif from_app is not None:
                effective, source = from_app, SCOPE_LAUNCHER
            else:
                effective, source = "", ""
            set_here = mine.value(qualified) is not None
            found[qualified] = ConfigValue(
                value=effective, scope=source, set_here=set_here,
                in_effect=not set_here or _same(mine_path, winning))
        return found

    def write(self, scope: str, target: str, values: Mapping[str, str],
              settings: Mapping[str, Any]) -> None:
        """Set values at one scope, in place.

        The file keeps its own shape - a value is replaced on the line it is on. The
        comments are the only documentation these settings have, and rewriting the file
        from a parse would throw all of them away.
        """
        path = path_for(scope, target, settings)
        if path is None:
            raise ValueError(f"There is no {scope} file to write.")
        held = _read(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(vini.written(held, dict(values)), encoding="utf-8")

    def inherited_from_folder(self, target: str,
                              settings: Mapping[str, Any]) -> dict[str, str]:
        """What a folder file is currently giving this table, for the confirm that has
        to be shown before a table file takes it off them."""
        if table_layer(target) is not None and table_layer(target).suffix:
            beside = Path(target).with_suffix(".ini")
            if beside.is_file():
                return {}
        folder = path_for(SCOPE_FOLDER, target, settings)
        if folder is None or not folder.is_file():
            return {}
        return {q: one.value for q, one in _read(folder).settings.items()}


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
        label=one.label,
        type=one.kind,
        default=one.default,
        description=one.description,
        choices=one.choices,
        minimum=one.minimum,
        maximum=one.maximum,
    )
