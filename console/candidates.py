"""One row for one thing you could pick, wherever the Console offers a choice of things.

A file to put in a media slot, a catalog entry to match a game against - the question
is the same in both, and it is not one a name answers. So the row leads with the
picture, and keeps its frame when there is no picture to put in it: a list where only
some rows carry art steps in and out as it scrolls.
"""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

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
        family: str = "image", glyph: str = "", action: str = "Use") -> None:
    """What it looks like, what it is, and the one thing you can do with it."""
    with ui.row().classes("items-center gap-3 w-full no-wrap console-source-row"):
        _body(src, name, meta, tag, family, glyph)
        ui.button(action, on_click=take).props("flat dense no-caps size=sm") \
            .classes("console-action shrink-0")


def choice(src: str, name: str, meta: str, pick: Callable, *,
           family: str = "image", glyph: str = "") -> None:
    """A row whose target is the whole row, with no button on it.

    For the lists you scan rather than compare: forty candidates with forty buttons is
    forty times the same word. `row` is the one to use where the act wants naming.

    The picture is small here, because these lists are the long ones and recognising a
    thing is a smaller question than judging it.
    """
    element = ui.row().classes("items-center gap-3 w-full no-wrap console-source-row "
                               "console-source-row--pick")
    with element:
        _body(src, name, meta, "", family, glyph, small=True)
    element.on("click", lambda: pick())
