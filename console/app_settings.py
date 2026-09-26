"""A table's Settings section: which launcher plays it, then what the program that
launcher runs does differently for this table.

The program's rows are the table's differences and nothing else. Every setting, at this
table, is one step further: Show Every Setting.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass, replace
from functools import partial
from types import SimpleNamespace
from typing import Any

from nicegui import ui

from common.i18n import t
from console import dialog as frame
from console import offload, panel, verbs, workbench
from console.data import config_groups

SCOPE_ENTRY = "entry"
ADDED = "added_settings"
ADDED_NOW = "added_setting_now"

_SHOW_ADDED = """
(() => {
  let tries = 0;
  const show = () => {
    const label = [...document.querySelectorAll('.console-workbench-body .console-fact-label')]
      .find(el => el.textContent.trim() === %s);
    const value = label && label.nextElementSibling;
    if (!value) { if (++tries < 40) setTimeout(show, 25); return; }
    value.scrollIntoView({block: 'center'});
    (value.querySelector('input:not(.hidden), textarea')
      || value.querySelector('[tabindex="0"]'))?.focus();
  };
  show();
})()
"""


def title_for(game_name: str, table_name: str, launcher_name: str,
              folder_tables: int) -> str:
    """Named for the table being edited. The game names it, and the table is added where
    the game has more than one."""
    subject = (t("console.app_settings.game_and_table", game=game_name, table=table_name)
               if folder_tables > 1 and table_name else game_name)
    return t("console.app_settings.settings", table=subject, launcher_name=launcher_name)


def shared_note(found: dict, folder_tables: int) -> tuple[Any, Any] | None:
    """Where this table's file is also its game's, what a value set for it reaches."""
    if folder_tables <= 1 or not found.get("shared_with_game"):
        return None
    return panel.intro(t("console.app_settings.shared_with_game", count=folder_tables - 1))


async def section(context: dict[str, Any]) -> None:
    table = next((one for one in context["tables"] if one.get("id") == context["lens"]),
                 None)
    entries = ([(panel.HEADING, t("console.workbench.launcher_2")),
                *workbench.launcher_rows(context, table),
                *await _program_entries(context, table)]
               if table is not None else [])
    with ui.column().classes("gap-0 console-form"):
        if table is None:
            ui.label(t("console.workbench.no_table_selected")).classes("console-help")
            return
        panel.facts(ui, entries)
    ui.run_javascript(workbench._KEEP_SCROLL
                      % f"settings:{table.get('id') or ''}".replace("'", "\\'"))
    if said := context["state"].pop(ADDED_NOW, None):
        ui.run_javascript(_SHOW_ADDED % json.dumps(said))


def _runs(context: dict[str, Any], table: dict[str, Any]) -> dict[str, Any] | None:
    held = (context.get("launchers") or {}).get("launchers") or []
    return next((one for one in held if one["launcher_id"] == table.get("launcher")), None)


async def _program_entries(context: dict[str, Any],
                           table: dict[str, Any]) -> list[tuple[Any, Any]]:
    launcher = _runs(context, table)
    if launcher is None or not launcher.get("has_config"):
        return []
    library = context["library"]
    entries: list[tuple[Any, Any]] = [(panel.HEADING, t(
        "console.app_settings.for_this_table", app=launcher.get("app_name") or ""))]
    if note := workbench._program_note(launcher):
        return [*entries, panel.intro(note)]
    table_id = str(table.get("id") or "")
    try:
        found = await offload.io(library.launcher_config, launcher["launcher_id"],
                                 table_id, SCOPE_ENTRY)
    except Exception as exc:  # noqa: BLE001 - this says why, never 500s
        return [*entries, panel.intro(t("said.could_not_read_the_settings", exc=exc))]

    groups = config_groups(found)
    values = dict(found.get("values") or {})
    inner: dict[str, Any] = {
        "library": library, "launcher": launcher, "config_groups": groups,
        "config_values": values, "config_scope": SCOPE_ENTRY, "config_table": table_id,
        "playing": await offload.io(workbench._playing, library),
        "state": context["state"], "rebuild": context["rebuild"],
        "saved": context.get("saved"),
    }
    if shared := shared_note(found, len(context.get("tables") or []) or 1):
        entries.append(shared)
    if reach := dict(found.get("from_game") or {}):
        entries += _from_game_entries(inner, reach)
    if others := _others(context, table, launcher):
        inner["config_more"] = ForAll(inner, others, bool(found.get("shared_with_game")),
                                      list(context.get("tables") or []),
                                      _for_every_table(groups), inner["rebuild"])
    added = _added(context["state"], table_id)
    blocks = differences(groups, values, added)
    view = point_of_view(groups, values, added)
    options = table_options(groups, values)
    if not blocks and view is None and options is None:
        entries.append(panel.intro(t("console.app_settings.same_as_all_tables")))
    if view is not None:
        blocks.append((view.label, view.rows))
    entries += await workbench._setting_entries(
        inner, [(label, "", fields) for label, fields in blocks], curated=True, sub=True,
        pairs=named_pairs(groups))
    remove = partial(_remove, inner)
    if view is not None:
        entries += _camera_entries(view, remove, inner["playing"])
    if options is not None:
        entries += _option_entries(options, values, remove, inner["playing"])
    if offered := addable(groups, values, added):
        entries.append((panel.FULL, partial(_add_picker, context, added, offered)))
    entries.append((panel.FULL, panel.action(
        t("console.app_settings.show_every_setting"),
        partial(_every_setting, context, table, inner), icon=verbs.DRILL)))
    return entries


def differences(groups: Sequence[Any], values: dict[str, Any],
                added: Collection[str] = ()) -> list[tuple[str, list[Any]]]:
    """What this table's file sets, what reaches it from its game's and what was just
    added, by area: the rows an area curates first, in its order, then the rest in the
    program's. A plugin's rows lead with the plugin's name, which is all that tells five
    Enables apart, and a row whose label another setting in its area shares leads with
    its window's."""
    names = workbench._plugin_names(groups)
    found = []
    for group in groups:
        if group.summarized or getattr(group, "read_only", False):
            continue
        order = {key: at for at, key in
                 enumerate(key for heading in group.curated for key in heading.keys)}
        shown = _whole(group, {field.key for field in group.settings
                               if _differs(values.get(field.key) or {}) or field.key in added})
        paired = {key for pair in _pairs_of(group) for key in pair.keys}
        fields = sorted((field for field in group.settings if field.key in shown),
                        key=lambda field: order.get(field.key, len(order)))
        if fields:
            found.append((group.label, [field if field.key in paired
                                        else _named(field, group, names) for field in fields]))
    return found


def _pairs_of(group: Any) -> list[Any]:
    return [pair for heading in group.curated for pair in getattr(heading, "pairs", ())]


def _whole(group: Any, keys: set[str]) -> set[str]:
    """`keys`, and the rest of each pair one of them is in."""
    return keys | {key for pair in _pairs_of(group) if not keys.isdisjoint(pair.keys)
                   for key in pair.keys}


def named_pairs(groups: Sequence[Any]) -> list[Any]:
    """Each pair, named as it is away from its heading: by its plugin, or by its window
    where the heading has a name."""
    names = workbench._plugin_names(groups)
    found = []
    for group in groups:
        for heading in group.curated:
            for pair in getattr(heading, "pairs", ()):
                found.append(SimpleNamespace(**{**vars(pair),
                                                "label": _pair_name(heading, pair, names)}))
    return found


def _pair_name(heading: Any, pair: Any, names: dict[str, str]) -> str:
    section = workbench._section_of(pair.keys[0])
    if section.startswith(workbench.PLUGIN_SECTION):
        return workbench.plugin_row(section, pair.label, names)
    if heading.label:
        return t("console.app_settings.window_row", window=heading.label, label=pair.label)
    return pair.label


def _differs(held: dict[str, Any]) -> bool:
    return bool(held.get("set_here")) or held.get("scope") == "folder"


def _shown(group: Any, values: dict[str, Any], added: Collection[str]) -> bool:
    return any(_differs(values.get(field.key) or {}) or field.key in added
               for field in group.settings)


def _added(state: dict[str, Any], table_id: str) -> list[str]:
    """The settings Add a Setting drew at this table, forgotten when another is open."""
    held = state.get(ADDED) or {}
    if held.get("table") != table_id:
        held = state[ADDED] = {"table": table_id, "keys": []}
    return list(held["keys"])


def addable(groups: Sequence[Any], values: dict[str, Any],
            added: Collection[str]) -> list[tuple[Any, str]]:
    """What this table could be given a value of its own for and is not showing yet, each
    with its area: the settings commonly set per table first, then the rest. Of the point
    of view, only the view modes it would draw."""
    names = workbench._plugin_names(groups)
    pairs = {pair.keys[0]: pair for pair in named_pairs(groups)}
    first: list[tuple[Any, str]] = []
    rest: list[tuple[Any, str]] = []
    for group in groups:
        if getattr(group, "read_only", False) or (
                group.summarized and _shown(group, values, added)):
            continue
        shown = _whole(group, {field.key for field in group.settings
                               if field.key in added or _differs(values.get(field.key) or {})})
        later = {key for pair in _pairs_of(group) for key in pair.keys[1:]}
        for field in group.settings:
            if (field.key in shown or field.key in later
                    or SCOPE_ENTRY not in (field.scopes or (SCOPE_ENTRY,))
                    or (group.summarized and field.key not in group.rows)):
                continue
            pair = pairs.get(field.key)
            (first if field.per_table else rest).append(
                (SimpleNamespace(**{**vars(field), "label": pair.label}) if pair is not None
                 else _named(field, group, names), str(group.label)))
    return first + rest


def _add_picker(context: dict[str, Any], added: list[str],
                offered: list[tuple[Any, str]]) -> None:
    """Picking one draws its row, with the value the table uses now, and focuses it."""
    headings = {}
    lead = offered[0][0]
    rest = next((field.key for field, _area in offered if not field.per_table), None)
    if lead.per_table:
        headings[lead.key] = t("console.app_settings.commonly_set_per_table")
        if rest is not None:
            headings[rest] = t("console.app_settings.everything_else")
    labels = {field.key: str(field.label) for field, _area in offered}
    picker = panel.SettingPicker(
        labels, areas={field.key: area for field, area in offered}, headings=headings,
        label=t("console.app_settings.add_a_setting")) \
        .props('dense outlined options-dense input-debounce=0 hide-selected fill-input '
               'popup-content-class="console-picker-popup"') \
        .classes("w-full mt-2")

    async def pick() -> None:
        key = str(picker.value or "")
        if key not in labels:
            return
        context["state"][ADDED]["keys"] = [*added, key]
        context["state"][ADDED_NOW] = labels[key]
        await context["rebuild"]()

    picker.on_value_change(pick)
    ui.run_javascript(workbench._ADD_BOX % (picker.id, "false"))


def _named(field: Any, group: Any, names: dict[str, str]) -> Any:
    section = workbench._section_of(field.key)
    if section.startswith(workbench.PLUGIN_SECTION):
        label = workbench.plugin_row(section, field.label, names)
    elif (sum(one.label == field.label for one in group.settings) > 1
          and (window := _window_of(field.key, group))):
        label = t("console.app_settings.window_row", window=window, label=field.label)
    else:
        return field
    return SimpleNamespace(**{**vars(field), "label": label})


def _window_of(key: str, group: Any) -> str:
    """The curated heading a setting is drawn under, or the one whose keys its own
    continues: `BackglassFSWidth` goes with the heading of `BackglassOutput` and
    `BackglassDisplay`."""
    held = next((heading for heading in group.curated if key in heading.keys), None)
    if held is not None:
        return str(held.label)
    name = key.rsplit(".", 1)[-1]
    for heading in group.curated:
        names = [one.rsplit(".", 1)[-1] for one in heading.keys]
        stem = os.path.commonprefix(names)
        if (len(names) > 1 and stem and name.startswith(stem)
                and {workbench._section_of(one) for one in heading.keys}
                == {workbench._section_of(key)}):
            return str(heading.label)
    return ""


def point_of_view(groups: Sequence[Any], values: dict[str, Any],
                  added: Collection[str] = ()) -> SimpleNamespace | None:
    """A summarized group, where anything in it differs at this table or was just added:
    the rows it draws, each named by its heading where they share a label, and the
    headings the rest is saved under."""
    group = next((one for one in groups if one.summarized), None)
    if group is None or not _shown(group, values, added):
        return None
    fields = {field.key: field for field in group.settings}
    drawn = [key for key in getattr(group, "rows", ()) if key in fields]
    camera = {key: values.get(key) or {} for key in fields if key not in drawn}
    return SimpleNamespace(
        label=group.label, rows=[_named(fields[key], group, {}) for key in drawn],
        views=[str(heading.label) for heading in group.curated
               if any(_differs(camera.get(key) or {}) for key in heading.keys)],
        own=[key for key, held in camera.items() if held.get("set_here")],
        reaching=any(_differs(held) for held in camera.values()))


def _camera_entries(view: SimpleNamespace, remove: Callable[[list[str]], Any],
                    playing: bool) -> list[tuple[Any, Any]]:
    """The rest of the summarized group as one row, with Reset where the table holds it."""
    entries: list[tuple[Any, Any]] = [
        (t("console.app_settings.camera"), _dotted(camera_said(view), bool(view.own)))]
    if view.own:
        entries.append((panel.ASIDE, _reset(t("word.reset"), partial(remove, view.own),
                                            t("console.app_settings.camera_reset.help"),
                                            playing)))
    entries.append(panel.note(t("console.app_settings.camera.help")))
    return entries


def camera_said(view: SimpleNamespace) -> str:
    said = t("console.workbench.saved_for_this_table" if view.own
             else "console.app_settings.saved_for_this_game" if view.reaching
             else "console.app_settings.the_tables_own")
    if view.views and view.reaching:
        return t("console.app_settings.saved_in_views", saved=said,
                 views=", ".join(view.views))
    return said


def table_options(groups: Sequence[Any], values: dict[str, Any]) -> tuple[str, list[Any]] | None:
    """A read-only group's settings that differ at this table, under its label."""
    for group in groups:
        fields = [field for field in group.settings
                  if _differs(values.get(field.key) or {})]
        if getattr(group, "read_only", False) and fields:
            return group.label, fields
    return None


def _option_entries(options: tuple[str, list[Any]], values: dict[str, Any],
                    remove: Callable[[list[str]], Any],
                    playing: bool) -> list[tuple[Any, Any]]:
    """Each as the file holds it, with Reset where the table holds it, and Reset All."""
    label, fields = options
    entries: list[tuple[Any, Any]] = [(panel.FULL, partial(workbench._subheading, label))]
    own = []
    for field in fields:
        held = values.get(field.key) or {}
        entries.append((field.label, _dotted(str(held.get("value") or ""),
                                             bool(held.get("set_here")))))
        if held.get("set_here"):
            own.append(field.key)
            entries.append((panel.ASIDE, _reset(
                t("word.reset"), partial(remove, [field.key]),
                t("console.app_settings.option_reset.help"), playing)))
        elif mark := workbench._config_mark(held, SCOPE_ENTRY, field):
            entries.append((panel.ASIDE, mark))
    if len(own) > 1:
        entries.append((panel.FULL, _reset(
            t("console.app_settings.reset_all"), partial(remove, own),
            t("console.app_settings.option_reset.help"), playing, inline=False)))
    return entries


def _dotted(text: str, own: bool) -> Callable[[], None]:
    """A value that is not edited here, with the dot where this table sets it."""
    def draw() -> None:
        with ui.row().classes("items-center gap-1 no-wrap console-field-row"):
            ui.element("span").classes(
                "console-mark console-mark--full console-named-mark").set_visibility(own)
            ui.label(text).classes("console-fact-value truncate min-w-0")
    return draw


def _reset(label: str, on_click: Callable[[], Any], hint: str, playing: bool, *,
           inline: bool = True) -> Callable[[], None]:
    return panel.action(label, on_click, icon=verbs.RESET, inline=inline,
                        enabled=not playing,
                        hint=t(workbench.PLAYING_NOTE) if playing else hint)


async def _remove(inner: dict[str, Any], keys: list[str]) -> None:
    """Takes these off the table's own settings, and draws the section again."""
    try:
        await offload.io(inner["library"].write_launcher_config,
                         inner["launcher"]["launcher_id"], dict.fromkeys(keys, ""),
                         table=inner["config_table"], scope=SCOPE_ENTRY)
    except Exception as exc:  # noqa: BLE001 - said, never raised into the page
        ui.notify(t("said.could_not_clear_it", exc=exc), type="negative")
        return
    await inner["rebuild"]()


async def _every_setting(context: dict[str, Any], table: dict[str, Any],
                         inner: dict[str, Any]) -> None:
    """All Settings, at this table, over the panel. The panel is drawn again on the way
    out, since anything here may have changed what it lists."""
    count = len(context.get("tables") or []) or 1
    title = title_for(str((context.get("game") or {}).get("name") or ""),
                      workbench._table_line(table),
                      str(inner["launcher"].get("display_name") or ""), count)
    every: dict[str, Any] = {**inner, "state": {"all_settings": {}}}
    every.pop("config_values", None)

    with frame.opened(title, full=True) as dialog:
        body = ui.column().classes("w-full grow min-h-0 gap-0 overflow-auto")

        async def redraw() -> None:
            every.pop("config_values", None)
            body.clear()
            with body:
                await workbench._all_settings(every)

        every["rebuild"] = redraw
        if (more := inner.get("config_more")) is not None:
            every["config_more"] = replace(more, rebuild=redraw)
        await redraw()
        with frame.footer():
            frame.answer(t("word.done"), dialog.close, icon=verbs.DONE)

    dialog.on("hide", lambda: context["rebuild"]())
    dialog.open()


def _from_game_entries(inner: dict[str, Any], reach: dict[str, str]) -> list[tuple[Any, Any]]:
    """How many of the game's own settings this table's file keeps from reaching it, and
    Copy the Game's Settings Here."""
    playing = bool(inner["playing"])
    return [panel.intro(t("console.app_settings.from_game", count=len(reach))),
            (panel.FULL, panel.action(
                t("console.app_settings.copy_from_game"),
                partial(_copy_from_game, inner, reach), icon=verbs.COPY,
                enabled=not playing,
                hint=t(workbench.PLAYING_NOTE) if playing
                else t("console.app_settings.copy_from_game.help")))]


async def _copy_from_game(inner: dict[str, Any], reach: dict[str, str]) -> None:
    try:
        await offload.io(inner["library"].write_launcher_config,
                         inner["launcher"]["launcher_id"], reach,
                         table=inner["config_table"], scope=SCOPE_ENTRY)
    except Exception as exc:  # noqa: BLE001 - said, never raised into the page
        ui.notify(t("said.could_not_save_it", exc=exc), type="negative")
        return
    ui.notify(t("console.app_settings.copied_from_game", count=len(reach)), type="positive")
    await inner["rebuild"]()


def _others(context: dict[str, Any], table: dict[str, Any],
            launcher: dict[str, Any]) -> list[dict[str, Any]]:
    """The game's other tables that run on the same program, each with its launcher."""
    found = []
    for other in context.get("tables") or []:
        runs = _runs(context, other)
        if (other.get("id") != table.get("id") and runs is not None
                and runs.get("has_config") and runs.get("app") == launcher.get("app")):
            found.append({"table": other, "launcher_id": runs["launcher_id"]})
    return found


def _read_all(library: Any, others: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for one in others:
        _read_settings(library, one)
    return others


def _read_settings(library: Any, one: dict[str, Any]) -> None:
    """Another table's settings as they stand, whether its file is also the game's, and
    whether the game's file is the one it reads."""
    found = library.launcher_config(one["launcher_id"], str(one["table"].get("id") or ""),
                                    SCOPE_ENTRY)
    one["values"] = dict(found.get("values") or {})
    one["shares"] = bool(found.get("shared_with_game"))
    one["reads_game"] = any((held or {}).get("scope") == "folder"
                            for held in one["values"].values())


def _for_every_table(groups: Sequence[Any]) -> frozenset[str]:
    """What Set for All offers: whatever one table can hold, but the camera and the table
    options."""
    found: set[str] = set()
    for group in groups:
        if getattr(group, "read_only", False):
            continue
        drawn = set(getattr(group, "rows", ())) if group.summarized else None
        found.update(field.key for field in group.settings
                     if (drawn is None or field.key in drawn)
                     and SCOPE_ENTRY in (field.scopes or (SCOPE_ENTRY,)))
    return frozenset(found)


def already_uses(other: dict[str, Any], field: Any, value: str, shares_here: bool) -> bool:
    """Whether another of the game's tables uses this value: it reads this table's file,
    which is also the game's, or has the value already."""
    if shares_here and other.get("reads_game"):
        return True
    held = (other.get("values") or {}).get(field.key) or {}
    return workbench._same_value(field, str(held.get("value") or ""), value)


@dataclass
class ForAll:
    """Set for All N Tables, beside a value this table sets itself that another of its
    game's tables does not use. A pair's row hands in its other rows as `paired`, and
    each of them set here is written with it. `rebuild` draws again whatever offered it.

    Nothing is offered until `ready` has read the other tables."""

    inner: dict[str, Any]
    others: list[dict[str, Any]]
    shares_here: bool
    tables: list[dict[str, Any]]
    offered: frozenset[str]
    rebuild: Callable[[], Awaitable[Any]]
    read: bool = False

    def _own(self, key: str, held: dict) -> bool:
        return key in self.offered and bool(held.get("set_here")) \
            and bool(held.get("in_effect", True))

    async def ready(self, values: dict[str, Any]) -> None:
        """Reads the other tables, once, when one of `values` is this table's own."""
        if self.read or not any(self._own(key, held or {}) for key, held in values.items()):
            return
        self.read = True
        try:
            await offload.io(_read_all, self.inner["library"], self.others)
        except Exception:  # noqa: BLE001 - without them the page offers no Set for All
            self.others = []

    def __call__(self, held: dict, field: Any,
                 *paired: tuple[dict, Any]) -> Callable[[], None] | None:
        own = [(one, str(said.get("value") or "")) for said, one in ((held, field), *paired)
               if self._own(one.key, said)]
        if not self.read or all(already_uses(other, one, value, self.shares_here)
                                for other in self.others for one, value in own):
            return None
        playing = bool(self.inner.get("playing"))
        return panel.action(
            t("console.app_settings.set_for_all", count=len(self.others) + 1),
            partial(_set_for_all, self.inner, self.others, own, self.shares_here,
                    self.tables, self.rebuild),
            icon=verbs.SHARE, inline=True, enabled=not playing,
            hint=t(workbench.PLAYING_NOTE) if playing
            else t("console.app_settings.set_for_all.help"))


def write_for_all(library: Any, others: list[dict[str, Any]], field: Any, value: str,
                  shares_here: bool) -> list[dict[str, Any]]:
    """Writes the value into each other table's own file, the one whose file is also the
    game's first, and none that uses it by then. Returns the tables written that read the
    game's file before, and no longer do."""
    cut = []
    for one in sorted(others, key=lambda one: not one.get("shares")):
        _read_settings(library, one)
        if already_uses(one, field, value, shares_here):
            continue
        library.write_launcher_config(one["launcher_id"], {field.key: value},
                                      table=str(one["table"].get("id") or ""),
                                      scope=SCOPE_ENTRY)
        if one["reads_game"]:
            cut.append(one["table"])
        _read_settings(library, one)
    return cut


def as_one(library: Any, targets: list[dict[str, Any]],
           groups: Sequence[Any]) -> dict[str, dict[str, Any]]:
    """Each setting as several tables hold it, in one `held`: set where any of them sets
    it, in effect where each that sets it has it in effect, with `each` table's value in
    use and `varies` where those differ, holding no value of its own then."""
    for one in targets:
        _read_settings(library, one)
    fields = {field.key: field for group in groups for field in group.settings}
    found = {}
    for key in dict.fromkeys(key for one in targets for key in one["values"]):
        field = fields.get(key)
        default = str(getattr(field, "default", "") or "")
        held = [(one["table"], (one["values"].get(key) or {})) for one in targets]
        setting = [one for _, one in held if one.get("set_here")]
        merged = dict(setting[0] if setting else held[0][1])
        each = [(table, str(one.get("value") or "") or default) for table, one in held]
        merged.update(set_here=bool(setting),
                      in_effect=all(one.get("in_effect", True) for one in setting),
                      each=each)
        if any(not workbench._same_value(field, each[0][1], value) for _, value in each):
            merged.update(varies=True, value="")
        found[key] = merged
    return found


def write_shared(library: Any, targets: list[dict[str, Any]], groups: Sequence[Any],
                 values: dict[str, str]) -> dict[str, Any]:
    """Values written at each of several tables: a value to each not using it yet, as Set
    for All does, and a blank to each that sets one. Returns under `cut` the tables
    written that read the game's file before, and no longer do."""
    fields = {field.key: field for group in groups for field in group.settings}
    cut = [table for key, value in values.items() if value != ""
           for table in write_for_all(library, targets, fields[key], value, False)]
    blank = [key for key, value in values.items() if value == ""]
    for one in targets if blank else []:
        _read_settings(library, one)
        held = {key: "" for key in blank
                if (one["values"].get(key) or {}).get("set_here")}
        if held:
            library.write_launcher_config(one["launcher_id"], held,
                                          table=str(one["table"].get("id") or ""),
                                          scope=SCOPE_ENTRY)
    return {"cut": cut}


async def _set_for_all(inner: dict[str, Any], others: list[dict[str, Any]],
                       own: Sequence[tuple[Any, str]], shares_here: bool,
                       tables: list[dict[str, Any]],
                       rebuild: Callable[[], Awaitable[Any]]) -> None:
    try:
        cut = await offload.io(lambda: [
            table for field, value in own
            for table in write_for_all(inner["library"], others, field, value, shares_here)])
    except Exception as exc:  # noqa: BLE001 - said, never raised into the page
        ui.notify(t("said.could_not_save_it", exc=exc), type="negative")
    else:
        ui.notify(t("console.app_settings.set_for_all_done", count=len(others) + 1),
                  type="positive")
        if cut:
            workbench.no_longer_reads_game(cut, tables)
    await workbench._keeping_place(ui.context.client, rebuild, own[0][0].key)
