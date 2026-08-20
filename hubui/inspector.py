"""The panel that follows the selection."""

from __future__ import annotations

from typing import Any

from nicegui import run, ui

from hubui import mediamap
from hubui.data import Library


async def build(container: ui.column, title: ui.column, library: Library,
                game_id: str | None) -> None:
    """Fill the panel, and the name that lives up in the panel's header row."""
    container.clear()
    title.clear()
    with container:
        if game_id is None:
            with title:
                ui.label("Game Details") \
                    .classes("text-base hub-detail-title leading-tight truncate")
                ui.label("Select a game") \
                    .classes("text-xs hub-detail-label leading-none truncate")
            return
        game = next((entry for entry in library.games if entry["id"] == game_id), None)
        if game is not None:
            with title:
                ui.label(game.get("name") or "") \
                    .classes("text-base hub-detail-title leading-tight truncate")
                ui.label(f"{game.get('manufacturer') or '?'} {game.get('year') or ''}") \
                    .classes("text-xs hub-detail-label leading-none truncate")
        if game is None:
            with title:
                ui.label("Game Details") \
                    .classes("text-base hub-detail-title leading-tight truncate")
                ui.label("Not in this library") \
                    .classes("text-xs hub-detail-label leading-none truncate")
            return



        media = library.media.get(game_id, {})
        present, borrowed, total = mediamap.summary(media)
        # First, not last. This is the question people actually have about a game, and
        # the shape of the map answers it before any label is read.
        label = f"Media ({present}/{total}"
        label += f", {borrowed} borrowed)" if borrowed else ")"
        with ui.expansion(label, value=True).classes("w-full"):
            mediamap.build(media, game_id)

        with ui.expansion("Identity").classes("w-full"):
            _rows(ui, {
                "VPS id": game.get("vps_id") or "-",
                "ROM": game.get("rom") or "-",
                "Type": game.get("type") or "-",
                "Themes": ", ".join(game.get("themes") or []) or "-",
            })

        # Off the loop, always. This is an HTTP call to our own process: made on the
        # event loop it blocks the server from answering it, the request times out
        # after 15s, and the browser reports the socket as lost rather than slow.
        tables = await run.io_bound(library.tables_for, game_id)
        with ui.expansion(f"Tables ({len(tables)})").classes("w-full"):
            for table in tables:
                with ui.row().classes("items-center gap-2 w-full px-3"):
                    ui.label(table.get("filename") or "").classes("text-xs truncate")
                    ui.badge(table.get("app") or "?", color="secondary").props("outline")



def _rows(target: Any, values: dict[str, str]) -> None:
    for label, value in values.items():
        with target.row().classes("items-center gap-2 w-full px-3 py-0"):
            target.label(label).classes("text-xs opacity-60 w-20")
            target.label(str(value)).classes("text-xs truncate")
