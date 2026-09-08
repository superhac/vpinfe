"""The last look before an import writes anything: what will land, and what will not.

Every row says three things, because those are the three a person is actually deciding
between: what the file is, what it is called, and what it does to whatever is there
already. The third is the one that matters and the one a file listing never tells you.

Nothing here is inferred from a filename. Where the drop landed named the game, and for
a media slot the kind as well, so this dialog confirms a decision rather than asking for
one that was already made.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nicegui import run, ui

logger = logging.getLogger("vpinfe.console.import_dialog")


def _size(count: int) -> str:
    size = float(count or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _where(plan: dict[str, Any], item: dict[str, Any]) -> str:
    """Where this lands, relative to the game folder - the folder itself is named by the
    title, and repeating it on every row buries the part that differs."""
    base = Path(str(plan.get("game_dir") or ""))
    found = Path(str(item.get("destination") or ""))
    try:
        rel = found.relative_to(base)
    except ValueError:
        return str(found)
    if item.get("action") == "extract_tree":
        return f"{rel.as_posix()}/"
    if item.get("action") == "replace_media":
        return rel.as_posix()
    if str(rel.parent) == ".":
        return "the game folder"
    if rel.name == str(item.get("name") or ""):
        return f"{rel.parent.as_posix()}/"
    return rel.as_posix()


async def open_for(library: Any, upload_id: str, plan: dict[str, Any], *,
                   source: str = "", game_dir: str = "", rom_name: str = "",
                   allow_new_game: bool = False, media_kind: str = "",
                   declared: dict | None = None,
                   on_done: Callable[[dict], Any] | None = None) -> None:
    """Show the plan and, if it is confirmed, run it.

    The dialog owns the upload from here: whichever way it closes, the staged files are
    either imported or thrown away. A session left behind is invisible rubbish in a temp
    directory that nothing else will ever clean up.
    """
    items = list(plan.get("items") or [])
    blocked = list(plan.get("blocked") or [])
    new_folder = str(plan.get("new_game_dir_name") or "")
    chosen: dict[int, bool] = {int(one["index"]): bool(one.get("default_enabled", True))
                               for one in items}
    # A single item with nothing blocked is not a choice, so it gets no checkbox - the
    # button already says what will happen.
    single = len(items) == 1 and not blocked
    named: dict[str, Any] = {"folder": new_folder, "vps_id": ""}

    with ui.dialog().props("persistent") as dialog, \
            ui.card().classes("console-import-card"):
        if new_folder:
            ui.label(f"Import from {source or 'this drop'}") \
                .classes("console-confirm-title")
            ui.label("The files keep their names. Only the folder is named here.") \
                .classes("console-help")
        else:
            ui.label(f"Import into {Path(str(plan.get('game_dir') or '')).name}") \
                .classes("console-confirm-title")
            if not single and source:
                ui.label(f"from {source}").classes("console-help")

        if new_folder:
            _folder_row(library, named, plan)

        rows = ui.column().classes("gap-0 w-full console-import-rows")

        if blocked:
            with ui.expansion(f"Not imported ({len(blocked)})") \
                    .props("dense dense-toggle").classes("console-import-blocked"):
                for one in blocked:
                    ui.label(f"{one.get('kind') or ''} - {one.get('reason') or ''}") \
                        .classes("console-help")

        count = ui.label("").classes("console-help")

        def recount() -> None:
            wanted = sum(1 for value in chosen.values() if value)
            count.text = ("" if single else
                          f"{wanted} of {len(items)} will be imported")

        with rows:
            for one in items:
                _draw_row(one, plan, chosen, single, recount)
        recount()

        with ui.row().classes("justify-end gap-2 w-full pt-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)) \
                .props("flat no-caps")
            go = ui.button("Import", on_click=lambda: dialog.submit(True)) \
                .props("no-caps")
            if not items:
                go.disable()

    said = await dialog
    if not said:
        await run.io_bound(library.abort_upload, upload_id)
        return

    wanted = None if single else [i for i, on in sorted(chosen.items()) if on]
    if wanted is not None and not wanted:
        await run.io_bound(library.abort_upload, upload_id)
        ui.notify("Nothing was selected, so nothing was imported", type="warning")
        return

    note = ui.notification("Importing…", spinner=True, timeout=None)
    try:
        report = await run.io_bound(
            library.upload_import, upload_id, game_dir=game_dir, rom_name=rom_name,
            allow_new_game=allow_new_game, media_kind=media_kind,
            vps_id=str(named["vps_id"] or ""),
            new_game_dir_name=(str(named["folder"]) if new_folder else None),
            selected=wanted, declared=declared)
    except Exception as exc:  # noqa: BLE001
        note.dismiss()
        ui.notify(f"Could not import it: {exc}", type="negative")
        await run.io_bound(library.abort_upload, upload_id)
        return
    note.dismiss()
    brought = int(report.get("imported") or 0)
    ui.notify(f"Imported {brought} item{'' if brought == 1 else 's'}", type="positive")
    if report.get("vps_error"):
        # The import worked and the match did not. Two facts, and rolling the second
        # into a failure would say the files did not land when they did.
        ui.notify(f"Imported, but could not match it: {report['vps_error']}",
                  type="warning")
    if on_done is not None:
        answer = on_done(report)
        if hasattr(answer, "__await__"):
            await answer


def _draw_row(item: dict[str, Any], plan: dict[str, Any], chosen: dict[int, bool],
              single: bool, changed: Callable[[], None]) -> None:
    """One thing that will land: what it is, what it is called, where it goes, and what
    it replaces."""
    index = int(item["index"])
    with ui.row().classes("items-center gap-2 w-full no-wrap console-import-row"):
        if not single:
            box = ui.checkbox(value=chosen[index]).props("dense")
            box.on_value_change(lambda: (chosen.__setitem__(index, bool(box.value)),
                                         changed()))
        # Fixed width, so the names beside them line up and the column reads down.
        ui.label(str(item.get("label") or item.get("kind") or "")) \
            .classes("console-import-kind")
        with ui.column().classes("gap-0 grow min-w-0"):
            ui.label(str(item.get("name") or "")) \
                .classes("console-member-name truncate")
            said = f"→ {_where(plan, item)}"
            if item.get("replaces"):
                said += f" · {item['replaces']}"
            ui.label(said).classes("console-member-table truncate")
        ui.label(_size(int(item.get("size") or 0))) \
            .classes("console-member-qualifier")


def _folder_row(library: Any, named: dict[str, Any], plan: dict[str, Any]) -> None:
    """The folder a new game is created as, and the upstream record it is named from.

    Searched rather than typed where there is a match: the folder name is a convention
    other tools read, and getting it from the record is how it stays one.
    """
    with ui.row().classes("items-center gap-2 w-full no-wrap pt-1"):
        field = ui.input(value=str(named["folder"] or "")) \
            .props("outlined dense debounce=0").classes("grow")
        field.on_value_change(lambda: named.__setitem__("folder", field.value or ""))
        ui.button("Match", on_click=lambda: _match(library, named, field)) \
            .props("flat dense no-caps size=sm") \
            .tooltip("Name the folder from the upstream record")
    del plan


async def _match(library: Any, named: dict[str, Any], field: Any) -> None:
    """Offer what the catalog has for this name, and take the folder name from it."""
    term = str(field.value or "").split("(")[0].strip()
    try:
        found = await run.io_bound(library.vps_search, term, 8)
    except Exception as exc:  # noqa: BLE001
        ui.notify(f"Could not search: {exc}", type="negative")
        return
    if not found:
        ui.notify("Nothing in the catalog matches that name", type="warning")
        return
    offered = {str(one.get("vps_id") or ""):
               f"{one.get('name') or ''} ({one.get('manufacturer') or ''} "
               f"{one.get('year') or ''})".replace(" )", ")")
               for one in found}
    with ui.dialog() as picker, ui.card().classes("console-confirm"):
        ui.label("Which one is this?").classes("console-confirm-title")
        ui.label("The folder is named from the record, so other tools reading this "
                 "library recognize it.").classes("console-help")
        # Pre-selected on the best match rather than left empty: the top hit is right
        # nearly always, and an empty picker asks somebody to re-read what they typed.
        holds = {"id": next(iter(offered), "")}
        ui.select(offered, value=holds["id"],
                  on_change=lambda e: holds.__setitem__("id", str(e.value or ""))) \
            .props("outlined dense").classes("w-full")
        with ui.row().classes("justify-end gap-2 w-full pt-2"):
            ui.button("Cancel", on_click=lambda: picker.submit("")) \
                .props("flat no-caps")
            ui.button("Use this", on_click=lambda: picker.submit(holds["id"])) \
                .props("no-caps")

    picked = await picker
    if not picked:
        return
    entry = next((one for one in found if str(one.get("vps_id")) == picked), None)
    if entry is None:
        return
    named["vps_id"] = picked
    folder = str(entry.get("folder_name") or "")
    if folder:
        named["folder"] = folder
        field.value = folder
