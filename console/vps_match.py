
"""Binding a game to its VPS entry, from the panel or from a grid selection.

Both callers come through here so there is one picker rather than two that drift.

**Nothing here ranks a result and nothing here assigns one.** A ranker was built for this
list and retired for scoring at chance, so the order is the one VPS answers in and the
choice is always a person's.
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import run, ui

from common.i18n import t
from console import candidates, offload, verbs

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
    with ui.dialog().props("persistent") as dialog, \
            ui.card().classes("console-confirm console-picker-dialog"):
        ui.label(t("console.vps_match.match_game_vps")).classes("console-confirm-title")
        if place:
            ui.label(place).classes("console-help")
        ui.label(t("console.vps_match.nothing_ranks_results_pick")) \
            .classes("console-help")
        field = ui.input(value=_seed(game)) \
            .props("dense autofocus clearable").classes("console-edit-field w-full")
        found = ui.column().classes("w-full gap-0 console-source-list")

        async def look() -> None:
            said = str(field.value or "").strip()
            rows = await offload.io(library.vps_search, said, 40) if said else []
            found.clear()
            with found:
                if not said:
                    ui.label(t("console.vps_match.type_name_maker_year")).classes("console-help")
                    return
                if not rows:
                    ui.label(t("console.vps_match.nothing_vps_matches", said=(said))) \
                        .classes("console-help")
                    return
                for row in rows:
                    _match_row(row, dialog)

        field.on("keydown.enter", look)
        ui.button(t("console.vps_match.search"), icon=verbs.SEARCH,
                on_click=look).props("flat dense no-caps size=sm") \
            .classes("console-action")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button(t("console.vps_match.clear_match"),
                icon=verbs.UNMATCH, on_click=lambda: dialog.submit(CLEARED)) \
                .props("flat no-caps")
            if walking:
                ui.button(t("console.vps_match.skip"),
                    icon=verbs.SKIP, on_click=lambda: dialog.submit(CANCELLED)) \
                    .props("flat no-caps")
                ui.button(t("console.vps_match.stop"),
                    icon=verbs.STOP, on_click=lambda: dialog.submit(STOPPED)) \
                    .props("flat no-caps")
            else:
                ui.button(t("word.cancel"), icon=verbs.CANCEL,
                        on_click=lambda: dialog.submit(CANCELLED)) \
                    .props("flat no-caps")
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
                      glyph="videogame_asset")
