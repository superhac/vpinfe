"""Browsing this machine to fill a path field with a folder, a program or a file.

`list_entries` is `library.folders`, taken as a parameter rather than imported: this
draws for any field that wants a path, and none of them is the library client.
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

_TITLE = {"dir": "console.folder_picker.choose_a_folder",
         "exe": "console.folder_picker.choose_a_program",
         "file": "console.folder_picker.choose_a_file"}
_ROW_ICON = {"exe": "terminal", "file": "description"}


@on_page
async def pick_path(list_entries: Callable[..., dict], start: str = "", *,
                    kind: str = "dir", suffixes: tuple[str, ...] = ()) -> str | None:
    """The chosen path, or None where the dialog was cancelled.

    A `start` that cannot be listed opens at the kind's own start instead of failing to
    open at all - the field it came from may hold a path from a mount that has since
    gone away.
    """
    try:
        here = await offload.io(list_entries, start, kind, suffixes)
    except Exception:  # noqa: BLE001 - a stale saved path is not a reason to refuse
        here = await offload.io(list_entries, "", kind, suffixes)

    picked = start if kind != "dir" and any(
        f["path"] == start for f in here.get("files") or []) else ""
    state: dict[str, Any] = {"here": here, "selected": picked}
    choose: dict[str, Any] = {}

    with frame.opened(t(_TITLE[kind]), wide=True) as box:
        roots_row = ui.row().classes("items-center gap-1 flex-wrap px-3")
        path_row = ui.row().classes("items-center gap-2 w-full no-wrap px-3")
        term = ui.input(placeholder=t("console.folder_picker.filter_folders" if kind == "dir"
                                      else "console.folder_picker.filter")) \
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

        def select(path: str) -> None:
            state["selected"] = path
            draw_listing()
            if "button" in choose:
                choose["button"].enable()

        def draw_listing() -> None:
            listing_col.clear()
            wanted = (term.value or "").strip().lower()
            folders = [f for f in state["here"]["folders"] if wanted in f["name"].lower()]
            files = [f for f in state["here"].get("files") or []
                    if wanted in f["name"].lower()]
            with listing_col:
                if not folders and not files:
                    ui.label(t("console.folder_picker.no_folders" if kind == "dir"
                              else "console.folder_picker.nothing_here")) \
                        .classes("console-help")
                for folder in folders:
                    row = ui.row().classes(
                        "items-center gap-2 w-full no-wrap console-source-row "
                        "console-source-row--pick console-source-row--line")
                    with row:
                        ui.icon("folder").classes("shrink-0")
                        ui.label(folder["name"]).classes("console-source-name grow")
                    row.on("click", lambda p=folder["path"]: _go(p))
                for one in files:
                    classes = ("items-center gap-2 w-full no-wrap console-source-row "
                              "console-source-row--pick console-source-row--line")
                    if one["path"] == state["selected"]:
                        classes += " console-source-row--chosen"
                    row = ui.row().classes(classes)
                    with row:
                        ui.icon(_ROW_ICON[kind]).classes("shrink-0")
                        ui.label(one["name"]).classes("console-source-name grow")
                    row.on("click", lambda p=one["path"]: select(p))
                    row.on("dblclick", lambda p=one["path"]: box.submit(p))

        @on_page
        async def _go(path: str) -> None:
            try:
                fresh = await offload.io(list_entries, path, kind, suffixes)
            except Exception as exc:  # noqa: BLE001
                ui.notify(t("console.mediasource.could_not_read_folder"), caption=why(exc),
                          type="negative")
                return
            state["here"] = fresh
            state["selected"] = ""
            term.value = ""
            draw_path()
            draw_listing()
            if "button" in choose:
                choose["button"].disable()

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
            if kind == "dir":
                frame.answer(t("console.folder_picker.choose_this_folder"),
                            lambda: box.submit(state["here"]["path"]), icon=verbs.CHOOSE)
            else:
                choose["button"] = frame.answer(
                    t("console.folder_picker.choose"),
                    lambda: box.submit(state["selected"]), icon=verbs.CHOOSE)
                if not state["selected"]:
                    choose["button"].disable()

    return await box
