"""Browsing this machine for a folder to fill a path field with.

`list_folders` is `library.folders`, taken as a parameter rather than imported: this
draws for any field that wants a directory, and none of them is the library client.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from common.failures import why
from common.i18n import t
from console import dialog as frame
from console import offload, panel, verbs
from console.on_page import on_page


@on_page
async def pick_folder(list_folders: Callable[[str], dict], start: str = "") -> str | None:
    """The chosen folder's path, or None where the dialog was cancelled.

    A `start` that cannot be listed opens at home instead of failing to open at all -
    the field it came from may hold a path from a mount that has since gone away.
    """
    try:
        here = await offload.io(list_folders, start)
    except Exception:  # noqa: BLE001 - a stale saved path is not a reason to refuse
        here = await offload.io(list_folders, "")

    state: dict[str, Any] = {"here": here}

    with frame.opened(t("console.folder_picker.choose_a_folder"), wide=True) as box:
        roots_row = ui.row().classes("items-center gap-1 flex-wrap px-3")
        path_row = ui.row().classes("items-center gap-2 w-full no-wrap px-3")
        term = ui.input(placeholder=t("console.folder_picker.filter_folders")) \
            .props("dense outlined clearable clear-icon=close").classes("w-full px-3")
        listing_col = ui.column().classes("w-full gap-1 console-folder-list px-3")

        def draw_path() -> None:
            path_row.clear()
            with path_row:
                up = panel.icon_only(verbs.UP, lambda: _go(state["here"]["parent"]),
                                     hint=t("console.folder_picker.up"))
                if not state["here"]["parent"]:
                    up.disable()
                ui.label(state["here"]["path"]).classes("console-help grow truncate")

        def draw_listing() -> None:
            listing_col.clear()
            wanted = (term.value or "").strip().lower()
            shown = [folder for folder in state["here"]["folders"]
                    if wanted in folder["name"].lower()]
            with listing_col:
                if not shown:
                    ui.label(t("console.folder_picker.no_folders")).classes("console-help")
                for folder in shown:
                    row = ui.row().classes(
                        "items-center gap-2 w-full no-wrap console-source-row "
                        "console-source-row--pick console-source-row--line")
                    with row:
                        ui.icon("folder").classes("shrink-0")
                        ui.label(folder["name"]).classes("console-source-name grow")
                    row.on("click", lambda p=folder["path"]: _go(p))

        @on_page
        async def _go(path: str) -> None:
            try:
                fresh = await offload.io(list_folders, path)
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("console.mediasource.could_not_read_folder"), caption=why(exc),
                          type="negative")
                return
            state["here"] = fresh
            term.value = ""
            draw_path()
            draw_listing()

        def _opens(path: str) -> Callable[[], Any]:
            return lambda: _go(path)

        with roots_row:
            for root in here.get("roots") or []:
                frame.quiet(root["name"], _opens(root["path"]),
                           icon=verbs.BROWSE).props("dense")
        draw_path()
        draw_listing()
        term.on_value_change(draw_listing)

        with frame.footer():
            frame.cancel(lambda: box.submit(None))
            frame.answer(t("console.folder_picker.choose_this_folder"),
                        lambda: box.submit(state["here"]["path"]), icon=verbs.CHOOSE)

    return await box
