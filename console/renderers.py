"""How a grid cell is drawn, by name.

A column names the drawing it uses and the others it allows; a view records which it is
using. The JavaScript behind every name is here and nowhere else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from nicegui import ui

from common.i18n import t
from console import media_ownership, tag_chips

# Ours, not AG Grid's: the drawings a column allows, its default first. Stripped by
# `grid.for_grid` before the definitions reach the grid.
CHOICES_KEY = "drawings"


@dataclass(frozen=True)
class Renderer:
    name: str
    # The catalog key of what a person calls this way of drawing.
    label: str
    # `params => html`.
    js: str
    # The row height the drawing needs, or 0 for whatever the grid already uses.
    row_px: int = 0


# What every column drawn by name renders through; `draw_as` chooses the drawing.
DISPATCH = (
    "params => {"
    " const scope = (params.context || {}).scope;"
    " const chosen = ((window.__vpinfeDrawAs || {})[scope] || {})[params.colDef.field];"
    " const draw = (window.__vpinfeDraw || {})[chosen || params.drawn];"
    " return draw ? draw(params) : (params.value == null ? '' : String(params.value)); }"
)

# Word -> how to draw it. The cell holds the word and the mark is drawn from it here;
# `console/data.py` has why.
_MARK_BY_WORD = {
    tier.noun: {"mark": tier.mark, "why": t(tier.why), "word": t(tier.noun)}
    for tier in (media_ownership.tier_for(key) for key in media_ownership.STATES)
}

MARK = Renderer("mark", "console.renderers.mark", (
    "params => {"
    " const m = " + json.dumps(_MARK_BY_WORD) + ";"
    " const t = m[params.value]; if (!t) return '';"
    " const tip = t.word + ' \u2014 ' + t.why;"
    " return '<span class=\"console-mark ' + t.mark + '\" title=\"' + tip"
    " + '\"></span>'; }"
))

# A kind with no picture - audio, a rule sheet - keeps its mark: the file is there
# either way, and a column that empties when you ask to see the art reads as one that
# lost its files.
PICTURE = Renderer("picture", "console.renderers.picture", (
    "params => {"
    " const kind = params.colDef.field.slice(6);"
    " const row = params.data || {}; const art = row['thumb_' + kind];"
    " if (!art) return window.__vpinfeDraw.mark(params);"
    " return '<span class=\"console-cell-art\">' + art"
    " + '<i class=\"material-icons console-cell-zoom\" title=\"' + "
    + json.dumps(t("word.enlarge")) + " + '\" data-game=\"'"
    " + row.id + '\" data-kind=\"' + kind + '\">open_in_full</i></span>'; }"
), row_px=74)

_ESCAPE = ("const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')"
           ".replace(/\"/g, '&quot;');")

# A picture that is the row's subject rather than one of its facts.
PREVIEW = Renderer("preview", "console.renderers.preview", (
    "params => {" + _ESCAPE +
    " return params.value ? '<img class=\"console-cell-preview\" loading=\"lazy\" src=\"'"
    " + esc(params.value) + '\">'"
    " : '<i class=\"material-icons console-cell-noart\">image_not_supported</i>'; }"
), row_px=96)

# A state as a chip where it is worth noticing and as a quiet word where it is not.
# `params.states` maps each value to its label and, for the ones worth noticing, a tier.
STATE = Renderer("state", "console.renderers.state", (
    "params => {" + _ESCAPE +
    " const one = (params.states || {})[params.value]; if (!one) return '';"
    " return one.tier ? '<span class=\"console-member-chip console-tier console-tier--'"
    " + one.tier + '\">' + esc(one.label) + '</span>'"
    " : '<span class=\"console-cell-quiet\">' + esc(one.label) + '</span>'; }"
))

TAGS = Renderer("tags", "console.renderers.tags", tag_chips.RENDERER)

REGISTRY: dict[str, Renderer] = {one.name: one
                                 for one in (MARK, PICTURE, PREVIEW, STATE, TAGS)}


def install() -> None:
    """Every drawing, where the dispatcher can find it. Harmless to repeat."""
    body = ", ".join(f"{json.dumps(name)}: {one.js}" for name, one in REGISTRY.items())
    ui.run_javascript(
        f"window.__vpinfeDraw = Object.assign(window.__vpinfeDraw || {{}}, {{{body}}});")


def drawable(default: str, *others: str, **params: Any) -> dict[str, Any]:
    """What makes a column drawn by name: `default` until a view says otherwise, and
    `others` as the choices it offers. `params` reach the drawing as it runs."""
    return {":cellRenderer": DISPATCH, "cellRendererParams": {**params, "drawn": default},
            CHOICES_KEY: (default, *others)}


def choices(definition: dict[str, Any]) -> tuple[str, ...]:
    return tuple(definition.get(CHOICES_KEY) or ())


def draw_as(scope: str, drawing: dict[str, str]) -> None:
    """Say how this grid's columns are drawn now. The grid redraws itself separately."""
    ui.run_javascript(
        "(window.__vpinfeDrawAs = window.__vpinfeDrawAs || {})"
        f"[{json.dumps(scope)}] = {json.dumps(drawing)};")


def row_px(drawing: dict[str, str], shown: list[str], base: int) -> int:
    """The row height the drawings on screen need, never less than the grid's own."""
    return max([base, *(REGISTRY[name].row_px for field, name in drawing.items()
                        if field in shown and name in REGISTRY)])
