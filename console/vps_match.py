
"""Binding a game to its VPS entry, from the panel or from a grid selection.

Both callers come through here so there is one picker rather than two that drift.

**Nothing here ranks a result and nothing here assigns one.** A ranker was built for this
list and retired for scoring at chance, so the order is the one VPS answers in and the
choice is always a person's.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from typing import Any

from nicegui import run, ui

from common import icons
from common.i18n import t
from console import candidates, offload, panel, verbs

logger = logging.getLogger("vpinfe.console.vps_match")

# A NUL cannot occur in a VPS id, so neither of these can be mistaken for one.
CANCELLED = None
CLEARED = "\x00none"
STOPPED = "\x00stopped"


async def ask(library: Any, game: dict[str, Any], place: str = "",
              walking: bool = False) -> str | None:
    """Ask which VPS entry this game is. The caller writes; this only asks.

    Answers with the chosen id, `""` where the choice is the one the scan already found
    and no override is wanted, `CLEARED` to say the machine is in no catalog, `CANCELLED`
    to do nothing, or `STOPPED` when walking. `place` is "3 of 34", empty for a game.

    `walking` splits Cancel into Skip and Stop, which are different intents in a run and
    cannot share one button.
    """
    bound = str(game.get("vps_id") or "")
    entry = await offload.io(library.vps_entry, bound) if bound else {}
    held = await offload.io(library.vps_catalog_held)
    picked = {"id": bound}
    scanned = str((game.get("discovered") or {}).get("vps_id") or "")
    behind = (await offload.io(library.vps_entry, scanned)
              if scanned and scanned != bound else {})

    with ui.dialog().props("persistent") as dialog, \
            ui.card().classes("console-confirm console-picker-dialog"):
        ui.label(t("console.vps_match.match_named",
                   name=(str(game.get("name") or "")))) \
            .classes("console-confirm-title")
        if place:
            ui.label(place).classes("console-help")

        if entry:
            ui.label(t("console.vps_match.current_match")).classes("console-group")
            def clear() -> None:
                ui.button(t("console.vps_match.clear_match"), icon=verbs.UNMATCH,
                          on_click=lambda: dialog.submit(CLEARED)) \
                    .props("flat dense no-caps size=sm") \
                    .classes("console-action console-action--danger shrink-0")

            entry_row(entry, trailing=clear)

        if behind:
            ui.label(t("console.vps_match.original_match")).classes("console-group")

            def take_scanned() -> None:
                ui.button(t("console.vps_match.use_this"), icon=verbs.ACCEPT,
                          on_click=lambda: dialog.submit(answer(scanned))) \
                    .props("flat dense no-caps size=sm") \
                    .classes("console-action shrink-0")

            entry_row(behind, trailing=take_scanned)

        ui.label(t("console.vps_match.search_for_match")).classes("console-group")
        with ui.row().classes("items-center gap-2 w-full no-wrap"):
            field = ui.input(value=_seed(game)) \
                .props("dense autofocus clearable").classes("console-edit-field grow")
            ui.button(t("console.vps_match.search"), icon=verbs.SEARCH,
                      on_click=lambda: look()).props("flat dense no-caps size=sm") \
                .classes("console-action shrink-0")
        heading = ui.label("").classes("console-group")
        found = ui.column().classes("w-full gap-0 console-source-list")

        with ui.row().classes("items-center justify-end gap-2 w-full"):
            update = ui.button(t("console.vps_match.update_match"), icon=verbs.ACCEPT,
                               on_click=lambda: dialog.submit(answer(str(picked["id"])))) \
                .props("no-caps")
            ui.button(t("word.cancel"), icon=verbs.CANCEL,
                      on_click=lambda: dialog.submit(CANCELLED)).props("flat no-caps")
            if walking:
                ui.button(t("console.vps_match.skip"), icon=verbs.SKIP,
                          on_click=lambda: dialog.submit(CANCELLED)).props("flat no-caps")
                ui.button(t("console.vps_match.stop"), icon=verbs.STOP,
                          on_click=lambda: dialog.submit(STOPPED)).props("flat no-caps")
        update.set_visibility(False)

        rows: list[dict[str, Any]] = []

        def answer(vps_id: str) -> str:
            """An override, or "" where the choice is the scan's own answer."""
            return "" if vps_id and vps_id == scanned else vps_id

        def take(vps_id: str) -> None:
            picked["id"] = vps_id
            update.set_visibility(vps_id != bound)
            draw()

        def draw() -> None:
            found.clear()
            with found:
                for row in rows:
                    this = str(row.get("vps_id") or "")
                    entry_row(row, pick=partial(take, this),
                               chosen=this == picked["id"], bound=this == bound)

        async def look() -> None:
            said = str(field.value or "").strip()
            rows[:] = await offload.io(library.vps_search, said, 40) if said else []
            heading.text = (t("console.vps_match.results", count=len(rows))
                            if said and held else "")
            if not said or not rows:
                found.clear()
                with found:
                    ui.label(t("console.vps_match.vps_not_downloaded") if not held
                             else t("console.vps_match.type_name_maker_year") if not said
                             else t("console.vps_match.nothing_vps_matches", said=(said))) \
                        .classes("console-help")
                return
            draw()

        field.on("keydown.enter", look)
        await look()

    return await dialog


async def walk(library: Any, games: list[dict[str, Any]]) -> None:
    """Work through several games' matches, one picker at a time.

    The selection is whatever the grid was filtered to, matched or not. **Skip leaves a
    game exactly as it was** - nothing is rewritten for being in the selection, which is
    why this walks rather than runs.
    """
    total = len(games)
    changed = 0
    for index, game in enumerate(games, 1):
        picked = await ask(library, game, walking=True,
                           place=t("console.vps_match.index_of_total",
                                   index=index, total=total))
        if picked == STOPPED:
            break
        if picked is CANCELLED:
            continue
        game_id = str(game.get("id") or "")
        try:
            if picked == CLEARED:
                await run.io_bound(library.declare_no_match, game_id)
            else:
                await run.io_bound(library.set_game_overrides, game_id,
                                   {"alt_vps_id": str(picked)})
        except Exception as exc:  # noqa: BLE001 - one bad write does not end the walk
            logger.exception("Could not set the match for %s", game.get("id"))
            ui.notify(t("console.vps_match.could_not_set_match", exc=(exc)), type="negative")
            continue
        changed += 1
    # Said once at the end rather than per game: a toast after every pick in a run of
    # thirty is noise covering the thing you are looking at.
    ui.notify(t("console.vps_match.match_set", changed=(changed),
            value=('' if changed == 1 else 'es')) if changed
              else t("console.vps_match.nothing_changed"), type="positive" if changed else "info")


def _seed(game: dict[str, Any]) -> str:
    """The query the search opens on: a starting point, visible and editable."""
    said = str(game.get("name") or "")
    if game.get("vps_id"):
        return said
    answered = game.get("overrides") or {}
    parts = [said] + [str(answered.get(key) or "").strip()
                      for key in ("alt_manufacturer", "alt_year")]
    return " ".join(part for part in parts if part)


def entry_row(row: dict[str, Any], *, pick: Callable[[], None] | None = None,
               chosen: bool = False, bound: bool = False,
               trailing: Callable[[], None] | None = None) -> None:
    """One VPS entry, in the shape the games grid draws a game in.

    `pick` absent draws it without making it a target. `trailing` puts one control at
    the end, after the way out to the catalog.
    """
    said = " ".join(str(row.get(k) or "") for k in ("manufacturer", "year")).strip()
    url = str(row.get("url") or "")

    def end() -> None:
        with ui.row().classes("items-center gap-2 no-wrap shrink-0"):
            if bound:
                panel.state(t("console.vps_match.current"), "on")()
            if url:
                # Or reading the entry would also pick it.
                with ui.element("div").on("click.stop", lambda: None):
                    panel.out(to=url, hint=t("console.vps_match.open_in_vps"))()
            if trailing is not None:
                with ui.element("div").on("click.stop", lambda: None):
                    trailing()

    candidates.choice(str(row.get("img_url") or ""), str(row.get("name") or ""),
                      said, pick, glyph=icons.GAMES, chosen=chosen,
                      trailing=end, entry=True)


def _match_row(row: dict[str, Any], dialog: Any) -> None:
    """One candidate, with the machine's photograph where VPS has one.

    Named twice over - by the maker and year that tell two machines of one name apart,
    and by the picture, which settles it faster than either. The release count rides in
    the same line: it says which entry the world actually builds for, and it is not a
    judgement of the match, which nothing here makes.
    """
    said = [" ".join(str(row.get(k) or "") for k in ("manufacturer", "year")).strip()]
    count = int(row.get("releases") or 0)
    if count:
        said.append(t("console.vps_match.release" if count == 1
                      else "console.vps_match.releases", count=count))
    candidates.choice(str(row.get("img_url") or ""), str(row.get("name") or ""),
                      " · ".join(part for part in said if part),
                      lambda: dialog.submit(str(row.get("vps_id") or "")),
                      glyph=icons.GAMES)
