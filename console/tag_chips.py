"""A tag as a chip, drawn the same way in a grid cell and on a panel.

Drawn twice and it cannot be drawn once: AG Grid renders a cell in the browser and a panel
is built on the server. Both answer to the constants here, and `tests/console` asserts
they still agree.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from nicegui import ui

from common.games.tag_registry import COLORS, derived_color

BOX = "console-tags"
CHIP = "console-tag"
DOT = "console-tag-dot"
# Where the grid's drawing finds each tag's color and description.
LOOKS = "__vpinfeTagLooks"


def dot_class(color: str) -> str:
    return f"{DOT} {DOT}--{color if color in COLORS else 'gray'}"


def color_of(tag: str, looks: Mapping[str, Mapping[str, Any]]) -> str:
    return str((looks.get(tag) or {}).get("color") or "") or derived_color(tag)


def draw(tags: Sequence[str], looks: Mapping[str, Mapping[str, Any]]) -> None:
    with ui.element("span").classes(BOX):
        for tag in tags:
            look = looks.get(tag) or {}
            with ui.element("span").classes(CHIP) as chip:
                ui.element("span").classes(dot_class(color_of(tag, looks)))
                ui.label(tag)
            if look.get("description"):
                chip.tooltip(str(look["description"]))


class Picker(ui.select):
    """Tags to choose from, each drawn as its chip.

    `adds` lets a tag be typed in that nothing carries yet. `props.opt` is a bare string
    for the moment between typing one and the server's answer, so the slots read both.

    NiceGUI remounts a template slot whenever the select renders, and a press that
    focuses the field makes it render: without `mousedown.prevent` the chip under the
    pointer is replaced before the button comes up, and its remove never fires.
    """

    SELECTED = f"""
        <q-chip dense removable :tabindex="props.tabindex" class="{CHIP}"
                @mousedown.prevent @remove="props.removeAtIndex(props.index)">
          <span :class="props.opt.dot || '{DOT} {DOT}--gray'"></span>
          {{{{ typeof props.opt === 'string' ? props.opt : props.opt.label }}}}
          <q-tooltip v-if="props.opt.help">{{{{ props.opt.help }}}}</q-tooltip>
        </q-chip>
    """
    OPTION = """
        <q-item v-bind="props.itemProps">
          <q-item-section side><span :class="props.opt.dot"></span></q-item-section>
          <q-item-section>
            <q-item-label>{{ props.opt.label }}</q-item-label>
          </q-item-section>
          <q-tooltip v-if="props.opt.help" class="console-menu-tip"
                     anchor="center right" self="center left">
            {{ props.opt.help }}
          </q-tooltip>
        </q-item>
    """

    def __init__(self, options: Sequence[str], *, value: Sequence[str],
                 looks: Mapping[str, Mapping[str, Any]], adds: bool = False) -> None:
        # Before `super().__init__`, which builds the payload for the first time.
        self.looks = dict(looks)
        super().__init__(list(options), multiple=True, value=list(value),
                         with_input=True, new_value_mode="add-unique" if adds else None)
        self.add_slot("selected-item", self.SELECTED)
        self.add_slot("option", self.OPTION)

    def _dressed(self, option: dict[str, Any]) -> dict[str, Any]:
        tag = str(option.get("label") or "")
        return {**option, "dot": dot_class(color_of(tag, self.looks)),
                "help": str((self.looks.get(tag) or {}).get("description") or "")}

    def _update_options(self) -> None:
        super()._update_options()
        self._props["options"] = [self._dressed(one) for one in self._props["options"]]

    def _value_to_model_value(self, value: Any) -> Any:
        return [self._dressed(one) for one in super()._value_to_model_value(value) or []]


def install(looks: Mapping[str, Mapping[str, Any]]) -> None:
    held = {name: {"color": str(one.get("color") or ""),
                   "description": str(one.get("description") or "")}
            for name, one in looks.items()}
    ui.run_javascript(f"window.{LOOKS} = {json.dumps(held)};")


RENDERER = (
    "params => {"
    " const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')"
    ".replace(/\"/g, '&quot;');"
    f" const looks = window.{LOOKS} || {{}};"
    f" const colors = {json.dumps(list(COLORS))};"
    " const held = (params.data || {}).tag_list || [];"
    f" return '<span class=\"{BOX}\">' + held.map(tag => {{"
    "  const look = looks[tag] || {};"
    "  const color = colors.includes(look.color) ? look.color : 'gray';"
    "  const tip = look.description ? ' title=\"' + esc(look.description) + '\"' : '';"
    f"  return '<span class=\"{CHIP}\"' + tip + '><span class=\"{DOT} {DOT}--' + color"
    "   + '\"></span>' + esc(tag) + '</span>'; }).join('') + '</span>'; }"
)
