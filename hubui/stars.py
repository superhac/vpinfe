"""Five stars, one control, wherever a rating is set.

Drawn twice and it cannot be drawn once: a grid cell is rendered by AG Grid in the
browser, a panel row is built from elements on the server. So both live here, answering
to the same constants, and `tests/hubui` asserts they still agree on what they draw.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import run, ui

MOST = 5
# The character *is* the control. In a tooltip it measures zero and cannot be clicked,
# and a scripted click passes on it anyway - `docs/conventions.md` has why.
CLEAR = "×"

BOX = "hub-stars"
STAR = "hub-star"
LIT = "hub-star--on"
CLEAR_CLASS = "hub-star-clear"

# One delegated listener, not a handler per cell: a renderer runs again on every scroll
# and NiceGUI strips inline handlers off raw HTML. Capture phase, because AG Grid's own
# handler sits between the cell and the document.
CLICK_JS = f"""
if (!window.__hubStars) {{
  window.__hubStars = true;
  document.addEventListener('click', (e) => {{
    const star = e.target.closest && e.target.closest('.{BOX} [data-value]');
    if (!star) return;
    e.stopPropagation();
    const box = star.closest('.{BOX}');
    emitEvent('hub_rate', {{game: box.dataset.game, table: box.dataset.table,
                           value: Number(star.dataset.value)}});
  }}, true);
}}
"""


def renderer(subject: str) -> str:
    """The grid's cell, as JavaScript. Only a rated row carries the clear, or an unrated
    library reads as a column of dismissals."""
    game = "row.id" if subject == "game" else "(row.game_id || '')"
    table = "''" if subject == "game" else "row.id"
    return (
        "params => {"
        " const row = params.data || {}; const held = Number(params.value) || 0;"
        f" let out = '<span class=\"{BOX}\" data-game=\"' + " + game
        + " + '\" data-table=\"' + " + table + " + '\">';"
        f" for (let n = 1; n <= {MOST}; n++) {{"
        f"  out += '<span class=\"{STAR}' + (n <= held ? ' {LIT}' : '')"
        "  + '\" data-value=\"' + n + '\" title=\"' + n + ' of 5\"></span>';"
        " }"
        f" if (held) {{ out += '<span class=\"{CLEAR_CLASS}\" data-value=\"0\"'"
        f"  + ' title=\"Clear rating\">{CLEAR}</span>'; }}"
        " return out + '</span>'; }"
    )


def draw(value: int, on_pick: Callable[[int], Any]) -> Callable[[], None]:
    """The panel's, as elements. A star sets and the clear unsets - one control doing
    both made a click on the lit star mean either, depending on a number the reader was
    not looking at."""
    def build() -> None:
        with ui.element("div").classes(BOX):
            for n in range(1, MOST + 1):
                lit = f" {LIT}" if n <= value else ""
                ui.element("span").classes(f"{STAR}{lit}") \
                    .on("click", lambda _, n=n: on_pick(n)) \
                    .tooltip(f"{n} of 5")
            if value:
                ui.label(CLEAR).classes(CLEAR_CLASS) \
                    .on("click", lambda _: on_pick(0)) \
                    .tooltip("Clear rating")

    return build


def rating_handler(rows_by_id: dict[str, Any], grid_of: Callable[[], Any],
                   client_factory: Callable[[], Any]) -> Callable[[Any], Any]:
    """One handler for both grids: write it, then repaint only the row that changed - a
    whole-grid refresh costs the scroll position and the selection for one number.

    `grid_of` rather than the grid, because a caller wires this before the grid exists -
    which the two closures this replaces did by reading a name bound later.
    """
    async def rate(event: Any) -> None:
        args = event.args if isinstance(event.args, dict) else {}
        game_id = str(args.get("game") or "")
        table_id = str(args.get("table") or "")
        value = int(args.get("value") or 0)
        if not game_id:
            return
        client = client_factory()
        call = client.rate_table if table_id else client.rate
        wanted = (game_id, table_id, value) if table_id else (game_id, value)
        try:
            await run.io_bound(call, *wanted)
        except Exception as exc:
            ui.notify(f"Could not save that rating: {exc}", type="negative")
            return
        row = rows_by_id.get(table_id or game_id)
        if row is not None:
            row["rating"] = value
            grid_of().run_grid_method("applyTransaction", {"update": [row]})

    return rate
