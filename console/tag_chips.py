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

from common.games.tag_registry import COLORS

BOX = "console-tags"
CHIP = "console-tag"
DOT = "console-tag-dot"
# Where the grid's drawing finds each tag's color and description.
LOOKS = "__vpinfeTagLooks"


def dot_class(color: str) -> str:
    return f"{DOT} {DOT}--{color if color in COLORS else 'gray'}"


def draw(tags: Sequence[str], looks: Mapping[str, Mapping[str, Any]]) -> None:
    with ui.element("span").classes(BOX):
        for tag in tags:
            look = looks.get(tag) or {}
            with ui.element("span").classes(CHIP) as chip:
                ui.element("span").classes(dot_class(str(look.get("color") or "")))
                ui.label(tag)
            if look.get("description"):
                chip.tooltip(str(look["description"]))


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
