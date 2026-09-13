"""Picking the Console's appearance by looking at it.

A select would put four words on screen, and the words are the weakest part of this
decision - "Synthwave" means nothing until you have seen it, and Dark and Light are
two words for something the eye settles in about a tenth of a second. So each mode
draws itself: a miniature of this surface in that mode's own colors.

The values are expanded rather than referenced. Every swatch is painted on a page that
is already in one of these modes, so a `var()` left in place would resolve against the
palette in use and all four would come out the same.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from common.i18n import t
from console import theme

# The name each mode goes by on screen. Its order is the order on the page: the two
# neutral ones together, the deliberate one first because it is the default, and the
# one that defers last.
NAMES = {
    "synthwave": "console.settings.theme_synthwave",
    "dark": "console.settings.theme_dark",
    "light": "console.settings.theme_light",
    theme.SYSTEM: "console.settings.theme_system",
}


def _miniature(mode: str, half: str = "") -> None:
    """One palette, drawn as the surface it paints: a rail, and the work beside it.

    Which two regions is not arbitrary - the rail against the work area is the contrast
    the last round of palette work was all about, so it is the thing worth previewing.
    """
    ground = theme.token("--surface-0", mode)
    with ui.element("div").classes(f"console-swatch-part {half}") \
            .style(f"background:{ground}"):
        ui.element("div").classes("console-swatch-rail") \
            .style(f"background:{theme.token('--nav-bg', mode)}")
        with ui.element("div").classes("console-swatch-work") \
                .style(f"background:{theme.token('--surface-work', mode)};"
                       f"border-color:{theme.token('--line', mode)}"):
            ui.element("div").classes("console-swatch-flair") \
                .style(f"background:{theme.token('--flair', mode)}")
            for width in ("70%", "45%"):
                ui.element("div").classes("console-swatch-line") \
                    .style(f"background:{theme.token('--ink', mode)};width:{width}")


def _swatch(mode: str) -> None:
    """The preview for one choice. `system` is the only one that is two."""
    with ui.element("div").classes("console-swatch"):
        if mode == theme.SYSTEM:
            # Both of them, because that is what it is: the picture cannot show one
            # answer when the answer is the computer's to give.
            for side, palette in zip(("console-swatch-part--left",
                                      "console-swatch-part--right"),
                                     theme.SYSTEM_PALETTES.values(), strict=True):
                _miniature(palette, side)
        else:
            _miniature(mode)


def tiles(option: dict[str, Any], value: Any, save: Callable[[Any], Any], *,
          section: dict[str, Any] | None = None,
          writable: bool = True,
          rerender: Callable[[], None] | None = None) -> Callable[[], None]:
    """The four modes, side by side, the one in use marked on its edge.

    The page reloads on a change rather than repainting in place: the palette is one
    block of custom properties injected when the page is built, and every surface below
    reads it from there. Swapping it under a live page is a second delivery path for the
    same values, and this is one click on a settings page.
    """
    chosen = theme.mode_or_default(str(value or ""))

    def draw() -> None:
        with ui.element("div").classes("console-swatches"):
            for mode in theme.MODES:
                classes = "console-swatch-tile"
                if mode == chosen:
                    classes += " console-swatch-tile--active"
                async def pick(mode: str = mode) -> None:
                    if mode != chosen and await save(mode):
                        ui.navigate.reload()

                tile = ui.element("button").classes(classes) \
                    .props(f'type="button" aria-pressed="{str(mode == chosen).lower()}"')
                if writable:
                    tile.on("click", pick)
                else:
                    tile.props("disabled")
                with tile:
                    _swatch(mode)
                    ui.label(t(NAMES[mode])).classes("console-swatch-name")
        if chosen == theme.SYSTEM:
            # The only one of the four whose behavior is not in its picture.
            ui.label(t("console.settings.theme_follows_system")).classes("console-help")

    return draw
