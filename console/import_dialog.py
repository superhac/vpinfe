
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

from common.i18n import t
from console import dialog as frame
from console import offload, panel, verbs

logger = logging.getLogger("vpinfe.console.import_dialog")


def _size(count: int) -> str:
    size = float(count or 0)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
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
        return t("console.import_dialog.game_folder")
    if rel.name == str(item.get("name") or ""):
        return f"{rel.parent.as_posix()}/"
    return rel.as_posix()


async def ask_where(library: Any) -> str | None:
    """Which location a new game goes to. "" means the one already marked for it, and
    None means do not import at all.

    Three outcomes, and only one of them is a question. Where the marked location works
    and there is nothing else it could be, nothing is asked - a question with one answer
    is a click charged for nothing. Where it does not work, this refuses and says why,
    offering the places that would work rather than only reporting a failure. And where
    it works but there is a choice, it asks only while somebody wants to be asked.
    """
    try:
        found = await offload.io(library.new_game_destination)
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.import_dialog.could_not_work_where", exc=(exc)), type="negative")
        return None

    others = list(found.get("alternatives") or [])
    if found.get("reason"):
        return await _no_destination(library, found, others)
    if not found.get("ask"):
        return ""
    return await _which_destination(library, found, others)


async def _no_destination(library: Any, found: dict[str, Any],
                          others: list[dict[str, Any]]) -> str | None:
    """It cannot go where it was told to. Refuse, say why, and offer the rest."""
    if not others:
        ui.notify(str(found.get("reason") or t("console.import_dialog.nowhere_put_new_game")),
                  type="negative")
        return None
    return await _pick(library, str(found.get("reason") or ""), others,
                       offer_remember=False)


async def _which_destination(library: Any, found: dict[str, Any],
                             others: list[dict[str, Any]]) -> str | None:
    """It could go to more than one place, and somebody wants to be asked."""
    marked = {"location_id": found.get("location_id"), "name": found.get("name"),
              "path": found.get("path")}
    return await _pick(library, "", [marked, *others], offer_remember=True)


async def _pick(library: Any, reason: str, offered: list[dict[str, Any]],
                *, offer_remember: bool) -> str | None:
    holds = {"id": str(offered[0].get("location_id") or ""), "stop_asking": False}
    with frame.opened(t("console.import_dialog.where_should_game_go")) as picker:
        if reason:
            # The refusal leads, because it is the reason they are being asked at all.
            ui.label(reason).classes("console-help px-3")
        panel.facts(ui, [(t("word.location"), panel.select(
            {str(one.get("location_id") or ""): str(one.get("name") or one.get("path") or "")
             for one in offered},
            str(holds["id"]), lambda e: holds.__setitem__("id", str(e.value or ""))))])
        if offer_remember:
            # Offered here rather than only in Settings, because this is the moment
            # somebody knows whether they want to be asked again.
            with ui.element("div").classes("px-3"):
                ui.checkbox(t("console.import_dialog.always_use_one_not"),
                            on_change=lambda e: holds.__setitem__("stop_asking",
                                                                  bool(e.value))) \
                    .props("dense").classes("console-help")
        with frame.footer():
            frame.cancel(lambda: picker.submit(None))
            frame.answer(t("console.import_dialog.use"),
                         lambda: picker.submit(holds["id"]), icon=verbs.ACCEPT)

    said = await picker
    if said is None:
        return None
    if holds["stop_asking"]:
        try:
            await run.io_bound(
                library.put_config,
                {"general": {"ask_where_new_games_go": False}})
            await run.io_bound(library.set_location_write_to, said)
        except Exception as exc:  # noqa: BLE001
            # The import still goes where they said. Only the remembering failed.
            ui.notify(t("console.import_dialog.could_not_remember", exc=(exc)), type="warning")
    return said


async def open_for(library: Any, upload_id: str, plan: dict[str, Any], *,
                   source: str = "", game_dir: str = "", rom_name: str = "",
                   allow_new_game: bool = False, media_kind: str = "",
                   location_id: str = "", asset_kind: str = "",
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

    with frame.opened(
            (t("console.import_dialog.import_2", value=source) if source
             else t("console.import_dialog.import_drop")) if new_folder
            else t("console.import_dialog.import_3",
                   name=Path(str(plan.get("game_dir") or "")).name),
            wide=True, persistent=True, classes="console-import-card") as dialog:
        if new_folder:
            ui.label(t("console.import_dialog.files_keep_names_folder")) \
                .classes("console-help px-3")
            _folder_row(library, named, plan)
        elif not single and source:
            ui.label(t("console.import_dialog.from", source=(source))) \
                .classes("console-help px-3")

        rows = ui.column().classes("gap-0 w-full console-import-rows px-3")

        if blocked:
            with ui.expansion(t("console.import_dialog.not_imported", len=(len(blocked)))) \
                    .props("dense dense-toggle") \
                    .classes("console-disclosure console-import-blocked px-3"):
                for one in blocked:
                    kind = t(f"asset.kind.{one.get('kind') or ''}.label")
                    ui.label(f"{kind} - {one.get('reason') or ''}").classes("console-help")

        count = ui.label("").classes("console-help px-3")

        def recount() -> None:
            wanted = sum(1 for value in chosen.values() if value)
            count.text = ("" if single else
                          t("console.import_dialog.imported", wanted=(wanted),
                                  len=(len(items))))

        with rows:
            for one in items:
                _draw_row(one, plan, chosen, single, recount)
        recount()

        with frame.footer():
            frame.cancel(lambda: dialog.submit(False))
            go = frame.answer(t("console.import_dialog.import"),
                              lambda: dialog.submit(True), icon=verbs.IMPORT)
            if not items:
                go.disable()

    said = await dialog
    if not said:
        await run.io_bound(library.abort_upload, upload_id)
        return

    wanted = None if single else [i for i, on in sorted(chosen.items()) if on]
    if wanted is not None and not wanted:
        await run.io_bound(library.abort_upload, upload_id)
        ui.notify(t("console.import_dialog.nothing_selected_nothing_imported"), type="warning")
        return

    note = ui.notification(t("console.import_dialog.importing"), spinner=True, timeout=None)
    try:
        report = await offload.io(
            library.upload_import, upload_id, game_dir=game_dir, rom_name=rom_name,
            allow_new_game=allow_new_game, media_kind=media_kind,
            location_id=location_id, asset_kind=asset_kind,
            vps_id=str(named["vps_id"] or ""),
            new_game_dir_name=(str(named["folder"]) if new_folder else None),
            selected=wanted, declared=declared)
    except Exception as exc:  # noqa: BLE001
        note.dismiss()
        ui.notify(t("console.import_dialog.could_not_import", exc=(exc)), type="negative")
        await run.io_bound(library.abort_upload, upload_id)
        return
    note.dismiss()
    brought = int(report.get("imported") or 0)
    ui.notify(t("console.import_dialog.imported_item", brought=(brought),
            value=('' if brought == 1 else 's')), type="positive")
    if report.get("vps_error"):
        # The import worked and the match did not. Two facts, and rolling the second
        # into a failure would say the files did not land when they did.
        ui.notify(t("console.import_dialog.imported_could_not_match", value=(report['vps_error'])),
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

            def picked() -> None:
                chosen[index] = bool(box.value)
                changed()

            box.on_value_change(picked)
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
    def draw() -> None:
        with ui.row().classes("items-center gap-2 w-full no-wrap console-field-row"):
            field = frame.field(str(named["folder"] or ""))
            field.on_value_change(lambda: named.__setitem__("folder", field.value or ""))
            panel.action(t("console.import_dialog.match"),
                         lambda: _match(library, named, field), icon=verbs.MATCH,
                         inline=True,
                         hint=t("console.import_dialog.name_folder_upstream_record"))()

    panel.facts(ui, [(t("word.folder"), draw)])
    del plan


async def _match(library: Any, named: dict[str, Any], field: Any) -> None:
    """Offer what the catalog has for this name, and take the folder name from it."""
    term = str(field.value or "").split("(")[0].strip()
    try:
        found = await offload.io(library.vps_search, term, 8)
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.import_dialog.could_not_search", exc=(exc)), type="negative")
        return
    if not found:
        ui.notify(t("console.import_dialog.nothing_spreadsheet_matches_name"), type="warning")
        return
    offered = {str(one.get("vps_id") or ""):
               f"{one.get('name') or ''} ({one.get('manufacturer') or ''} "
               f"{one.get('year') or ''})".replace(" )", ")")
               for one in found}
    holds = {"id": next(iter(offered), "")}
    with frame.opened(t("console.import_dialog.one")) as picker:
        ui.label(t("console.import_dialog.folder_named_record_other")) \
            .classes("console-help px-3")
        panel.facts(ui, [(t("word.game"), panel.select(
            offered, holds["id"], lambda e: holds.__setitem__("id", str(e.value or ""))))])
        with frame.footer():
            frame.cancel(lambda: picker.submit(""))
            frame.answer(t("console.import_dialog.use"),
                         lambda: picker.submit(holds["id"]), icon=verbs.ACCEPT)

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
