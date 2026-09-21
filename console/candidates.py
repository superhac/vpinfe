"""One row for one thing you could pick, wherever the Console offers a choice of things.

A file to put in a media slot, a catalog entry to match a game against - the question
is the same in both, and it is not one a name answers. So the row leads with the
picture, and keeps its frame when there is no picture to put in it: a list where only
some rows carry art steps in and out as it scrolls.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from common.i18n import t
from console import verbs

# A family with no frame of its own still gets a mark, so the slot is never empty.
GLYPHS = {"audio": "graphic_eq"}
FALLBACK = "description"
SHOWABLE = ("image", "video")


def _peek(src: str, family: str) -> None:
    """A bigger look, without leaving the dialog the row is in.

    Off to the side rather than over the row, so the list it belongs to stays readable
    behind it. In a tooltip because the lists around it scroll, and anything drawn
    inside a scrolling box is clipped by it.
    """
    with ui.tooltip().classes("console-thumb-peek") \
            .props('anchor="center left" self="center right"'):
        if family == "video":
            ui.html(f'<video src="{src}#t=0.1" preload="metadata" muted '
                    f'playsinline></video>')
        else:
            ui.html(f'<img src="{src}">')


def _body(src: str, name: str, meta: str, tag: str, family: str, glyph: str,
          small: bool = False) -> None:
    """The picture and the words, which both shapes draw the same way."""
    frame = "console-source-thumb" + (" console-source-thumb--small" if small else "")
    with ui.element("div").classes(frame):
        if src and family == "video":
            ui.html(f'<video src="{src}#t=0.1" preload="metadata" muted '
                    f'playsinline></video>')
        elif src and family == "image":
            ui.html(f'<img src="{src}" loading="lazy">')
        else:
            ui.icon(glyph or GLYPHS.get(family, FALLBACK)) \
                .classes("console-source-thumb-glyph")
        if src and family in SHOWABLE:
            _peek(src, family)
    with ui.column().classes("gap-0 min-w-0 grow"):
        ui.label(name).classes("console-source-name")
        if meta:
            ui.label(meta).classes("console-help")
        if tag:
            ui.label(tag).classes("console-source-tag")


def row(src: str, name: str, meta: str, tag: str, take: Callable, *,
        family: str = "image", glyph: str = "", action: str = t("console.candidates.use")) -> None:
    """What it looks like, what it is, and the one thing you can do with it."""
    with ui.row().classes("items-center gap-3 w-full no-wrap console-source-row"):
        _body(src, name, meta, tag, family, glyph)
        ui.button(action, icon=verbs.ACCEPT, on_click=take) \
            .props("flat dense no-caps size=sm") \
            .classes("console-action shrink-0")


def choice(src: str, name: str, meta: str, pick: Callable | None = None, *,
           family: str = "image", glyph: str = "", chosen: bool = False,
           trailing: Callable[[], None] | None = None, entry: bool = False) -> Any:
    """A row whose target is the whole row, with no button on it.

    For the lists you scan rather than compare: forty candidates with forty buttons is
    forty times the same word. `row` is the one to use where the act wants naming.

    The picture is small here, because these lists are the long ones and recognizing a
    thing is a smaller question than judging it.

    `pick` absent draws the row without making it a target, for showing one on its own.
    `chosen` lights it. `trailing` puts one control at the end, for an act about that
    row rather than about the list. `entry` takes the grid's two-line type, for a row
    naming the same kind of thing a grid row names.
    """
    classes = "items-center gap-3 w-full no-wrap console-source-row"
    if pick is not None:
        classes += " console-source-row--pick"
    if chosen:
        classes += " console-source-row--chosen"
    if entry:
        classes += " console-source-row--entry"
    element = ui.row().classes(classes)
    with element:
        _body(src, name, meta, "", family, glyph, small=True)
        if trailing is not None:
            trailing()
    if pick is not None:
        element.on("click", lambda: pick())
    return element
