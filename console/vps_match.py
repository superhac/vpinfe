
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

# What `ask` hands back, so a caller never has to read `None` and `""` as magic.
CANCELLED = None
CLEARED = ""
# Ending a walk, and it has to be a string because it travels the same return as an id.
# A NUL cannot occur in one, so this can never be mistaken for a VPS id.
STOPPED = "\x00stopped"


async def ask(library: Any, game: dict[str, Any], place: str = "",
              walking: bool = False) -> str | None:
    """Ask which VPS entry this game is. The caller writes; this only asks.

    Answers with the chosen id, `CLEARED` to drop the binding, `CANCELLED` to do nothing,
    or `STOPPED` when walking. `place` is "3 of 34", empty for a single game.

    `walking` splits Cancel into Skip and Stop, which are different intents in a run and
    cannot share one button.
    """
    bound = str(game.get("vps_id") or "")
    entry = await offload.io(library.vps_entry, bound) if bound else {}
    picked = {"id": bound}

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

            _entry_row(entry, trailing=clear)

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
                               on_click=lambda: dialog.submit(str(picked["id"]))) \
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

        def take(vps_id: str) -> None:
            picked["id"] = vps_id
            update.set_visibility(vps_id != bound)
            draw()

        def draw() -> None:
            found.clear()
            with found:
                for row in rows:
                    this = str(row.get("vps_id") or "")
                    _entry_row(row, pick=partial(take, this),
                               chosen=this == picked["id"])

        async def look() -> None:
            said = str(field.value or "").strip()
            rows[:] = await offload.io(library.vps_search, said, 40) if said else []
            heading.text = (t("console.vps_match.results", count=len(rows))
                            if said else "")
            if not said or not rows:
                found.clear()
                with found:
                    ui.label(t("console.vps_match.type_name_maker_year") if not said
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
        try:
            await run.io_bound(library.set_game_overrides, str(game.get("id") or ""),
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


def _entry_row(row: dict[str, Any], *, pick: Callable[[], None] | None = None,
               chosen: bool = False,
               trailing: Callable[[], None] | None = None) -> None:
    """One VPS entry, in the shape the games grid draws a game in.

    `pick` absent draws it without making it a target. `trailing` puts one control at
    the end, after the way out to the catalog.
    """
    said = [" ".join(str(row.get(k) or "") for k in ("manufacturer", "year")).strip()]
    count = int(row.get("releases") or 0)
    if count:
        said.append(t("console.vps_match.release" if count == 1
                      else "console.vps_match.releases", count=count))
    url = str(row.get("url") or "")

    def end() -> None:
        with ui.row().classes("items-center gap-2 no-wrap shrink-0"):
            if url:
                # Or reading the entry would also pick it.
                with ui.element("div").on("click.stop", lambda: None):
                    panel.link_out(t("word.view"), to=url)()
            if trailing is not None:
                with ui.element("div").on("click.stop", lambda: None):
                    trailing()

    candidates.choice(str(row.get("img_url") or ""), str(row.get("name") or ""),
                      " · ".join(part for part in said if part),
                      pick, glyph=icons.GAMES, chosen=chosen,
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
