"""Strawman sections, built to be argued with.

Overview, Media, Collections and Extensions exist here to show how the shell holds
together, not as finished pages. Where a page could use real library data it does -
a mock number proves nothing, and the checks below are the validator registry in
embryo: each one is a name, a sentence a person can read, and a predicate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from hubui import mediamap
from hubui.data import Library

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
    card = ui.element("div").classes("hub-card")
    with card:
        ui.label(title).classes("hub-card-title")
    return card


def _bar(fraction: float) -> None:
    with ui.element("div").classes("hub-bar w-full"):
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
            ui.label(str(len(library.games))).classes("hub-kpi")
            ui.label("games").classes("text-xs opacity-60")
        with _card("Media coverage"):
            ui.label(f"{(present / total_slots * 100 if total_slots else 0):.0f}%") \
                .classes("hub-kpi")
            _bar(present / total_slots if total_slots else 0)
            ui.label(f"{present} of {total_slots} slots").classes("text-xs opacity-60")
        with _card("Needs attention"):
            ui.label(str(open_findings)).classes("hub-kpi")
            ui.label("findings across the library").classes("text-xs opacity-60")
        with _card("Players"):
            ui.label(str(len(registry))).classes("hub-kpi")
            ui.label("devices known").classes("text-xs opacity-60")
        with _card("This build"):
            ui.label(str(discovery.get("app_version") or "?")).classes("hub-kpi")
            ui.label("no update endpoint yet").classes("text-xs opacity-60")

    ui.label("What needs attention").classes("hub-group mt-4")
    with ui.element("div").classes("hub-card w-full"):
        for key, name, description, _ in CHECKS:
            games = found[key]
            with ui.row().classes("items-center gap-3 w-full no-wrap py-1"):
                ui.icon("error" if games else "check_circle", size="18px") \
                    .classes("text-warning" if games else "text-positive")
                with ui.column().classes("gap-0 grow min-w-0"):
                    ui.label(name).classes("hub-setting")
                    # The sentence is the finding. Without it a count is a puzzle.
                    ui.label(description).classes("hub-help")
                ui.label(f"{len(games)}").classes("text-sm opacity-70 shrink-0")
                ui.button("Show", on_click=lambda k=key: go("games")) \
                    .props("flat dense no-caps size=sm").classes("shrink-0") \
                    .set_enabled(bool(games))


# --- Media -----------------------------------------------------------------------

# Strawman only. The real thing reads the registry that the asset search would use.
SOURCES = (
    ("VPinMediaDB", "github.com/superhac/vpinmediadb", True, True),
    ("Local uploads", "this install", True, True),
)


def media(library: Library, go_game: Callable[[str], None]) -> None:
    """Coverage, and the work that follows from it.

    A bar chart of what is missing is a report, and a report is not a tool. Picking a
    kind here produces the list of games missing it, which is the thing you would
    otherwise assemble by hand before you could do anything about it.
    """
    kinds: list[tuple[str, int, int, list[dict]]] = []
    for kind in library.kinds():
        ok = borrowed = 0
        gap: list[dict] = []
        for game in library.games:
            state = mediamap._state(library.media[game["id"]].get(kind, {}))
            if state == "present":
                ok += 1
            elif state == "borrowed":
                borrowed += 1
            else:
                gap.append(game)
        kinds.append((kind, ok, borrowed, gap))
    kinds.sort(key=lambda k: -len(k[3]))
    holder: dict[str, Any] = {}
    rows_by_kind: dict[str, Any] = {}
    chosen = {"kind": kinds[0][0] if kinds else None}

    def show(kind: str) -> None:
        chosen["kind"] = kind
        target = holder.get("work")
        if target is None:
            return
        target.clear()
        _, ok, borrowed, gap = next(k for k in kinds if k[0] == kind)
        with target:
            ui.label(mediamap.LABELS.get(kind, kind)).classes("hub-card-title")
            ui.label(f"{len(gap)} games have no {mediamap.LABELS.get(kind, kind).lower()}. "
                     f"{ok} resolved" + (f", {borrowed} borrowed." if borrowed else "."))\
                .classes("hub-help mb-2")
            with ui.row().classes("gap-2 mb-3"):
                ui.button(f"Search sources for {len(gap)}", icon="travel_explore") \
                    .props("dense no-caps unelevated").set_enabled(False)
                ui.button("Show in Games", icon="list").props("flat dense no-caps") \
                    .set_enabled(False)
            if not gap:
                ui.label("Nothing missing. Every game resolved this kind.") \
                    .classes("hub-help")
            for game in gap[:60]:
                ui.label(game.get("name") or "").classes("text-xs opacity-80 truncate") \
                    .on("click", lambda g=game: go_game(g["id"])) \
                    .classes("cursor-pointer")
            if len(gap) > 60:
                ui.label(f"...and {len(gap) - 60} more").classes("text-xs opacity-50")

    with ui.row().classes("w-full gap-4 no-wrap items-start"):
        with ui.element("div").classes("hub-card shrink-0").style("width:330px"):
            ui.label("Gaps by kind").classes("hub-card-title")
            ui.label("Worst first. Pick one to see which games it affects.") \
                .classes("hub-help mb-2")
            for kind, ok, borrowed, gap in kinds:
                total = ok + borrowed + len(gap)
                row = ui.element("div").classes("hub-index-item w-full")
                if kind == chosen["kind"]:
                    row.classes(add="hub-index-on")

                def pick(k=kind) -> None:
                    for other in rows_by_kind.values():
                        other.classes(remove="hub-index-on")
                    rows_by_kind[k].classes(add="hub-index-on")
                    show(k)

                row.on("click", pick)
                with row:
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        ui.label(mediamap.LABELS.get(kind, kind)) \
                            .classes("text-xs grow min-w-0 truncate")
                        ui.label(str(len(gap))).classes("text-xs opacity-60 shrink-0")
                    _bar(ok / total if total else 0)
                rows_by_kind[kind] = row
        with ui.element("div").classes("hub-card grow min-w-0"):
            holder["work"] = ui.column().classes("w-full gap-0")

    ui.label("Sources").classes("hub-group mt-4")
    with ui.element("div").classes("hub-card w-full"):
        ui.label("Where the asset search looks. Results carry the source they came from, "
                 "so a file can always be traced back.").classes("hub-help mb-2")
        for name, location, enabled, provided in SOURCES:
            with ui.row().classes("items-center gap-3 w-full no-wrap py-1"):
                ui.checkbox(value=enabled).props("dense")
                with ui.column().classes("gap-0 grow min-w-0"):
                    ui.label(name).classes("hub-setting")
                    ui.label(location).classes("hub-help")
                if provided:
                    ui.badge("built in").props("outline")
        ui.button("Add source", icon="add").props("flat dense no-caps").classes("mt-2")

    ui.label("Recorder").classes("hub-group mt-4")
    with ui.element("div").classes("hub-card w-full"):
        ui.label("Capture playfield, backglass and score-display media from a player "
                 "while it runs the game, for the kinds nobody has published.") \
            .classes("hub-help")
        ui.label("Not built. Gated on what VPX Standalone can capture on Linux and "
                 "macOS - a Windows-only path is the wrong shape for this platform.") \
            .classes("hub-help mt-1 text-warning")
    if chosen["kind"]:
        show(chosen["kind"])


# --- Collections -----------------------------------------------------------------

AXES = ("manufacturer", "game_type", "year")


def collections(library: Library) -> None:
    rows = library.game_rows()
    state = {"axis": "manufacturer", "value": ""}
    # Filled once the Members card exists. The controls are built first and have to
    # close over something, so the container arrives by reference rather than the
    # controls being built twice.
    holder: dict[str, Any] = {}

    def resolve() -> None:
        """Rule and result, side by side and live.

        The count is the point: a filter whose effect you cannot see is a filter you
        have to run to understand, which is the whole complaint about writing SQL.
        """
        target = holder.get("result")
        if target is None:
            return
        target.clear()
        value = (state["value"] or "").strip().lower()
        hits = [row for row in rows
                if value and value in str(row.get(state["axis"], "")).lower()]
        with target:
            if not value:
                ui.label("Pick an axis and type a value.").classes("hub-help")
                return
            ui.label(f"{len(hits)} of {len(rows)} games").classes("hub-card-title mb-1")
            for row in hits[:18]:
                ui.label(row["name"]).classes("text-xs opacity-80 truncate")
            if len(hits) > 18:
                ui.label(f"...and {len(hits) - 18} more").classes("text-xs opacity-50")

    with ui.row().classes("w-full gap-4 no-wrap items-start"):
        with ui.element("div").classes("hub-card shrink-0").style("width:340px"):
            ui.label("Rule").classes("hub-card-title")
            ui.label("A filter collection is built from the library, never from another "
                     "collection.").classes("hub-help mb-2")
            ui.select(list(AXES), value=state["axis"],
                      on_change=lambda e: (state.update(axis=e.value), resolve())) \
                .props("dense outlined").classes("w-full")
            ui.input("contains",
                     on_change=lambda e: (state.update(value=e.value), resolve())) \
                .props("dense outlined").classes("w-full")
        with ui.element("div").classes("hub-card grow min-w-0"):
            ui.label("Members").classes("hub-card-title")
            holder["result"] = ui.column().classes("w-full gap-0 pt-1")
    resolve()


# --- Extensions ------------------------------------------------------------------

def extensions(registry: list[dict]) -> None:
    ui.label("An extension runs either on the hub or on one device. Where it runs is a "
             "property of the extension, not a setting.").classes("hub-help mb-3")
    with ui.element("div").classes("hub-card w-full"):
        ui.label("Nothing installed").classes("hub-setting")
        ui.label("Install one from a repository, or drop a package here. The list will "
                 "show what it declares and which devices it reached.") \
            .classes("hub-help")
