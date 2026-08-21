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



        # Off the loop, always. This is an HTTP call to our own process: made on the
        # event loop it blocks the server from answering it, the request times out
        # after 15s, and the browser reports the socket as lost rather than slow.
        tables = await run.io_bound(library.tables_for, game_id)

        media = library.media.get(game_id, {})
        present, borrowed, total = mediamap.summary(media)
        # First, not last. This is the question people actually have about a game, and
        # the shape of the map answers it before any label is read.
        label = f"Media ({present}/{total}"
        label += f", {borrowed} borrowed)" if borrowed else ")"
        with ui.expansion(label, value=True).classes("w-full"), \
                ui.column().classes("w-full gap-0"):
            await _media_block(library, game_id, tables)

        with ui.expansion("Identity").classes("w-full"):
            _rows(ui, {
                "VPS id": game.get("vps_id") or "-",
                "ROM": game.get("rom") or "-",
                "Type": game.get("type") or "-",
                "Themes": ", ".join(game.get("themes") or []) or "-",
            })

        with ui.expansion(f"Tables ({len(tables)})").classes("w-full"):
            for table in tables:
                with ui.row().classes("items-center gap-2 w-full px-3"):
                    ui.label(table.get("filename") or "").classes("text-xs truncate")
                    ui.badge(table.get("app") or "?", color="secondary").props("outline")



def _prefix(game_id: str, table_id: str) -> str:
    return (f"/api/v1/games/{game_id}/tables/{table_id}/media" if table_id
            else f"/api/v1/games/{game_id}/media")


async def _media_block(library: Library, game_id: str,
                       tables: list[dict[str, Any]]) -> None:
    """The map, and - only where a folder holds more than one build - a lens over it.

    One table means one answer, so the control never appears and nobody meets the
    concept. That is the common case by a long way.
    """
    state = {"table": ""}
    note = ui.label().classes("hub-help px-2")
    holder = ui.column().classes("w-full gap-0")

    async def draw() -> None:
        table_id = state["table"]
        entries = await run.io_bound(library.media_for, game_id, table_id or None)
        note.text = ("Named for this .vpx. Only this table uses them."
                     if table_id else
                     "Named for the folder. Every table in this game uses them.")
        holder.clear()
        with holder:
            mediamap.build(entries, _prefix(game_id, table_id))

    async def pick(event: Any) -> None:
        state["table"] = event.value or ""
        await draw()

    if len(tables) > 1:
        options = {"": "Shared"}
        options.update({table["id"]: table.get("filename") or table["id"]
                        for table in tables if table.get("id")})
        ui.select(options, value="", label="Viewing as", on_change=pick) \
            .props("dense outlined").classes("w-full px-2 pt-1")
    else:
        note.set_visibility(False)
    await draw()


def _rows(target: Any, values: dict[str, str]) -> None:
    for label, value in values.items():
        with target.row().classes("items-center gap-2 w-full px-3 py-0"):
            target.label(label).classes("text-xs opacity-60 w-20")
            target.label(str(value)).classes("text-xs truncate")
