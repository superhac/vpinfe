"""The panel: a rail of named destinations, one open, and the facts beside it.

The side pane draws it about a game; Settings draws it about the install. Both render
through here, so a treatment is changed in one place rather than in each surface that
happens to show the same kind of value.

Every control constructor returns the callable `facts` takes as a value, so it drops
into an entry list as the second half of a pair.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from nicegui import ui

# Rows that are not a fact. A group's title and an action strip span both columns, so
# every group keeps the one shared label width.
HEADING = object()
FULL = object()
# The value column alone, for a line that belongs to the control above it rather than
# to the row. Across both columns it starts at the label's edge and reads as a caption
# for the label instead.
ASIDE = object()

# A rail row that names the rows under it rather than opening anything.
GROUP = object()

# The rail's width. A lever rather than a literal: the pane is narrow and Settings is
# not, and both rails are the same control.
RAIL_PX = 152


def header(name: str) -> None:
    """What the content under it is about, where the rail row is too far away to say it."""
    ui.label(name).classes("text-base console-workbench-title console-panel-heading")


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


def _draw_value(target: Any, value: Any) -> None:
    if callable(value):
        value()
        return
    target.label(str(value)).classes("console-fact-value truncate min-w-0") \
        .tooltip(str(value))


def sections(entries: Sequence[tuple[Any, ...]], current: str,
             on_pick: Callable[[str], Any], *, rail_px: int = RAIL_PX) -> Any:
    """The rail and the region it opens into, returning the region.

    `entries` are `(key, label)` with an optional third element for a hint and a fourth
    for a mark drawn before the name, or `(GROUP, name)` for a heading over the rows
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
                    ui.label(label).classes("console-group console-rail-group")
                    continue
                _rail_row(str(key), label, str(key) == current, on_pick, hint, mark)
        work = ui.element("div").classes("min-w-0 console-section-work")
    return work


def _rail_row(key: str, label: str, open_now: bool,
              on_pick: Callable[[str], Any], hint: str = "",
              mark: Callable[[], None] | None = None) -> None:
    """One destination's name, which is both the rail entry and the accordion header.

    The chevron says the row opens, which is a fact about the control rather than a
    label for the destination. Without it the stacked rows are words with no sign that
    any of them do anything.

    `mark` draws before the name, where a state about the destination itself goes - a
    device answering is a fact about that device and not about the row being open.
    """
    row = ui.row().classes("items-stretch gap-0 no-wrap console-section-row")
    if open_now:
        row.classes(add="console-section-on")
    if hint:
        row.tooltip(hint)
    with row:
        # `no-wrap`, or a mark plus a long name is two lines and one taller row. The
        # label ellipses instead, which is what `truncate` was already there to do.
        with ui.row().classes("items-center grow min-w-0 no-wrap console-section-hit"):
            if mark is not None:
                mark()
            ui.label(label).classes("console-section-text truncate")
        with ui.row().classes("items-center console-section-caret"):
            ui.icon("expand_more", size="18px")
    # The whole band, name and chevron alike - a header that opens on the word but only
    # closes on the arrow is a control with two rules to learn.
    row.on("click", lambda: on_pick(key))


def switch(value: bool, on_change: Callable[[Any], Any], *,
           disabled: bool = False, hint: str = "") -> Callable[[], None]:
    """Every binary value the user can set, drawn the same way."""
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


def state(text: str, level: str, *, beside: str = "") -> Callable[[], None]:
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
            ui.label(text).classes(f"console-tier console-tier--{level}")

    return draw


def field(value: str, on_save: Callable[[str], Any], *, lines: int = 0,
          placeholder: str = "", disabled: bool = False,
          status: Callable[[Any], Any] | None = None) -> Callable[[], None]:
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
    """
    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
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
                control.on("blur", lambda: on_save(control.value or ""))
                control.on("keydown.enter", lambda: control.run_method("blur"))
                if status is not None:
                    with control.add_slot("append"):
                        status(control)
            if disabled:
                control.disable()

    return draw


# A state a value is in, as the mark and the color that say so. `unset` draws nothing:
# an optional setting left blank is a choice, and a mark on every empty field is a page
# full of marks that mean nothing.
_VALUE_STATES = {
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
    def draw(_control) -> None:
        pair = _VALUE_STATES.get(state)
        if pair is None:
            return
        icon, color = pair
        mark = ui.icon(icon, size="18px").classes(f"text-{color} console-value-state")
        if reason:
            mark.tooltip(reason)

    return draw


def select(options: Any, value: str, on_change: Callable[[Any], Any], *,
           disabled: bool = False) -> Callable[[], None]:
    """A list to pick from, where the reader already knows what the names mean.

    Where the label of each option is itself the thing being decided, the set goes on
    screen whole as radios instead - a closed control makes the reader open it to
    compare.
    """
    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            control = ui.select(options, value=value, on_change=on_change) \
                .props("dense borderless options-dense") \
                .classes("console-edit-field console-edit-select")
            if disabled:
                control.disable()

    return draw


def number(value: Any, on_change: Callable[[Any], Any], *,
           disabled: bool = False) -> Callable[[], None]:
    """A whole number. Narrow, because a four-digit box in a full-width field says the
    value might be long."""
    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            control = ui.number(value=value if value != "" else None, format="%d",
                                on_change=on_change) \
                .props("dense borderless").classes("console-edit-field console-edit-narrow")
            if disabled:
                control.disable()

    return draw


def action(label: str, on_click: Callable[[], Any], *, icon: str = "",
           inline: bool = False, danger: bool = False, hint: str = "",
           enabled: bool = True) -> Callable[[], None]:
    """A verb, which follows the value it acts on.

    Weight follows the target: an action on a field or a section takes `.console-action`;
    one sitting beside a state takes `.console-action--inline`, the same control at the
    chip's type scale.
    """
    def draw() -> None:
        classes = "console-action--inline" if inline else "console-action"
        if danger:
            classes = f"console-action {classes} console-action--danger"
        control = ui.button(label, icon=icon or None, on_click=on_click) \
            .props("flat dense no-caps size=sm").classes(classes)
        if not enabled:
            control.disable()
        if hint:
            control.tooltip(hint)

    return draw


def note(text: str) -> tuple[Any, Callable[[], None]]:
    """The sentence under a control that says what it does.

    Written out rather than left to a tooltip, and only where the label cannot carry
    the meaning on its own: a config key's name says what it is called, not what
    turning it off costs. Help you have to already suspect you need is not help.
    """
    def draw() -> None:
        ui.label(text).classes("console-help")

    return (ASIDE, draw)


def intro(text: str) -> tuple[Any, Callable[[], None]]:
    """What a whole page cannot say row by row, said once above the rows.

    The width of the panel, because it is not about any one control - which is the
    difference between this and `note`.
    """
    def draw() -> None:
        ui.label(text).classes("console-help")

    return (FULL, draw)
