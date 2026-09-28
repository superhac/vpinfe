"""The panel: a rail of named destinations, one open, and the facts beside it.

The side pane draws it about a game; Settings draws it about the install. Both render
through here, so a treatment is changed in one place rather than in each surface that
happens to show the same kind of value.

Every control constructor returns the callable `facts` takes as a value, so it drops
into an entry list as the second half of a pair.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from nicegui import ui

from common import icons
from common.i18n import t
from console import game_tables, list_art, offload, tag_chips, verbs
from console.on_page import on_page

# Rows that are not a fact. A group's title and an action strip span both columns, so
# every group keeps the one shared label width.
HEADING = object()
FULL = object()
# The value column alone, for a line that belongs to the control above it rather than
# to the row. Across both columns it starts at the label's edge and reads as a caption
# for the label instead.
ASIDE = object()
# Both columns, for a line belonging to the heading above it. Sits tight under the
# heading and leaves room before the first row, so it reads as part of the heading
# rather than as something between two groups.
LEDE = object()

# A rail row that names the rows under it rather than opening anything.
GROUP = object()

# The rail's width. A lever rather than a literal: the pane is narrow and Settings is
# not, and both rails are the same control.
RAIL_PX = 152


def header(name: str, note: str = "",
           findings: Sequence[Callable[[], None]] = ()) -> None:
    """What the content under it is about, where the rail row is too far away to say it.

    `note` is drawn inside the same rule as the name, and so is each of `findings`: what is
    wrong with everything under it, before the first of its headings.
    """
    if not note and not findings:
        ui.label(name).classes("text-base console-workbench-title console-panel-heading")
        return
    with ui.element("div").classes("console-panel-heading"):
        ui.label(name).classes("text-base console-workbench-title")
        if note:
            ui.label(note).classes("console-help console-panel-note")
        for finding in findings:
            finding()


def facts(target: Any, entries: Sequence[tuple[Any, Any]]) -> None:
    """The facts of one section, as (label, value) pairs.

    One list for all of them, not a row each, so the label column is the width of the
    longest label. A row whose value is not text passes a callable and draws its own;
    it has to be in *this* list, or it sizes a label column of its own and its value
    starts somewhere else entirely.

    `min-w-0` is what lets a value shrink: a grid item refuses to go below its content
    width without it, and the row wraps instead of ellipsing.
    """
    with target.element("div").classes("console-facts"):
        for label, value in entries:
            if label is HEADING:
                target.label(str(value)).classes("console-fact-heading")
                continue
            if label is FULL:
                with target.element("div").classes("console-fact-full"):
                    value()
                continue
            if label is LEDE:
                with target.element("div").classes("console-fact-full console-fact-lede"):
                    value()
                continue
            if label is ASIDE:
                with target.element("div").classes("console-fact-aside"):
                    value()
                continue
            # As given. A label that came from a registry is already the answer, and
            # re-casing it is how "RAR Tool Path" reached a user as "Rar Tool Path" -
            # the casing rule is a fallback for a bare key, not a filter over finished
            # words. A surface that writes its labels in prose cases them on the way in.
            target.label(str(label)).classes("console-fact-label")
            _draw_value(target, value)


_CLIPPED_JS = """
if (!window.__hubClipWatch) {
  window.__hubClipWatch = true;
  const mark = () => {
    for (const el of document.querySelectorAll('.console-fact-value')) {
      el.classList.toggle('console-clipped', el.scrollWidth > el.clientWidth + 1);
    }
  };
  const soon = () => requestAnimationFrame(() => requestAnimationFrame(mark));
  new MutationObserver(soon).observe(document.body,
                                     {childList: true, subtree: true});
  new ResizeObserver(soon).observe(document.body);
  soon();
}
"""


def install_fact_tooltips() -> None:
    """Watch which fact values are clipped. Once per page, before any panel."""
    ui.run_javascript(_CLIPPED_JS)


def _draw_value(target: Any, value: Any) -> None:
    if callable(value):
        value()
        return
    target.label(str(value)).classes("console-fact-value truncate min-w-0") \
        .tooltip(str(value))


def sections(entries: Sequence[tuple[Any, ...]], current: str,
             on_pick: Callable[[str], Any], *, rail_px: int = RAIL_PX) -> Any:
    """The rail and the region it opens into, returning the region.

    `entries` are `(key, catalog key)` with an optional third element for a hint's key
    and a fourth for a mark drawn before the name, or `(GROUP, name)` for a heading over the rows
    that follow it.

    Two regions, not loose rows: the rail scrolls on its own and the open page beside it
    holds still. Left loose, every row takes a grid track of its own and the region they
    are meant to sit beside gets whatever is left, which on a long index is a few lines.
    """
    frame = ui.element("div").classes("w-full grow min-h-0 console-sections") \
        .style(f"--rail-w: {rail_px}px")
    with frame:
        with ui.element("div").classes("min-h-0 console-section-rail"):
            for entry in entries:
                key, label = entry[0], entry[1]
                hint = entry[2] if len(entry) > 2 else ""
                mark = entry[3] if len(entry) > 3 else None
                if key is GROUP:
                    _rail_group(t(label), mark)
                    continue
                _rail_row(str(key), t(label), str(key) == current, on_pick, t(hint), mark)
        work = ui.element("div").classes("min-w-0 console-section-work")
    return work


def _rail_group(label: str, mark: Callable[[], None] | None = None) -> None:
    """A heading over the run of rows that follows it, with a corner for a mark.

    The mark is drawn over the heading rather than beside it, so a group reads at the
    same place on the line whether or not something under it wants attention.
    """
    if mark is None:
        ui.label(label).classes("console-group console-rail-group")
        return
    with ui.element("div").classes("console-group console-rail-group"):
        ui.label(label)
        mark()


def _rail_row(key: str, label: str, open_now: bool,
              on_pick: Callable[[str], Any], hint: str = "",
              mark: Callable[[], None] | None = None) -> None:
    """One destination's name, which is both the rail entry and the accordion header.

    The chevron says the row opens, which is a fact about the control rather than a
    label for the destination. Without it the stacked rows are words with no sign that
    any of them do anything.

    `mark` draws in the row's own corner, over the name rather than beside it: a state
    about the destination must not move the word that names it, and the gutter it sits
    in is reserved on every row whether one is drawn or not.
    """
    row = ui.row().classes("items-stretch gap-0 no-wrap console-section-row")
    if open_now:
        row.classes(add="console-section-on")
    if hint:
        row.tooltip(hint)
    with row:
        # `no-wrap`, or a long name is two lines and one taller row. The label ellipses
        # instead, which is what `truncate` was already there to do.
        with ui.row().classes("items-center grow min-w-0 no-wrap console-section-hit"):
            ui.label(label).classes("truncate")
            if mark is not None:
                mark()
        with ui.row().classes("items-center console-section-caret"):
            ui.icon("expand_more", size="18px")
    # The whole band, name and chevron alike - a header that opens on the word but only
    # closes on the arrow is a control with two rules to learn.
    row.on("click", lambda: on_pick(key))


def switch(value: bool | None, on_change: Callable[[Any], Any], *,
           disabled: bool = False, hint: str = "") -> Callable[[], None]:
    """Every binary value the user can set, drawn the same way. None draws it neither
    on nor off, and a click from there turns it on."""
    def draw() -> None:
        # Green, the same token a present chip takes: on means the same thing whether
        # the panel found it or the user set it, and the shape already says which.
        control = ui.switch(value=value, on_change=on_change) \
            .props("dense color=positive").classes("console-fact-switch")
        if disabled:
            control.disable()
        if hint:
            control.tooltip(hint)

    return draw


def state(text: str, level: str, *, beside: str = "",
          hint: str = "") -> Callable[[], None]:
    """A state the panel found and the user cannot set, as a chip.

    The counterpart of the switch: a switch is a setting, a chip is a finding, and the
    shape is what says which. `level` is what the absence costs - `on`, `off`, `unknown`,
    `warn`, `bad`.
    """
    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            if beside:
                ui.label(beside).classes("console-fact-value truncate min-w-0") \
                    .tooltip(beside)
            chip = ui.label(text).classes(f"console-tier console-tier--{level}")
            if hint:
                chip.tooltip(hint)

    return draw


def field(value: str, on_save: Callable[[str], Any], *, lines: int = 0,
          placeholder: str = "", disabled: bool = False,
          status: Callable[[Any], Any] | None = None,
          refuses: bool = False, left_empty: str = "",
          browse: Callable[[str], Any] | None = None) -> Callable[[], None]:
    """Free text the user can set.

    Written when you leave it or when you press Enter, and `debounce=0` is what makes
    that safe: nicegui's model is only current if every keystroke reaches it, and reading
    it without that gets whatever the last sync happened to hold. Several lines settle as
    you stop typing instead, because a paragraph has no natural moment of leaving - and
    Enter belongs to the text there rather than to finishing it.

    Enter blurs rather than saving on the spot, so there is one write path and not two
    that can both fire on the way out. Leaving is what saves; Enter is a way of leaving.

    `status` draws inside the control's own append slot rather than after it, which is
    where Quasar puts an input's state and where a reader already looks for one - a mark
    in the next grid column would read as a fact about the row, not about the value.

    With `refuses`, a one-line field's `on_save` answers why it refused the value, or
    empty when it saved, and the answer is the field's error.

    With `left_empty`, a one-line field's tooltip holds its value, else `left_empty`.

    `browse` draws beside `status` in the same slot. It takes the field's current value
    and answers the path chosen, or nothing where browsing was cancelled; a path it
    answers goes through `leave` exactly as typing and leaving does.
    """
    held = {"was": value or ""}

    async def leave(control: ui.input, text: str) -> None:
        if text == held["was"]:
            return
        said = on_save(text)
        if inspect.isawaitable(said):
            said = await said
        if not (refuses and said):
            held["was"] = text
        if refuses and not control.is_deleted:
            if said:
                control.props["error"] = True
                control.props["error-message"] = str(said)
            else:
                control.props(remove="error error-message")
            control.update()

    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            control: ui.textarea | ui.input
            if lines:
                control = ui.textarea(placeholder=placeholder)
                control.value = value
                control.props(f"dense borderless rows={lines} debounce=800") \
                    .classes("console-edit-field")
                control.on_value_change(lambda: on_save(control.value or ""))
            else:
                control = ui.input(placeholder=placeholder)
                control.value = value
                control.props("dense borderless debounce=0") \
                    .classes("console-edit-field")
                control.on("blur", lambda: leave(control, control.value or ""))
                control.on("keydown.enter", lambda: control.run_method("blur"))
                if left_empty:
                    with control:
                        ui.tooltip().bind_text_from(
                            control, "value", backward=lambda said: said or left_empty)
                if status is not None or browse is not None:
                    with control.add_slot("append"):
                        if status is not None:
                            status(control)
                        if browse is not None:
                            @on_page
                            async def _browsed() -> None:
                                chosen = await browse(control.value or "")
                                if not chosen:
                                    return
                                if not control.is_deleted:
                                    control.value = chosen
                                await leave(control, chosen)

                            ui.button(icon=verbs.BROWSE, on_click=_browsed) \
                                .props("flat round dense") \
                                .tooltip(t("console.folder_picker.browse"))
            if disabled:
                control.disable()

    return draw


class GridBar:
    """The bar above a grid: two rows, each with a left side and a right-aligned end."""

    def __init__(self) -> None:
        self.top = ui.row().classes("w-full items-center gap-2 no-wrap console-bar-row")
        self.bottom = ui.row().classes(
            "w-full items-center gap-2 no-wrap console-bar-row console-bar-foot")


def grid_bar() -> GridBar:
    """Drawn into the caller's own panel row, which keeps its surface and spacing."""
    return GridBar()


def bar_end() -> Any:
    """The right-aligned end of a bar row. It shrinks; the stylesheet says what gives."""
    return ui.row().classes("items-center gap-2 no-wrap min-w-0 console-bar-end")


def add_action(choices: Any, *, empty: bool, heading: str = "") -> Any:
    """The verb that fills a page, from one choice or several.

    Several collapse into one `+` with a menu rather than a row of identical glyphs:
    two of the same icon side by side say there are two of something without saying
    which is which.

    An icon once there are rows and the full words while there are none: the bar is
    scarce width on a page you already know, and a glyph is a guess on one you do not.
    """
    items = list(choices.items()) if isinstance(choices, dict) else list(choices)
    if len(items) == 1:
        label, act = items[0]
        if empty:
            return ui.button(label, icon="add", on_click=act) \
                .props("flat dense no-caps size=sm").classes("shrink-0 console-action")
        return ui.button(icon="add", on_click=act) \
            .props("flat dense round size=sm").classes("shrink-0 console-action") \
            .tooltip(label)

    button = ui.button(icon="add").props("flat dense round size=sm") \
        .classes("shrink-0 console-action")
    with button, ui.menu():
        if heading:
            ui.item_label(heading).props("header").classes("console-menu-header")
        for label, act in items:
            ui.menu_item(label, act).classes("console-menu-item")
    return button


def search(placeholder: str) -> Any:
    """The box above a grid that narrows what is in it.

    Not a fact row - it has no label column and it sets nothing - but it is a control,
    and six pages had written the same three props out by hand. Returned rather than
    drawn into a callable, because the caller wires the grid to it and needs the control
    itself.
    """
    return ui.input(placeholder=placeholder) \
        .props("dense outlined clearable clear-icon=close").classes("w-64")


def refresh(on_click: Callable[[], Any], hint: str) -> Any:
    """The round Refresh at the end of a grid's bar, after its count. Returned, so a
    caller whose read takes a while can disable it until the read is back."""
    return ui.button(icon=verbs.REFRESH, on_click=on_click) \
        .props("flat dense round size=sm").classes("shrink-0").tooltip(hint)


def icon_only(icon: str, on_click: Callable[[], Any], *, hint: str = "") -> Any:
    """A round button that is only its icon - Up in the folder picker. Returned, so a
    caller can `.disable()` it, the way Up does at a root."""
    control = ui.button(icon=icon, on_click=on_click).props("flat round dense")
    if hint:
        control.tooltip(hint)
    return control


def selection_actions(hint: str) -> tuple[Any, Any]:
    """A grid bar's `more_vert` for the selected rows, and the menu it opens. Hidden until
    the caller shows it, which is when some rows are selected."""
    control = ui.button(icon=verbs.MORE).props("flat round dense").tooltip(hint)
    with control:
        menu = ui.menu().props("no-parent-event")
    control.set_visibility(False)
    return control, menu


def trouble_mark(reason: str = "") -> Callable[[], None]:
    """The mark that says something under here is misconfigured.

    A glyph rather than the count the nav badge carries: a heading and a rail row are
    signposts, and what is actually wrong is on the page they lead to.
    """
    def draw() -> None:
        icon = ui.icon("error", size="14px").classes("console-trouble-mark")
        if reason:
            icon.tooltip(reason)

    return draw


# A state a value is in, as the mark and the color that say so. `unset` draws nothing:
# an optional setting left blank is a choice, and a mark on every empty field is a page
# full of marks that mean nothing.
# Blank where blank is not allowed. Its own state because `unset` deliberately draws
# nothing - an optional path left empty is a choice - and a feature's requirement left
# empty is the thing that broke it.
REQUIRED = "required"
# A program that is there and does not run.
UNUSABLE = "unusable"

_VALUE_STATES = {
    REQUIRED: ("cancel", "negative"),
    UNUSABLE: ("error", "warning"),
    "ok": ("check_circle", "positive"),
    "missing": ("cancel", "negative"),
    "wrong_kind": ("cancel", "negative"),
    "not_executable": ("error", "warning"),
}


def value_state(state: str, reason: str = "") -> Callable[[Any], None]:
    """The mark that says whether a value is good, for `field(status=...)`.

    A tick and a cross rather than a chip: this is about the text in the box beside it,
    and a chip in the append slot would be a second control where a mark is wanted.
    """
    def draw(_control: Any) -> None:
        pair = _VALUE_STATES.get(state)
        if pair is None:
            return
        icon, color = pair
        mark = ui.icon(icon, size="18px").classes(f"text-{color} console-value-state")
        if reason:
            mark.tooltip(reason)

    return draw


class DescribedSelect(ui.select):
    """A picker whose options each carry a line saying what they are for.

    `describes` maps an option's label to its line. The slot reads it as `opt.help`,
    and `console-menu-tip` is what keeps the tooltip visible while the menu is open.
    """

    SLOT = """
        <q-item v-bind="props.itemProps">
          <q-item-section>
            <q-item-label>{{ props.opt.label }}</q-item-label>
          </q-item-section>
          <q-tooltip v-if="props.opt.help" class="console-menu-tip"
                     anchor="center right" self="center left">
            {{ props.opt.help }}
          </q-tooltip>
        </q-item>
    """

    def __init__(self, options: Any, *, value: Any, label: str | None = None,
                 describes: dict[str, str] | None = None,
                 on_change: Callable[[Any], Any] | None = None) -> None:
        # Before `super().__init__`, which builds the payload for the first time.
        self.describes: dict[str, str] = dict(describes or {})
        super().__init__(options, value=value, label=label, on_change=on_change)
        self.add_slot("option", self.SLOT)

    def _update_options(self) -> None:
        super()._update_options()
        for option in self._props["options"]:
            option["help"] = self.describes.get(str(option.get("label") or ""), "")

    def describe_options(self, describes: dict[str, str]) -> None:
        """The lines, and the rebuild that puts them on the payload."""
        self.describes = dict(describes)
        self.update()


class CountedSelect(ui.select):
    """Several from a list, each option saying how many games hold it.

    `counts` maps a value to its count. The chips of what is chosen carry the value
    alone.
    """

    SLOT = """
        <q-item v-bind="props.itemProps">
          <q-item-section>
            <q-item-label>{{ props.opt.label }}</q-item-label>
          </q-item-section>
          <q-item-section side v-if="props.opt.count != null">
            <q-item-label caption>{{ props.opt.count }}</q-item-label>
          </q-item-section>
        </q-item>
    """

    def __init__(self, options: Sequence[str], counts: dict[str, int], *,
                 value: Sequence[str], typed: bool = False) -> None:
        # Before `super().__init__`, which builds the payload for the first time.
        self.counts = dict(counts)
        super().__init__(list(options), value=list(value), multiple=True,
                         with_input=typed)
        self.props("use-chips")
        self.add_slot("option", self.SLOT)

    def _update_options(self) -> None:
        super()._update_options()
        for option in self._props["options"]:
            option["count"] = self.counts.get(str(option.get("label") or ""))


class MarkedSelect(ui.select):
    """One from a list, each option with a word in its trailing slot where `marks` has
    one, and `heading` above the option `heading_at`, where the list changes kind."""

    SLOT = """
        <q-item-label v-if="props.opt.heading" header class="console-menu-header">
          {{ props.opt.heading }}</q-item-label>
        <q-item v-bind="props.itemProps">
          <q-item-section>
            <q-item-label>{{ props.opt.label }}</q-item-label>
          </q-item-section>
          <q-item-section side v-if="props.opt.mark">
            <q-item-label caption>{{ props.opt.mark }}</q-item-label>
          </q-item-section>
        </q-item>
    """

    def __init__(self, options: dict[str, str], *, value: str | None,
                 marks: dict[str, str] | None = None, heading: str = "",
                 heading_at: str | None = None) -> None:
        # Before `super().__init__`, which builds the payload for the first time.
        self.marks = dict(marks or {})
        self.heading = heading
        self.heading_at = heading_at
        super().__init__(options, value=value)
        self.add_slot("option", self.SLOT)

    def _update_options(self) -> None:
        super()._update_options()
        for option in self._props["options"]:
            chosen = self._values[option["value"]]
            option["mark"] = self.marks.get(chosen, "")
            option["heading"] = self.heading if chosen == self.heading_at else ""


class GamePicker(ui.select):
    """One game from the library, typed into, each option with its maker and year. A
    game in `held` is ticked and cannot be picked. `art` is each game's list art, or None
    while the lists draw none."""

    LINES = """
            <q-item-label>{{ props.opt.label }}</q-item-label>
            <q-item-label caption v-if="props.opt.made" class="console-cell-made">
              {{ props.opt.made }}</q-item-label>"""
    SLOT = f"""
        <q-item v-bind="props.itemProps">
          <q-item-section>
            {list_art.option_html(LINES, icons.GAMES)}
          </q-item-section>
          <q-item-section side class="console-pick-held">
            <q-icon v-if="props.opt.held" name="check" class="console-tick" />
          </q-item-section>
        </q-item>
    """

    def __init__(self, games: Sequence[dict[str, Any]], held: set[str], *,
                 label: str, art: dict[str, str] | None = None) -> None:
        # Before `super().__init__`, which builds the payload for the first time.
        self.made = {str(game["id"]): game_tables.made(game) for game in games}
        self.held = set(held)
        self.art = art
        super().__init__({str(game["id"]): str(game.get("name") or game["id"])
                          for game in games}, with_input=True, label=label)
        self.add_slot("option", self.SLOT)

    def _update_options(self) -> None:
        super()._update_options()
        for option in self._props["options"]:
            game = str(self._values[option["value"]])
            option["made"] = self.made.get(game, "")
            option["held"] = option["disable"] = game in self.held
            if self.art is not None:
                option[list_art.FIELD] = self.art.get(game, "")


class SettingPicker(ui.select):
    """One setting, typed into, each option with its area under it and a heading above
    the option in `headings` that starts a run. An option's `also` is its key, for
    `workbench._ADD_BOX`'s filter.

    A heading is an option of its own with an empty label, so anything typed filters it
    out: a heading left above a filtered list would claim a run that is no longer whole."""

    HEADING = "heading:"
    SLOT = """
        <q-item-label v-if="props.opt.heading" header class="console-menu-header">
          {{ props.opt.heading }}</q-item-label>
        <q-item v-else v-bind="props.itemProps">
          <q-item-section>
            <q-item-label>{{ props.opt.label }}</q-item-label>
            <q-item-label caption v-if="props.opt.area" class="console-cell-made">
              {{ props.opt.area }}</q-item-label>
          </q-item-section>
        </q-item>
    """

    def __init__(self, options: dict[str, str], *, areas: dict[str, str],
                 headings: dict[str, str], label: str) -> None:
        # Before `super().__init__`, which builds the payload for the first time.
        self.areas = dict(areas)
        self.headings = {}
        listed: dict[str, str] = {}
        for key, text in options.items():
            if key in headings:
                listed[self.HEADING + key] = ""
                self.headings[self.HEADING + key] = headings[key]
            listed[key] = text
        super().__init__(listed, with_input=True, label=label)
        self.add_slot("option", self.SLOT)

    def _update_options(self) -> None:
        super()._update_options()
        for option in self._props["options"]:
            key = str(self._values[option["value"]])
            if key in self.headings:
                option.update(heading=self.headings[key], disable=True)
            else:
                option.update(area=self.areas.get(key, ""), also=key)


def hint(control: Any, said: str) -> None:
    """A line under a field. The field must carry `bottom-slots`."""
    if said:
        control.props(f'hint="{said}"')
    else:
        control.props(remove="hint")


def path_field(placeholder: str = "", *, wants: str, value: str = "",
               width: str = "w-96",
               on_checked: Callable[[str, str], str] | None = None,
               browse: Callable[[str], dict] | None = None,
               suffixes: tuple[str, ...] = ()) -> Any:
    """A path typed by hand, saying whether it is there. Returns the input.

    `wants` is what should be at the end of it - `dir`, `file` or `exe`, the words
    `path_checks` answers in. The mark draws in the control's append slot, beside the
    text it is about, and an empty box draws none.

    `on_checked` returns the line to show under the field - what the path turned out to
    be. It goes in the hint, the row the error message uses, so a field with something
    to say and one without are the same height.

    `browse` draws Browse beside the field, whatever `wants` is. `suffixes` narrows a
    `file` field's picker to those extensions; empty means every file.

    `debounce=0` stays on the input and the wait goes on a timer: a debounce here leaves
    the value stale at the moment a button is pressed.
    """
    from common import path_checks

    control = ui.input(placeholder=placeholder)
    control.value = value
    control.props("outlined dense debounce=0 bottom-slots").classes(width)
    with control.add_slot("append"):
        holder = ui.element("div").classes("console-value-state")
        if browse is not None:
            from console import folder_picker

            async def _browsed() -> None:
                chosen = await folder_picker.pick_path(
                    browse, control.value or "", kind=wants, suffixes=suffixes)
                if chosen:
                    control.value = chosen

            ui.button(icon=verbs.BROWSE, on_click=_browsed) \
                .props("flat round dense").tooltip(t("console.folder_picker.browse"))
    seen: dict[str, Any] = {"was": object()}

    async def look() -> None:
        said = str(control.value or "").strip()
        if said == seen["was"]:
            return
        seen["was"] = said
        state, why = await offload.io(path_checks.check, wants, said)
        holder.clear()
        with holder:
            value_state(state, why)(control)
        if on_checked is not None:
            hint(control, on_checked(state, said))

    # One timer comparing against what it last asked about, rather than one restarted
    # per keystroke: a cancelled one-shot leaves an element behind and the restarts stop
    # arriving, which shows up as a mark that answers the first path and no other.
    ui.timer(0.3, look)
    return control


def select(options: Any, value: str, on_change: Callable[[Any], Any], *,
           disabled: bool = False,
           describes: dict[str, str] | None = None,
           status: Callable[[Any], Any] | None = None) -> Callable[[], None]:
    """A list to pick from, where the reader already knows what the names mean, or
    `describes` says, by label, on each option.

    Where the label of each option is itself the thing being decided, the set goes on
    screen whole as radios instead - a closed control makes the reader open it to
    compare.
    """
    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            control = (DescribedSelect(options, value=value, describes=describes,
                                       on_change=on_change)
                       if describes else
                       ui.select(options, value=value, on_change=on_change)) \
                .props("dense borderless options-dense") \
                .classes("console-edit-field console-edit-select")
            if status is not None:
                with control.add_slot("append"):
                    status(control)
            if disabled:
                control.disable()

    return draw


def multi_select(options: Any, value: Sequence[str], on_change: Callable[[Any], Any], *,
                 disabled: bool = False) -> Callable[[], None]:
    """Several from a list, where the row is a choice rather than a fact.

    Closed rather than a column of checkboxes: the set here is as long as whatever it is
    over - the systems in somebody's old library - and a control that grows down the
    dialog would push what it is for off the screen. Everything selected shows, so what
    is chosen is still readable without opening it.
    """
    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            control = ui.select(options, value=list(value or []), multiple=True,
                                on_change=on_change) \
                .props("dense borderless options-dense use-chips") \
                .classes("console-edit-field console-edit-select")
            if disabled:
                control.disable()

    return draw


def combo(value: str, options: Any, on_change: Callable[[Any], Any], *,
          disabled: bool = False, status: Callable[[Any], Any] | None = None,
          placeholder: str = "", clearable: bool = True) -> Callable[[], None]:
    """A list to pick from that can also be typed into. Not `clearable` where the row
    has a Clear of its own.

    For a value something else can offer good answers to and still be wrong about - which
    installs are on the network, say. A closed select would leave a filtered network with
    no way to name a machine by hand; a plain field would make the ordinary case a typing
    exercise with a URL in it.
    """
    def draw() -> None:
        offered = dict(options or {})
        # What is stored is always one of the choices, even when nothing is offering it
        # now: a machine that is switched off has to still read as the choice that was
        # made, and a value outside the list is refused outright.
        if value and value not in offered:
            offered[value] = value
        with ui.element("div").classes("console-fact-edit"):
            control = ui.select(offered, value=value or None, on_change=on_change,
                                with_input=True, new_value_mode="add-unique")
            control.props("dense borderless options-dense input-debounce=0"
                          + (" clearable clear-icon=close" if clearable else ""))
            if placeholder:
                control.props(f'placeholder="{placeholder}"')
            control.classes("console-edit-field console-edit-select console-edit-combo")
            if status is not None:
                with control.add_slot("append"):
                    status(control)
            if disabled:
                control.disable()

    return draw


def swatch(color: str, on_pick: Callable[[str], Any], *,
           disabled: bool = False) -> Callable[[], None]:
    """A color the user can set, drawn as itself, `#RRGGBB` on hover."""
    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            button = ui.button().props("flat round dense").classes("console-swatch")
            with button:
                dot = ui.element("span").classes("console-tag-dot") \
                    .style(f"background: {color}")
                tip = ui.tooltip(color)

                async def pick(event: Any) -> None:
                    chosen = str(event.color or "").upper()
                    dot.style(f"background: {chosen}")
                    tip.text = chosen
                    said = on_pick(chosen)
                    if inspect.isawaitable(said):
                        await said

                if not disabled:
                    ui.color_picker(on_pick=pick).set_color(color)
            if disabled:
                button.disable()

    return draw


def named_as(value: Any, named: dict[str, str]) -> str:
    """Of `named`, the one `value` is as a number; "" for any other."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return next((one for one in named if float(one) == number), "")


def named_number(value: Any, named: dict[str, str], on_pick: Callable[[Any], Any], *,
                 disabled: bool = False, whole: bool = True,
                 low: Any = None, high: Any = None) -> Callable[[], None]:
    """A number some of whose values have names: the names and Custom to pick from, and
    the number itself beside Custom."""
    said = named_as(value, named)

    async def call(chosen: Any) -> None:
        answer = on_pick(chosen)
        if inspect.isawaitable(answer):
            await answer

    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            picker = ui.select({**named, "": t("word.custom")}, value=said) \
                .props("dense borderless options-dense") \
                .classes("console-edit-field console-edit-select")
            box = ui.number(value=None if said else value, format="%d" if whole else None,
                            min=low, max=high) \
                .props("dense borderless").classes("console-edit-field console-edit-narrow")
            box.set_visibility(not said)

            async def picked(event: Any) -> None:
                box.set_visibility(not event.value)
                if event.value:
                    await call(event.value)
                else:
                    box.run_method("focus")

            async def typed(event: Any) -> None:
                if event.value is not None:
                    await call(int(event.value) if whole else float(event.value))

            picker.on_value_change(picked)
            box.on_value_change(typed)
            if disabled:
                picker.disable()
                box.disable()

    return draw


def number(value: Any, on_change: Callable[[Any], Any], *,
           disabled: bool = False, whole: bool = True,
           low: Any = None, high: Any = None, step: Any = None,
           placeholder: str = "") -> Callable[[], None]:
    """A number. Narrow, because a four-digit box in a full-width field says the value
    might be long.

    `whole` because not every number is a count: a port is, and a theme's scale factor
    is not. Formatting a fraction as an integer does not round it on the way in - it
    shows a different value than the one that is stored.

    Bounds are the control's, not a check afterwards: a spinner that will not go past
    the limit says what the limit is without anybody being told off for passing it.
    """
    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            control = ui.number(value=value if value != "" else None,
                                placeholder=placeholder or None,
                                format="%d" if whole else None,
                                min=low, max=high, step=step,
                                on_change=on_change) \
                .props("dense borderless").classes("console-edit-field console-edit-narrow")
            if placeholder:
                control.style(f"--blank: {len(placeholder) + 1}ch")
            if disabled:
                control.disable()

    return draw


def action(label: str,
           # The event or nothing, which is NiceGUI's own Handler type: `js` emits a
           # result and this is what receives it.
           on_click: Callable[[Any], Any] | Callable[[], Any] | None = None, *,
           icon: str = "", inline: bool = False, danger: bool = False, hint: str = "",
           enabled: bool = True, js: str = "") -> Callable[[], None]:
    """A verb, which follows the value it acts on.

    Weight follows the target: an action on a field or a section takes `.console-action`;
    one sitting beside a state takes `.console-action--inline`, the same control at the
    chip's type scale.

    `js` is for the few acts a browser will only allow while it still believes a person
    just asked for them. The Console is server-rendered, so an ordinary click goes to the
    server and comes back - and by then the click's own permission has expired. A handler
    given here runs in the browser at the moment of the click and `emit(...)`s its result,
    which `on_click` then receives.
    """
    def draw() -> None:
        classes = "console-action console-action--inline" if inline else "console-action"
        control = ui.button(label, icon=icon or None,
                            on_click=None if js else on_click) \
            .props("flat dense no-caps size=sm").classes(classes)
        if danger:
            control.classes("console-action console-action--danger")
        if js:
            control.on("click", on_click, js_handler=js)
        if not enabled:
            control.disable()
        if hint:
            control.tooltip(hint)

    return draw


def remote_action(label: str, on_click: Callable[..., Any] | None = None, *, icon: str,
                  primary: bool = False, danger: bool = False, hint: str = "") -> ui.button:
    """A verb on the Remote, the width of its row. `primary` for the one a screen is for,
    `danger` for one that ends what the others are for."""
    control = ui.button(label, icon=icon, on_click=on_click)
    if primary:
        control = control.props("no-caps unelevated color=primary") \
            .classes("remote-action remote-action--primary")
    else:
        control = control.props("no-caps flat") \
            .classes("remote-action" + (" remote-action--danger" if danger else ""))
    if hint:
        control.tooltip(hint)
    return control


def icon_action(label: str, on_click: Callable[[], Any], *, icon: str, hint: str = "",
                enabled: bool = True) -> Callable[[], None]:
    """A verb drawn as its icon alone, for one repeated down a column of rows. `label` is
    its name to a screen reader, and `hint` what it says on hover."""
    def draw() -> None:
        control = ui.button(icon=icon, on_click=on_click).props("flat dense round size=sm")
        control.props["aria-label"] = label
        if not enabled:
            control.disable()
        if hint:
            control.tooltip(hint)

    return draw


def menu_entry(label: str, on_click: Callable[..., Any] | None = None, *,
               mark: Callable[[], Any] | None = None,
               trail: Callable[[], Any] | None = None,
               classes: str = "", auto_close: bool = True, refused: str = "") -> Any:
    """An entry in a menu whose items share the leading slot: `mark` draws into it, and an
    entry without one indents to it so the labels line up. `trail` draws the state at the
    end. `refused` dims it, with those words under it, and it does nothing."""
    if refused:
        on_click, auto_close = None, False
        classes = f"console-menu-blocked {classes}"
    item = ui.menu_item(on_click=on_click, auto_close=auto_close) \
        .classes(f"console-menu-item {classes}".strip())
    with item, ui.row().classes("items-center gap-2 no-wrap w-full"):
        if mark is None:
            ui.element("span").classes("console-menu-mark")
        else:
            mark()
        with ui.column().classes("gap-0 grow min-w-0"):
            ui.label(label)
            if refused:
                ui.label(refused).classes("console-menu-sub")
        if trail is not None:
            trail()
    return item


@dataclass(frozen=True)
class Verb:
    """One thing that can be done to a subject as a whole.

    Written once per subject and drawn in both places it is offered: the panel header's
    menu and the grid row's context menu. `run` absent is offered and refused, and
    `hint` says why. `choices` opens a second menu instead of acting. `to` makes it a
    link to that address instead, one outside the Console opening a new tab and marked
    as leaving. `in_panel` false keeps it to the grid, for a verb whose panel home is a
    field. `icon` is for where it is also drawn as a button; a menu item takes none.
    """
    label: str
    run: Callable[[], Any] | None = None
    danger: bool = False
    hint: str = ""
    choices: tuple[tuple[str, Callable[[], Any]], ...] = ()
    in_panel: bool = True
    icon: str = ""
    to: str = ""


def leaves(to: str) -> bool:
    """Whether an address is outside the Console, which is anything not a path here."""
    return not to.startswith("/")


def _verb_entry(verb: Verb) -> None:
    live = verb.run is not None or bool(verb.choices) or bool(verb.to)
    classes = "console-menu-item"
    if not live:
        classes += " console-menu-blocked"
    elif verb.danger:
        classes += " console-menu-danger"
    acts = live and not verb.choices and not verb.to
    item = ui.menu_item(on_click=verb.run if acts else None,
                        auto_close=live and not verb.choices).classes(classes)
    if verb.to:
        item.props["href"] = verb.to
        if leaves(verb.to):
            item.props["target"] = "_blank"
    with item, ui.row().classes("items-center gap-2 no-wrap w-full"):
        with ui.column().classes("gap-0 grow min-w-0"):
            ui.label(verb.label)
            if verb.hint and not live:
                ui.label(verb.hint).classes("console-menu-sub")
        if verb.choices:
            ui.icon(verbs.DRILL).classes("console-menu-trail")
        elif verb.to and leaves(verb.to):
            ui.icon(verbs.OPEN_OUT).classes("console-menu-trail")
    if verb.choices:
        with item, ui.menu().props('anchor="top end" self="top start"'):
            for label, run in verb.choices:
                ui.menu_item(label, run).classes("console-menu-item")


def verb_entries(entries: Sequence[Verb]) -> None:
    """Into the menu being built. The destructive ones last, under a rule."""
    safe = [one for one in entries if not one.danger]
    risky = [one for one in entries if one.danger]
    for one in safe:
        _verb_entry(one)
    if safe and risky:
        ui.separator()
    for one in risky:
        _verb_entry(one)


def verb_menu(menu: Any, name: str, entries: Sequence[Verb]) -> None:
    """A grid row's context menu: the row's name, then what can be done to it."""
    menu.clear()
    if not entries:
        return
    with menu:
        ui.item_label(name).props("header").classes("console-menu-header")
        ui.separator()
        verb_entries(entries)


def subject_menu(slot: Any, entries: Sequence[Verb]) -> None:
    """The panel header's menu, for the subject the panel is about."""
    slot.clear()
    shown = [one for one in entries if one.in_panel]
    if not shown:
        return
    with slot:
        button = ui.button(icon=verbs.MORE).props("flat dense round size=sm") \
            .tooltip(t("word.actions"))
        with button, ui.menu():
            verb_entries(shown)


def link(label: str, *, to: str, on_click: Callable[[], Any] | None = None,
         hint: str = "") -> Callable[[], None]:
    """A link to somewhere else in the Console.

    An anchor, never a click handler on a label. A destination has an address, so a row
    that only listens for a click hides that from the browser and kills "open in a new
    tab", middle-click and copy-link-address on it.

    With `on_click` the row also takes `console-link--inplace`, which is what the page's
    click handler looks for: it stops the browser following the href on a plain click and
    leaves every modified one alone, so the fast path works and the address still means
    something. Without one the browser simply follows the href.

    Carries no icon; `link_out` is the one that does.
    """
    def draw() -> None:
        row = ui.link(label, target=to).classes("console-link")
        if on_click is not None:
            row.classes("console-link--inplace")
            row.on("click", on_click)
        if hint:
            row.tooltip(hint)

    return draw


def menu_link(label: str, *, to: str) -> None:
    """A menu row that goes somewhere else in the Console: an item's look, not accent."""
    row = ui.menu_item(label).classes("console-menu-item")
    row.props["href"] = to


def tag_link(tag: str, color: str, *, to: str, mark: str = "",
             hint: str = "") -> Callable[[], None]:
    """A tag chip that goes somewhere: the chip's look, and an address like any link."""
    def draw() -> None:
        with ui.link(target=to).classes(tag_chips.chip_class(color)) as row:
            ui.element("span").classes(tag_chips.dot_class(color))
            ui.label(tag)
            if mark:
                ui.icon(mark)
        if hint:
            row.tooltip(hint)

    return draw


def link_out(label: str, *, to: str, hint: str = "") -> Callable[[], None]:
    """A link that leaves the Console, opening in a new tab and marked `open_in_new`.

    `label` is the thing being opened wherever the surface has one to give - a name
    already on the row reads better than a verb added beside it.
    """
    def draw() -> None:
        row = ui.link(target=to, new_tab=True).classes("console-link console-link-out")
        with row:
            ui.label(label)
            ui.icon("open_in_new")
        if hint:
            row.tooltip(hint)

    return draw


def out(*, to: str, hint: str) -> Callable[[], None]:
    """The way out to somewhere else, as its marker alone. `hint` is required."""
    def draw() -> None:
        row = ui.link(target=to, new_tab=True) \
            .classes("console-link console-link-out console-link-out--mark")
        with row:
            ui.icon(verbs.OPEN_OUT)
        row.tooltip(hint)

    return draw


def line(text: str, *, hint: str = "", classes: str = "console-help") -> ui.label:
    """A line of words, ending in a mark that opens `hint` when there is one."""
    shown = ui.label(text).classes(classes)
    if not hint:
        return shown
    shown.classes("console-detailed")
    with shown:
        mark = ui.icon(verbs.SAYS_MORE).props('tabindex=0 role=button aria-hidden=false')
        mark.props["aria-label"] = hint
        mark.on("click.stop", js_handler="() => {}")
        with mark, ui.menu().classes("console-detailed"):
            ui.label(hint)
    ui.tooltip(hint).classes("console-detailed").props["target"] = f"#{shown.html_id}"
    return shown


def note(text: str, hint: str = "") -> tuple[Any, Callable[[], None]]:
    """The sentence under a control that says what it does, and `hint` behind its mark.

    Written out rather than left to a tooltip, and only where the label cannot carry
    the meaning on its own: a config key's name says what it is called, not what
    turning it off costs. Help you have to already suspect you need is not help.
    """
    def draw() -> None:
        line(text, hint=hint)

    return (ASIDE, draw)


def disclosure(label: str) -> Any:
    """A label that opens onto more of what is already here. Used as a context."""
    built = ui.expansion(label).props("dense dense-toggle").classes("console-disclosure")
    built.props["toggle-aria-label"] = label
    return built


def lede(text: str) -> tuple[Any, Callable[[], None]]:
    """The line under a heading that says what the group is for."""
    def draw() -> None:
        ui.label(text).classes("console-help")

    return (LEDE, draw)


def intro(text: str, hint: str = "") -> tuple[Any, Callable[[], None]]:
    """What a whole page cannot say row by row, said once above the rows.

    The width of the panel, because it is not about any one control - which is the
    difference between this and `note`.
    """
    def draw() -> None:
        line(text, hint=hint)

    return (FULL, draw)
