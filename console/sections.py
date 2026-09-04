"""Strawman sections, built to be argued with.

Overview and Extensions exist here to show how the shell holds together, not as
finished pages. Where a page could use real library data it does -
a mock number proves nothing, and the checks below are the validator registry in
embryo: each one is a name, a sentence a person can read, and a predicate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from common.media_specs import media_label_map
from console.data import Library

# name, one-line description, predicate over (game, media entries).
#
# Deliberately shaped the way a real registry would be, so that promoting this is a
# matter of moving it and adding config rather than a rewrite. The description is not
# decoration: it is what the row's finding says, and writing it forces the check to be
# about something a person can act on.
CHECKS: tuple[tuple[str, str, str, Callable[[dict, dict, dict], bool]], ...] = (
    ("rom_missing", "Declared ROM is not installed",
     "The table will not boot; PinMAME has nothing to load.",
     lambda g, m, x: bool(x.get("rom_missing"))),
    ("no_playfield", "No playfield image",
     "The frontend has nothing to show for this game on the playfield screen.",
     lambda g, m, x: not m.get("playfield", {}).get("present")),
    ("no_backglass", "No backglass image",
     "A second screen will sit empty while this game is selected.",
     lambda g, m, x: not m.get("backglass", {}).get("present")),
    ("borrowed_wheel", "Wheel is standing in for something else",
     "A fallback is being used, so the wheel looks fine and is still missing.",
     lambda g, m, x: str(m.get("wheel", {}).get("via") or "").startswith("fallback:")),
    ("no_media", "No media at all",
     "Nothing resolved for any kind. Usually a folder that was never populated.",
     lambda g, m, x: not any(e.get("present") for e in m.values())),
    ("no_year", "No year recorded",
     "Sorting and filtering by year will place this game arbitrarily.",
     lambda g, m, x: not g.get("year")),
)


def rollups(library: Library) -> dict[str, dict[str, Any]]:
    """Per-game facts a check needs that the game payload does not carry.

    Whether a rom is installed is resolved per table, because two builds of one machine
    can declare different ones. A game reads as missing a rom when any of its tables
    declares one that PinMAME's audit says is not there.

    `rom_installed` is three-valued and only `False` counts. `None` is "we could not
    tell" - the audit needs a configured VPX binary, and the name match alone cannot
    see a clone set's parent zip. Treating not-known as missing would report a whole
    library as broken on any machine without VPX.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in library.table_rows():
        fact = out.setdefault(str(row.get("game_id") or ""), {"rom_missing": False})
        if row.get("rom_installed") is False:
            fact["rom_missing"] = True
    return out


def findings(library: Library) -> dict[str, list[dict[str, Any]]]:
    """Run every check over the library. Keyed by check, so a section can show counts."""
    out: dict[str, list[dict[str, Any]]] = {key: [] for key, _, _, _ in CHECKS}
    extra = rollups(library)
    for game in library.games:
        entries = library.media.get(game["id"], {})
        facts = extra.get(game["id"], {})
        for key, _, _, predicate in CHECKS:
            try:
                if predicate(game, entries, facts):
                    out[key].append(game)
            except Exception:
                # A check that throws is a broken check, not a broken library. It
                # reports nothing rather than taking the page down with it.
                continue
    return out


def _card(title: str):
    card = ui.element("div").classes("console-card")
    with card:
        ui.label(title).classes("console-card-title")
    return card


def _bar(fraction: float) -> None:
    with ui.element("div").classes("console-bar w-full"):
        ui.element("div").style(f"width:{max(0.0, min(1.0, fraction)) * 100:.0f}%")


# --- Overview --------------------------------------------------------------------

def overview(library: Library, registry: list[dict], discovery: dict,
             go: Callable[[str], None]) -> None:
    found = findings(library)
    total_slots = sum(len(entries) for entries in library.media.values())
    present = sum(1 for entries in library.media.values()
                  for entry in entries.values() if entry.get("present"))
    open_findings = sum(len(games) for games in found.values())

    with ui.row().classes("w-full gap-4 no-wrap"):
        with _card("Library"):
            ui.label(str(len(library.games))).classes("console-kpi")
            ui.label("games").classes("text-xs opacity-60")
        with _card("Media coverage"):
            ui.label(f"{(present / total_slots * 100 if total_slots else 0):.0f}%") \
                .classes("console-kpi")
            _bar(present / total_slots if total_slots else 0)
            ui.label(f"{present} of {total_slots} slots").classes("text-xs opacity-60")
        with _card("Needs attention"):
            ui.label(str(open_findings)).classes("console-kpi")
            ui.label("findings across the library").classes("text-xs opacity-60")
        with _card("Devices"):
            ui.label(str(len(registry))).classes("console-kpi")
            ui.label("known to this install").classes("text-xs opacity-60")
        with _card("This build"):
            ui.label(str(discovery.get("app_version") or "?")).classes("console-kpi")
            ui.label("no update endpoint yet").classes("text-xs opacity-60")

    ui.label("Coverage by kind").classes("console-group mt-4")
    with ui.element("div").classes("console-card w-full"):
        # A filter says which games lack a topper. Nothing in a grid says "you have no
        # toppers at all" without filtering twenty kinds one at a time, which is the
        # one thing a rollup does that a lens cannot.
        kept = library.kept_kinds()["media"]
        counts = [(kind, sum(1 for entries in library.media.values()
                             if entries.get(kind, {}).get("present")))
                  for kind in library.kinds() if kind in kept]
        for kind, held in sorted(counts, key=lambda item: item[1]):
            with ui.row().classes("items-center gap-3 w-full no-wrap py-1"):
                ui.label(media_label_map().get(kind, kind)) \
                    .classes("console-setting w-40 shrink-0")
                with ui.element("div").classes("grow min-w-0"):
                    _bar(held / len(library.games) if library.games else 0)
                ui.label(f"{held} of {len(library.games)}") \
                    .classes("text-xs opacity-60 shrink-0")

    ui.label("What needs attention").classes("console-group mt-4")
    with ui.element("div").classes("console-card w-full"):
        for key, name, description, _ in CHECKS:
            games = found[key]
            with ui.row().classes("items-center gap-3 w-full no-wrap py-1"):
                ui.icon("error" if games else "check_circle", size="18px") \
                    .classes("text-warning" if games else "text-positive")
                with ui.column().classes("gap-0 grow min-w-0"):
                    ui.label(name).classes("console-setting")
                    # The sentence is the finding. Without it a count is a puzzle.
                    ui.label(description).classes("console-help")
                ui.label(f"{len(games)}").classes("text-sm opacity-70 shrink-0")
                ui.button("Show", on_click=lambda k=key: go("games")) \
                    .props("flat dense no-caps size=sm").classes("shrink-0") \
                    .set_enabled(bool(games))


# --- Extensions ------------------------------------------------------------------

def extensions(registry: list[dict]) -> None:
    ui.label("An extension runs where its feature lives. Where it runs is a "
             "property of the extension, not a setting.").classes("console-help mb-3")
    with ui.element("div").classes("console-card w-full"):
        ui.label("Nothing installed").classes("console-setting")
        ui.label("Install one from a repository, or drop a package here. The list will "
                 "show what it declares and which devices it reached.") \
            .classes("console-help")
