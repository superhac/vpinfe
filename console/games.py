"""The games grid: one row per game, with views over the same rows."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any

from nicegui import run, ui

from common.games import asset_registry
from common.i18n import t
from common.labels import humanize
from common.media_specs import media_label_map
from console import (
    art,
    art_fill,
    collection_adds,
    confirm,
    deeplink,
    game_tables,
    grid,
    media_ownership,
    mediaview,
    offload,
    panel,
    renderers,
    row_drag,
    send_to_device,
    stars,
    table_features,
    tag_chips,
    verbs,
    views,
    vps_match,
    workbench,
)
from console import dialog as frame
from console.api import ApiClient

logger = logging.getLogger("vpinfe.console.games")

SCOPE = "console.games.columns"

# The groups are the grain distinction, surfaced in the column picker: what
# the row *is*, what it rolls up, and what it has. Media sits last because it is most
# of the list and least of the use - and last is where it already was, so the grouping
# names a seam that was there rather than moving anything.
_GAME = "word.game"
_ASSETS = "console.view.assets"
_MEDIA = "console.view.media"
_FEATURES_VIEW = "console.game_tables.features"

# What the games resource calls an asset is not always what `asset_registry` calls it -
# `settings` is the table INI, and one `alt_color` covers both Serum and VNI. Named
# here because the two vocabularies have not been reconciled, and a column headed
# "Settings" says nothing about which file it means.
# Only where this surface has to differ from the registry's own label. Everything
# else asks `asset_registry`, which is where a kind's acronyms are cased once.
# `alt_color` and `alt_sound` are here because the games resource still names them
# its own way - one `alt_color` covering the registry's Serum and VNI.
_ASSET_LABELS = {
    "alt_color": "console.games.alt_color",
    "alt_sound": "console.games.altsound",
    # The `.directb2s`, which media also calls a backglass - one is the file that
    # drives the second screen, the other is a picture of it. A column header has no
    # group heading beside it, so the two cannot both be "Backglass".
    "backglass": "console.games.b2s",
}


def _asset_label(key: str) -> str:
    """The registry's word for a kind, then this surface's override, then humanize."""
    if key in _ASSET_LABELS:
        return t(_ASSET_LABELS[key])
    try:
        return asset_registry.spec_for(key).label
    except KeyError:
        return humanize(key)
# Five stars, filled to the value, and they are the control as well as the picture -
# which is what lets the row menu drop its "Rate" item. A rating is one number a person
# reads at a glance and sets in one click; a menu to open a dialog to pick a number is
# three acts for that.
#
# Clicking the star a rating already stands on clears it. That is how every star widget
# behaves, and the alternative is a sixth control on a column this narrow.
_RATING_CHOICES = ([{"value": 0, "label": t("console.games.unrated")}]
                   + [{"value": n, "label": "", "mark": f"{stars.STAR} {stars.LIT}",
                       "repeat": n} for n in range(1, 6)])


def _two(words: tuple[str, str]) -> list[dict[str, Any]]:
    """A fact's own pair as the funnel's two choices, true first - which is the notable
    state, because that is the direction every one of these columns reads."""
    return [{"value": True, "label": words[0]}, {"value": False, "label": words[1]}]


# AG Grid infers `cellDataType: boolean` from the data and draws a checkbox for it,
# and that renderer wins over any formatter - a boolean column meant to print a word or
# a tick comes out blank without this. Every boolean column here turns it off.
_NO_CHECKBOX: dict[str, Any] = {":cellRenderer": None}

_TICK = {
    ":valueFormatter": "params => params.value ? '\u2713' : ''",
    "cellClass": "console-tick",
    **_NO_CHECKBOX,
    # Yes and No, because the column's own header is the noun: "Hidden" answers yes or
    # no, and a pair naming the thing again would read as "Hidden: Present". A column
    # whose subject has better words passes its own.
    **grid.choice_filter([{"value": True, "label": t("word.yes")},
                          {"value": False, "label": t("console.games.no")}]),
}


# Delegated once, in the capture phase for the same reason the enlarge is: the cell's
# own click would move the focused row, and rating a row you can see is not a request
# to go and look at it.
COLUMNS = [
    grid.identifier("name", t(_GAME), 280, pinned="left", group=t(_GAME),
                subtitle="said",
                help=t("console.games.game_library_names.help"),
                **row_drag.source(row_drag.GAMES)),
    # Always, including 1: it is the only thing saying the row collapses its tables,
    # and it qualifies everything to its right. "Table Count" rather
    # than "Tables", which read as the tables themselves - this is a number about the
    # game, and it belongs with the game's other facts.
    grid.column("table_count", t("word.table_count"), type="numericColumn", group=t(_GAME),
                help=t("console.games.how_many_vpx_files.help")),
    grid.column("hidden", game_tables.FRONTEND, group=t(_GAME),
                help=t("console.games.hidden_game.help"),
                **{":valueFormatter":
                   "params => params.value ? "
                   + json.dumps(game_tables.HIDDEN_WORDS[0]) + " : ''",
                   **grid.choice_filter(_two(game_tables.HIDDEN_WORDS), formatted=True)},
                **renderers.drawable("state", states={True: {
                    "label": game_tables.HIDDEN_WORDS[0],
                    "why": t("console.game_tables.hidden_game.help"),
                    "chip": "console-chip-warn"}})),
    grid.column("manufacturer", t("word.manufacturer"), group=t(_GAME),
                help=t("help.who_made_it")),
    grid.column("year", t("word.year"), group=t(_GAME),
                help=t("help.year_released")),
    grid.column("game_type", t("console.games.type"), group=t(_GAME),
                help=t("console.games.solid_state_electro_mechanical.help")),
    # Qualified for the reason Game Rating is: an install has a *frontend* theme and will
    # have a Console one, so "Themes" in a column header is three things one screen apart.
    # The panel says "Themes" plainly, because a group headed Machine has said which.
    grid.list_column("themes", t("console.games.game_themes"), 200, group=t(_GAME),
                     help=t("console.games.what_game_about.help")),
    # The word only where it is missing, and a blank cell everywhere else: most of a
    # library is matched, so a mark on every row says nothing and the few that are not
    # are the whole point of the column. It sits beside the catalog facts because it
    # explains them - a game with no manufacturer, year or themes is usually a game the
    # catalog has never been asked about.
    grid.column("vps_unmatched", t("console.games.vps_match"), group=t(_GAME),
                help=t("console.games.blank_where_game_matched.help"),
                **_NO_CHECKBOX,
                **{":valueFormatter":
                   "params => params.value ? "
                   + json.dumps(game_tables.VPS_WORDS[0]) + " : ''",
                   **grid.choice_filter(_two(game_tables.VPS_WORDS),
                                        formatted=True)}),
    grid.column("vps_matched_by", t("console.games.how_matched"), 160, group=t(_GAME),
                help=t("console.games.how_matched.help"),
                **grid.choice_filter([{"value": token, "label": word} for token, word
                                      in game_tables.HOW_MATCHED.items()])),
    # No ROM or Version here: ROM is an asset (`asset_registry`), Version has no
    # game-level meaning, and both were the default table's shown as the game's.
    # Named for whose rating it is, because the tables grid has one too and "Rating"
    # in two places invites the reader to assume they are the same number.
    grid.column("rating", t("console.games.game_rating"), group=t(_GAME),
                help=t("console.games.rating_game_0_5.help"),
                cellClass="console-stars-cell",
                **{**grid.choice_filter(_RATING_CHOICES),
                   ":cellRenderer": stars.renderer("game")}),
    grid.list_column("tags", t("console.workbench.tags"), 200, group=t(_GAME),
                     help=t("console.games.tags.help"), looks=renderers.TAG_LOOKS),
    grid.list_column("collections", t("console.workbench.collections"), 200,
                     group=t(_GAME), help=t("console.games.collections.help"),
                     looks=renderers.COLLECTION_LOOKS),
]

# Presets, not a replacement for choosing columns: a view sets which columns are
# shown, and anything the user changes afterwards is theirs and is what persists.
# Only fields that belong to a game. `rom` and `version` do not: game_repository reads
# them from the default table, so at this grain they report one table's and call them
# the game's. Tables is where that question is answered.
# Which part of a game a view is about, so a row lands there rather than on Details
# and one more click. Only where the view leaves no doubt - the rest open wherever the
# panel was, which is what stepping down a list needs.
VIEW_SECTIONS = {views.builtin_id(_MEDIA): "media"}

# A column that reports a problem, and the panel section that fixes it. Clicking the
# word is the only thing to do with it, so the click lands where it is fixed rather
# than on Details and one more click.
COLUMN_SECTIONS = {"vps_unmatched": "game_details", "hidden": "game_details"}

# The grid on its Unmatched filter, as `state["arriving"]`.
UNMATCHED = {"vps_unmatched": {"values": [True]}}

GAME_VIEWS: dict[str, list[str] | views.Preset] = {
    # Named for the workbench group it matches: a view and a panel
    # group about the same facts carry the same word, so crossing between the grid and
    # the panel is not a translation.
    "console.view.game": views.Preset(
        columns=("name", "table_count", "hidden", "manufacturer", "year", "game_type",
                 "themes", "vps_unmatched", "rating", "tags", "collections"),
        help=t("console.view.game.help")),
    # Media and Assets are built from what the library reports it has, so both are
    # filled at render time. Two views, not one: they answer different questions - what
    # a game looks like, and what it needs to play as intended - and a matrix that mixes
    # them is neither.
    _MEDIA: views.Preset(help=t("console.view.game_media.help")),
    _ASSETS: views.Preset(help=t("console.view.game_assets.help")),
}

_ALL = [definition["field"] for definition in COLUMNS]


# What one row is: three grains of the library the user owns - the folder, the
# launchable file inside it, and the asset that resolved for it. Everything here has to
# be something the workbench can answer for, which is what keeps a catalog out.

# An asset column asks whether the game has one, and "Missing" is the word the media
# vocabulary already uses for the same absence.
_HAS_CHOICES = [{"value": True, "label": t("word.present")},
                {"value": False, "label": t("console.games.missing")}]


def asset_columns(keys: list[str]) -> list[dict[str, Any]]:
    """One column per asset kind, availability only.

    A group rather than a single count. What a reader wants is which of them a game
    has, and a number cannot say that.
    """
    labels = {key: _asset_label(key) for key in keys}
    width = max((grid.header_width(label) for label in labels.values()), default=92)
    return [grid.column(f"asset_{key}", label, width, group=t(_ASSETS),
                        help=t("help.asset_kind", label=(label)),
                        cellStyle={"textAlign": "center"},
                        **{**_TICK, **grid.choice_filter(_HAS_CHOICES)})
            for key, label in sorted(labels.items(), key=lambda kv: kv[1].lower())]


# What the funnel offers on a media column, in the legend's own words and marks. The
# value is what the cell holds - "" for missing, which is a blank cell and so a choice
# like any other rather than the one state the filter cannot express.
#
# And no mark on Missing: the cell draws nothing for it, so a glyph here would offer a
# mark the grid never puts on screen. Same reason the legend leaves it out.
_STATE_CHOICES = [
    {"value": "" if key == media_ownership.MISSING
     else media_ownership.tier_for(key).noun,
     "label": t(media_ownership.tier_for(key).noun),
     "mark": ("" if key == media_ownership.MISSING
              else f"console-mark {media_ownership.tier_for(key).mark}")}
    for key in media_ownership.STATES
]


# Delegated and installed once: NiceGUI strips inline handlers off raw HTML, and a
# renderer runs again on every scroll. The click is taken in the *capture* phase,
# because AG Grid's handler sits between the cell and the document - stopping the event
# on the way back up is too late, and enlarging would also pick the slot.
_CELL_MEDIA = """
if (!window.__hubCellMedia) {
  window.__hubCellMedia = true;
  const clip = (el) => el && el.closest
    ? el.closest('.console-media-cell')?.querySelector('video') : null;
  document.addEventListener('mouseover', (e) => {
    const v = clip(e.target);
    if (v && v.paused) v.play().catch(() => {});
  });
  document.addEventListener('mouseout', (e) => {
    const v = clip(e.target);
    if (!v) return;
    const cell = e.target.closest('.console-media-cell');
    if (e.relatedTarget && cell && cell.contains(e.relatedTarget)) return;
    v.pause();
    v.currentTime = 0.1;
  });
  document.addEventListener('click', (e) => {
    const zoom = e.target.closest && e.target.closest('.console-cell-zoom');
    if (!zoom) return;
    e.stopPropagation();
    emitEvent('hub_media_zoom', {game: zoom.dataset.game, kind: zoom.dataset.kind});
  }, true);
}
"""


# Columns whose values are the catalog's rather than a state this code defines. Every
# other choice filter here lists what the code owns - Present/Missing, Matched/Unmatched -
# and a fixed list for these would go stale the day VPS gains a value.
_DERIVED_FACETS = ("manufacturer", "game_type")

# Past this many distinct values a checkbox list stops being a list of choices and
# becomes a haystack, whatever is typed at it. The funnel's own text box is the better
# tool there. Measured over 148 games: 3 types, 17 manufacturers - and 50 years and 74
# themes, which are why neither of those is a derived facet.
_FACET_CEILING = 60


def with_derived_facets(columns: list[dict[str, Any]],
                        rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give the open-valued columns a facet built from what the library actually holds.

    Copies rather than edits: `COLUMNS` is a module constant and a filter injected into
    it would outlive the render that wanted it.
    """
    built = []
    for definition in columns:
        field = str(definition.get("field") or "")
        if field not in _DERIVED_FACETS:
            built.append(definition)
            continue
        seen = sorted({str(row.get(field) or "").strip() for row in rows} - {""},
                      key=str.casefold)
        if not seen or len(seen) > _FACET_CEILING:
            built.append(definition)
            continue
        choices = [{"value": value, "label": value} for value in seen]
        # A blank is a value like any other here, and the component is written for it.
        if any(not str(row.get(field) or "").strip() for row in rows):
            choices.append({"value": "", "label": t("console.games.not_recorded")})
        built.append(definition | grid.choice_filter(choices))
    return built


def media_columns(kinds: list[str]) -> list[dict[str, Any]]:
    """One width for every kind, set by the widest line any of them needs.

    A ragged set of widths reads as noise in a matrix whose cells are all one glyph -
    the columns should scan as a grid, so they are sized together rather than each to
    its own header.
    """
    # The registry's own label, never the key. `media_specs` carries the name a person
    # reads for each kind - acronyms already cased - and deriving one from the key
    # instead is what put "real dmd color" in the column picker.
    labels = media_label_map()
    # Ordered by what is shown, not by the key behind it. Sorting on the key put FSS
    # between Playfield and Playfield Video, and DMD after Real DMD Color - a list that
    # looks unsorted because it is sorted on something the reader cannot see.
    headers = {kind: grid.two_line(labels.get(kind) or humanize(kind))
               for kind in sorted(kinds, key=lambda k: (labels.get(k) or k).lower())}
    width = max((grid.header_width(header) for header in headers.values()), default=92)
    return [grid.column(f"media_{kind}", header, width,
                        cellClass="console-media-cell", group=t(_MEDIA),
                        help=t("help.media_kind", label=(header)),
                        **grid.choice_filter(_STATE_CHOICES),
                        **renderers.drawable("mark", "picture"))
            for kind, header in headers.items()]


def auto_match_outcome(result: dict[str, Any]) -> tuple[str, bool]:
    """What Auto-match says when it is done, and whether any match moved."""
    moved = int(result.get("changed") or 0)
    waiting = int(result.get("unmatched") or 0)
    if moved and waiting:
        return t("console.games.auto_matched_some",
                 matched=t("console.games.auto_matched", count=moved),
                 waiting=t("console.games.still_need_match", count=waiting)), True
    if moved:
        return t("console.games.auto_matched", count=moved), True
    if waiting:
        return t("console.games.still_need_match", count=waiting), False
    return t("console.vps_match.nothing_changed"), False


async def _rate(games: list[dict[str, Any]]) -> None:
    """Set a rating on every game passed in.

    The API rates one game at a time (`PUT /games/{id}/rating`), so this loops here
    rather than calling a bulk endpoint that does not exist.
    """
    from nicegui import run
    if not games:
        return

    async def apply(value: int) -> None:
        client = ApiClient()
        for game in games:
            await run.io_bound(client.rate, game["id"], value)
        box.close()
        ui.notify(t("console.games.rated_game_s", count=len(games), value=value),
                  type="positive")

    with frame.opened(t("console.games.rate_game_s", count=len(games))) as box:
        with ui.row().classes("px-3"):
            stars.draw(0, lambda n: asyncio.create_task(apply(n)))()
        with frame.footer():
            frame.cancel(box.close)
    box.open()


async def _launch(games: list[dict[str, Any]]) -> None:
    """Launch one game. Deliberately refuses a multi-row selection.

    Launching is device-resident and starts something on a machine; doing it for
    several rows at once has no sensible meaning, so it is refused rather than looped.
    """
    if len(games) != 1:
        ui.notify(t("console.games.select_single_game_launch"), type="warning")
        return
    await offload.io(ApiClient().launch, games[0]["id"])
    ui.notify(t("console.games.launching", get=(games[0].get('name'))), type="positive")


def media_zoomed(state: dict[str, Any], event: Any) -> Any:
    """A media cell's zoom, answered by the grid drawn last."""
    zoom = state.get("media_zoom")
    return zoom(event) if zoom else None


def rated(state: dict[str, Any], event: Any) -> Any:
    """A star clicked in a grid, written by the grid drawn last - Games or Tables."""
    rate = state.get("rate")
    return rate(event) if rate else None


def build(rows: list[dict[str, Any]], kinds: list[str], library: Any,
          on_select: Callable[[dict | None], Any],
          state: dict[str, Any] | None = None,
          rerender: Callable[[], None] | None = None,
          rescan: Callable[[], Any] | None = None) -> None:
    state = state if state is not None else {}
    tag_chips.install(library.tag_looks())
    renderers.install_collection_looks(library.smart_collections())
    columns = with_derived_facets(COLUMNS, rows) \
        + asset_columns(library.asset_keys()) + media_columns(kinds)
    all_fields = [definition["field"] for definition in columns]
    selected: list[dict[str, Any]] = []
    context_row: list[dict[str, Any]] = []

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                                  "console-panel console-grid-bar"):
        bar = panel.grid_bar()
        # The media preset is the library's own kinds, so it is only knowable here.
        presets = {**GAME_VIEWS,
                   _MEDIA: views.Preset(
                       columns=("name", *[f"media_{kind}" for kind in kinds]),
                       help=t("console.view.game_media.help")),
                   _ASSETS: views.Preset(
                       columns=("name",
                                *[f"asset_{key}" for key in library.asset_keys()]),
                       help=t("console.view.game_assets.help"))}
        def annotate() -> None:
            """The key to the marks, on the line that says what the view is for.

            Read from the vocabulary rather than restated here, and each entry carries
            its own explanation on hover - a legend that names a state without saying
            what it means is half a legend.
            """
            with ui.row().classes("items-center gap-3 no-wrap shrink-0 text-xs "
                                  "opacity-60 console-tier-key") as legend:
                for key in media_ownership.LEGEND:
                    tier = media_ownership.tier_for(key)
                    with ui.row().classes("items-center gap-1 no-wrap") \
                            .tooltip(t(tier.why)):
                        ui.element("span").classes(f"console-mark {tier.mark}")
                        ui.label(t(tier.noun))
            legend.bind_visibility_from(view_picker, "value",
                                        lambda value: value == views.builtin_id(_MEDIA))

        narrowed = str(state.get("collection") or "")
        # Taken once: a filter a link asked for is not put back on every redraw after.
        arriving = state.pop("arriving", None) \
            or ({"collections": {"values": [narrowed]}} if narrowed else None)
        wire_views, view_picker, showing, describe = view_control(
            library, SCOPE, presets, all_fields, columns, bar=bar, annotate=annotate,
            arriving=arriving)
        describe()
        with bar.top, panel.bar_end():
            search = panel.search(t("console.games.search_games"))
        with bar.bottom, panel.bar_end():
            # The selection count sits with the total: it is the same fact - how much am I
            # looking at - and it costs no vertical space of its own.
            count = ui.label(t("console.games.games", len=(len(rows)))) \
                .classes("text-xs console-label")
            actions = ui.button(icon=verbs.MORE).props("flat round dense") \
                .tooltip(t("console.games.actions_selected_games"))
            with actions:
                bulk_menu = ui.menu().props("no-parent-event")
            actions.set_visibility(False)
            if rescan is not None:
                panel.refresh(rescan, t("console.games.read_library_disk_pick"))

    shown: dict[str, int] = {"rows": len(rows)}

    def said() -> str:
        if selected:
            return grid.selection_said(table, len(selected), t(
                "console.games.selected", len=len(selected), len2=shown["rows"]))
        if shown["rows"] != len(rows):
            return t("console.games.games_of", value=shown["rows"], len=len(rows))
        return t("console.games.games", len=len(rows))

    def on_select_rows(rows_selected: list[dict[str, Any]]) -> None:
        selected[:] = rows_selected
        actions.set_visibility(bool(rows_selected))
        count.text = said()

    by_id = {row["id"]: row for row in rows}

    def focused(event: Any) -> Any:
        """The row the keyboard or a click landed on, and the part of it in question.

        A media cell is a question about one slot, so the panel opens there - out of a
        collapsed panel too, because clicking a picture is asking to see it. A view only
        names its section: reopening a panel somebody shut would fight them every row.
        """
        row = by_id.get(grid.focused_row(event))
        column = grid.focused_column(event)
        if row and column.startswith("media_"):
            state["section"] = "media"
            state.setdefault("slot", {"kind": None})["kind"] = column[len("media_"):]
        elif row and state.get("section") != workbench.COLLAPSED:
            section = (COLUMN_SECTIONS.get(column)
                       or VIEW_SECTIONS.get(str(view_picker.value or "")))
            if section:
                state["section"] = section
        return on_select(row)

    def zoom_media(event: Any) -> None:
        """Enlarge the file a cell is showing - the same viewer the media map opens."""
        args = event.args if isinstance(event.args, dict) else {}
        game_id, kind = str(args.get("game") or ""), str(args.get("kind") or "")
        if game_id and kind:
            version = (library.media.get(game_id) or {}).get(kind, {}).get("version")
            mediaview.open_viewer(art.media(game_id, kind, version=version), kind,
                                  media_label_map().get(kind, kind))

    rate_row = stars.rating_handler(rows, by_id, lambda: table, ApiClient)

    grid.on_row_focus(SCOPE, focused)
    state["media_zoom"] = zoom_media
    state["rate"] = rate_row
    ui.run_javascript(_CELL_MEDIA)
    ui.run_javascript(stars.CLICK_JS)

    async def on_context(row: dict | None) -> None:
        # The row menu acts on the row under the cursor, which is not necessarily the
        # selection. Conflating the two is how people act on the wrong thing.
        context_row[:] = [row] if row else []
        known = await collection_adds.read(library, narrowed_to()) if row else None
        _fill_menu(row=row, known=known)

    def narrowed_to() -> str:
        """The collection the grid is filtered to, while it is one."""
        return str(state.get("collection") or "")

    def offer(games: list[dict[str, Any]], subject: str) -> collection_adds.Offer:
        return collection_adds.Offer(
            library, [collection_adds.Row(str(one["id"])) for one in games],
            collection_adds.GAMES, subject,
            then=partial(refresh_games, [str(one["id"]) for one in games]),
            narrowed=narrowed_to())

    async def auto_match(games: list[dict[str, Any]]) -> None:
        ids = [str(one["id"]) for one in games]
        try:
            result = await offload.io(library.auto_match, ids)
        except Exception as exc:  # noqa: BLE001 - said, and the grid is as it was
            ui.notify(t("console.games.could_not_auto_match", exc=exc), type="warning")
            return
        said, moved = auto_match_outcome(result)
        ui.notify(said, type="positive" if moved else "info")
        if moved:
            await refresh_games(ids)
            if state.get("game") in ids:
                answer = on_select(by_id.get(str(state["game"])))
                if inspect.isawaitable(answer):
                    await answer

    async def get_missing_art(games: list[dict[str, Any]]) -> None:
        ids = [str(one["id"]) for one in games]

        async def placed() -> None:
            await run.io_bound(library.reread_media, ids)
            await refresh_games(ids)

        await art_fill.ask(ids, state, placed,
                           name=str(games[0].get("name") or "") if len(games) == 1 else "")

    async def fill_bulk() -> None:
        chosen = grid.selection(table)
        known = await collection_adds.read(library, narrowed_to())
        bulk_menu.clear()
        with bulk_menu:
            panel.menu_entry(t("console.games.rate_selected"), lambda: _rate(chosen))
            # One picker at a time: a person decides every one, and Skip leaves a game
            # exactly as it was.
            panel.menu_entry(t("console.games.match_vps"),
                             lambda: vps_match.walk(library, chosen))
            panel.menu_entry(t("console.games.auto_match"),
                             lambda: auto_match(chosen)) \
                .tooltip(t("console.games.auto_match.help"))
            panel.menu_entry(t("console.art_fill.get_missing"),
                             lambda: get_missing_art(chosen))
            # Where the games you have already picked go. From here rather than only
            # from the device, because starting with the tables and choosing where they
            # land is a different job from managing what a phone holds.
            panel.menu_entry(t("console.games.send_device"),
                             lambda: send_to_device.ask_where(chosen))
            ui.separator()
            collection_adds.draw(offer(chosen, ""), known, bulk_menu.close)
            ui.separator()
            panel.menu_entry(t("word.clear_selection"),
                             lambda: table.run_grid_method("deselectAll"))
        bulk_menu.open()

    actions.on_click(fill_bulk)

    async def on_header_context(col_id: str | None) -> None:
        # Asked of the grid rather than tracked here: the column can also be dragged in
        # and out of the pinned area, and a local flag would then be wrong.
        current: list[dict[str, Any]] = \
            await table.run_grid_method("getColumnState") or []
        entry = next((c for c in current if c.get("colId") == col_id), {})
        _fill_menu(col_id=col_id, pinned=bool(entry.get("pinned")))

    async def hide_column(col_id: str) -> None:
        table.run_grid_method("setColumnsVisible", [col_id], False)

    def _fill_menu(row: dict | None = None, col_id: str | None = None,
                   pinned: bool = False,
                   known: collection_adds.Read | None = None) -> None:
        """One menu, filled for whatever was right-clicked.

        Two menus cannot both hang off the grid wrapper, and the wrapper sees every
        right-click - so one menu, filled from what was under the pointer. Otherwise the
        row menu opens over a header, offering to launch a column.
        """
        context_menu.clear()
        with context_menu:
            if col_id and not col_id.startswith("ag-Grid-"):
                header = next((definition.get("headerName") for definition in columns
                               if definition.get("field") == col_id), col_id)
                ui.item_label(str(header).replace("\n", " ")) \
                    .props("header").classes("console-menu-header")
                ui.separator()
                # One entry that says what it will do, rather than two where one is
                # always a no-op.
                if pinned:
                    ui.menu_item(t("word.unpin"), lambda: grid.pin(table, col_id, None)) \
                        .classes("console-menu-item")
                else:
                    ui.menu_item(t("word.pin_left"),
                                 lambda: grid.pin(table, col_id, "left")) \
                        .classes("console-menu-item")
                ui.menu_item(t("word.hide_column"), lambda: hide_column(col_id)) \
                    .classes("console-menu-item")
            elif row:
                ui.item_label(row.get("name") or "").props("header") \
                    .classes("console-menu-header")
                ui.separator()
                panel.menu_entry(t("console.games.launch"), lambda: _launch(context_row))
                if known is not None:
                    ui.separator()
                    collection_adds.draw(offer([row], str(row.get("name") or "")), known,
                                         context_menu.close)

    # The menu hangs off a wrapper, not off the grid: ui.aggrid's Vue template is a bare
    # <div> with no slot, so a child of it is never rendered and the menu silently does
    # not exist. Anchoring to an element that does render its children is the fix.
    # The wrapper has to carry the flex chain too, not just anchor the menu: as a plain
    # block it collapsed to its content height and the grid inside it never filled.
    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        # No `html_fields` for the media columns: NiceGUI answers that by installing a
        # renderer of its own, and these columns bring theirs. The cell's value is a
        # word now, so a column left to render itself would print it - which is the
        # accident this replaces, not the intent.
        table: ui.aggrid = grid.build(columns, rows, SCOPE, on_select_rows, on_context,
                                      on_header_context, view_of=showing)
        context_menu: ui.context_menu = ui.context_menu()

    async def refresh_game(game_id: str) -> None:
        """Put one game's row back on screen after something changed it.

        A transaction rather than a page rebuild. A rebuild reads as the grid flashing:
        scroll position, focus and the open panel all go, for a write that touched one
        row. `getRowId` is the row's id, so a transaction leaves all three alone.
        """
        await run.io_bound(library.load_game_collections, True)
        renderers.install_collection_looks(library.smart_collections(), on=table)
        fresh = next((row for row in await offload.io(library.game_rows)
                      if row.get("id") == game_id), None)
        if fresh is None:
            return
        grid.transact(table, rows, {"update": [fresh]}, by_id)

    state["refresh_game"] = refresh_game

    async def refresh_games(ids: list[str]) -> None:
        """The Collections column of the rows an add or its Undo touched, and the panel
        where it is showing one of them. Nothing where the grid has gone."""
        if table.is_deleted or state.get("view") != "games":
            return
        await run.io_bound(library.load_game_collections, True)
        renderers.install_collection_looks(library.smart_collections(), on=table)
        wanted = set(ids)
        fresh = [row for row in await offload.io(library.game_rows)
                 if row.get("id") in wanted]
        grid.transact(table, rows, {"update": fresh}, by_id)
        if state.get("game") in wanted and state.get("section") == "collections":
            answer = on_select(by_id.get(str(state["game"])))
            if inspect.isawaitable(answer):
                await answer

    state["refresh_games"] = refresh_games

    async def counted() -> None:
        seen = await table.run_grid_method("getDisplayedRowCount")
        shown["rows"] = seen if isinstance(seen, int) else len(rows)
        count.text = said()

    async def follow_the_filter() -> None:
        """The address names the collection the grid is narrowed to, while it is one."""
        try:
            model = await table.run_grid_method("getFilterModel") or {}
        except TimeoutError:
            return
        values = list((model.get("collections") or {}).get("values") or [])
        one = values[0] if len(values) == 1 and values[0] else None
        if one != (state.get("collection") or None):
            state["collection"] = one
            deeplink.sync(state)

    table.on("modelUpdated", counted)
    table.on("filterChanged", follow_the_filter, args=[])
    wire_views(table)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText", search.value or ""))


# A tick where it is true and nothing where it is not, so a column of them is scanned
# rather than read. The value stays boolean underneath, which is what lets the column
# sort and filter - a column of "Yes"/"" strings would sort alphabetically and filter
# as text.
# The community text filter does not read a boolean well: it offers a select reading
# "Choose one / True / False" - "Choose one" twice, since the placeholder is also the
# first option, and the two words that follow are the wire's, not a person's. Two
# choices in the column's own terms instead.
# One column per feature. Not used draws nothing at all, so what a reader sees down a
# column is the tables that have it - and, where a scan is mid-flight, the ones nobody
# has read yet. A tick for the plain yes, the same as the asset and media columns; the
# shaped circle is kept for the state that is neither yes nor no.
_FEATURE_MARKS = {
    key: {"mark": table_features.state_for(key).mark,
          "glyph": table_features.state_for(key).glyph,
          "cls": table_features.state_for(key).glyph_class,
          "noun": table_features.state_for(key).noun,
          "why": table_features.state_for(key).why}
    for key in table_features.STATES
}

_FEATURE_RENDERER = (
    "params => {"
    " const m = " + json.dumps(_FEATURE_MARKS) + ";"
    " const v = params.value;"
    " const t = m[v === null || v === undefined ? '" + table_features.UNKNOWN
    + "' : (v ? '" + table_features.IN_SCRIPT + "' : '" + table_features.UNUSED + "')];"
    " if (!t) return '';"
    " const why = t.noun + ' \u2014 ' + t.why;"
    " if (t.glyph) return '<span class=\"' + t.cls + '\" title=\"' + why + '\">'"
    " + t.glyph + '</span>';"
    " if (!t.mark) return '';"
    " return '<span class=\"console-mark ' + t.mark + '\" title=\"' + why"
    " + '\"></span>'; }"
)

# The value is a boolean and null, so the funnel offers the three words rather than a
# text box somebody has to know to type "true" into. Null arrives as "" - the component
# reads an absent value that way, which is what makes "not parsed yet" pickable.
_FEATURE_CHOICES: list[dict[str, Any]] = [
    {"value": True, "label": table_features.state_for(table_features.IN_SCRIPT).noun,
     "glyph": table_features.state_for(table_features.IN_SCRIPT).glyph,
     "glyphClass": table_features.state_for(table_features.IN_SCRIPT).glyph_class},
    {"value": False, "label": table_features.state_for(table_features.UNUSED).noun},
    {"value": "", "label": table_features.state_for(table_features.UNKNOWN).noun,
     "glyph": table_features.state_for(table_features.UNKNOWN).glyph,
     "glyphClass": table_features.state_for(table_features.UNKNOWN).glyph_class},
]

_FEATURES = "console.games.features"

FEATURE_COLUMNS = [
    grid.column(f"feature_{key}", label, group=t(_FEATURES),
                help=t("help.table_feature", label=(label)),
                cellClass="console-media-cell",
                **{**grid.choice_filter(_FEATURE_CHOICES),
                   ":cellRenderer": _FEATURE_RENDERER})
    for key, label in table_features.LABELS.items()
]


# One row per launchable file. The game's name leads, because a filename alone does not
# say what the thing is - and it is pinned, because scrolling right to see which game a
# row belongs to is the failure this subject exists to fix.
_TABLE = "console.games.table"
_IN_PLAY = "console.games.library"

_NEWER = "newer"

# A lock is the exception, so it takes the mark. The value a game with one table holds
# is in no filter choice and draws nothing.
_DEFAULT_STATES = {
    game_tables.CHOSEN: {"label": game_tables.DEFAULT_WORDS[game_tables.CHOSEN][0],
                         "why": game_tables.DEFAULT_WORDS[game_tables.CHOSEN][1],
                         "mark": verbs.LOCKED},
    game_tables.DERIVED: {"label": game_tables.DEFAULT_WORDS[game_tables.DERIVED][0],
                          "why": game_tables.DEFAULT_WORDS[game_tables.DERIVED][1]},
}
_ONLY_TABLE = "only"

# Marks the tables that were deliberately pointed somewhere, so a reader can see what
# changing the default will and will not move. Only on those: a mark on every row would
# say nothing, and following the default is the ordinary case.
SET_HERE_MARK = "● "

# The mark drawn as the picker's dot: the accent, or amber where the table falls back.
_LAUNCHER_CELL = (
    "params => {" + renderers._ESCAPE +
    f" const mark = {json.dumps(SET_HERE_MARK)}; const said = String(params.value || '');"
    " if (!said.startsWith(mark)) return esc(said);"
    " const off = (params.data || {}).launcher_falls_back;"
    f" const tip = off ? {json.dumps(t('console.games.launcher_falls_back'))}"
    f" : {json.dumps(t('console.workbench.chosen_here'))};"
    " return '<span class=\"console-mark console-mark--full console-named-mark'"
    " + (off ? ' console-named-mark--off' : '') + '\" title=\"' + esc(tip) + '\"></span>'"
    " + esc(said.slice(mark.length)); }"
)
_LAUNCHER_DRAWN: dict[str, Any] = {":cellRenderer": _LAUNCHER_CELL}

# What a table's settings file changes for it, by kind. The cell holds the kind, which a
# filter and a saved view keep, and draws `settings_said`.
_OWN_SETTINGS, _POINT_OF_VIEW, _FROM_GAME = "own", "point_of_view", "from_game"
_GAME_SCOPE = t("console.workbench.folder")
_SETTINGS_CHOICES = [
    {"value": _OWN_SETTINGS, "label": t("console.games.has_settings_own")},
    {"value": _POINT_OF_VIEW, "label": t("asset.kind.pov.label")},
    {"value": _FROM_GAME, "label": t("console.games.settings_from", scope=_GAME_SCOPE)},
    {"value": "", "label": t("console.games.same_as_all_tables")},
]
_SETTINGS_DRAWN: dict[str, Any] = {
    ":valueFormatter": "params => (params.data || {}).settings_said || ''",
    ":comparator": "(a, b, nodeA, nodeB) => {"
                   " const n = node => ((node && node.data) || {}).settings_count || 0;"
                   " return n(nodeA) - n(nodeB) || String(a).localeCompare(String(b)); }",
}

# Whether a table's release is a mod, which the filter keeps, drawn as what it is a mod of.
_MOD = "mod"
_MOD_DRAWN: dict[str, Any] = {
    ":valueFormatter": "params => (params.data || {}).mod_of_said || ''",
    ":comparator": "(a, b, nodeA, nodeB, descending) => {"
                   " const said = node => ((node && node.data) || {}).mod_of_said || '';"
                   " const x = said(nodeA), y = said(nodeB);"
                   " if (!x || !y) { if (x === y) return 0; const last = x ? -1 : 1;"
                   "  return descending ? -last : last; }"
                   " return x.localeCompare(y); }",
}

# Which settings those are, by key.
OWN_SETTINGS_COLUMN = "own_settings"

# A column whose answer a panel section holds, so focusing it opens there.
TABLE_COLUMN_SECTIONS = {"settings": "table_settings", OWN_SETTINGS_COLUMN: "table_settings"}

TABLE_COLUMNS = [
    grid.identifier("game", t(_TABLE), 300, pinned="left", group=t(_GAME),
                subtitle=("said", "", "said_built"),
                help=t("console.games.game_this_table.help"),
                **row_drag.source(row_drag.TABLES)),
    grid.column("version", t("word.version"), group=t(_TABLE),
                help=t("console.games.table_s_version.help")),
    grid.column("on_vps", t("console.games.on_vps"), group=t(_TABLE),
                help=t("console.games.on_vps.help")),
    grid.column("update", t("console.games.update"), 140, group=t(_TABLE),
                help=t("console.games.update.help"),
                **grid.choice_filter([
                    {"value": _NEWER, "label": t("console.games.newer_on_vps")},
                    {"value": "", "label": t("console.games.no_newer_version")}])),
    grid.column("mod_of", t("console.games.mod_of"), 200, group=t(_TABLE),
                help=t("console.games.mod_of.help"),
                **{**grid.choice_filter([
                    {"value": _MOD, "label": t("console.games.mod")},
                    {"value": "", "label": t("console.games.no_mod_known")}],
                    formatted=True), **_MOD_DRAWN}),
    grid.column("author", t("word.author"), 160, group=t(_TABLE),
                help=t("console.games.built_table_several_names.help")),
    grid.column("rom", t("console.games.rom"), 110, group=t(_TABLE),
                help=t("console.games.pinmame_rom_table_resolves.help")),
    grid.column("launcher", t("console.games.launcher"), group=t(_TABLE),
                help=t("console.games.launcher_plays_file_dot.help"),
                **_LAUNCHER_DRAWN),
    grid.column("settings", t("console.workbench.table_settings"), 155, group=t(_TABLE),
                help=t("console.games.settings.help"),
                **{**grid.choice_filter(_SETTINGS_CHOICES, formatted=True),
                   **_SETTINGS_DRAWN}),
    grid.list_column(OWN_SETTINGS_COLUMN, t("console.games.own_settings"), 240, group=t(_TABLE),
                     help=t("console.games.own_settings.help"),
                     looks=renderers.SETTING_LOOKS),
    # One column per fact rather than one word folding three together. "Status" cannot
    # stay one column anyway - has an update, missing its rom and the rest are all
    # status - and folded, a table that is both the default and hidden reads as only
    # one of them. Each of these sorts and filters on its own, which is what a list is
    # for. A summary column can be built later, deliberately, from these.
    # Not a tick: a locked default and an automatic one are different facts.
    grid.column("default_state", game_tables.DEFAULT_LABEL, group=t(_IN_PLAY),
                help=t("console.games.table_frontend_offers.help"),
                **grid.choice_filter(
                    [{"value": kind, "label": word}
                     for kind, (word, _why) in game_tables.DEFAULT_WORDS.items()]
                    + [{"value": "", "label": t("console.games.not_default")}],
                    formatted=True),
                **renderers.drawable("state", states=_DEFAULT_STATES)),
    grid.column("rating", t("console.games.table_rating"), group=t(_TABLE),
                help=t("console.games.rating_table_0_5.help"),
                cellClass="console-stars-cell",
                **{**grid.choice_filter(_RATING_CHOICES),
                   ":cellRenderer": stars.renderer("table")}),
    grid.list_column("tags", t("console.workbench.tags"), 200, group=t(_TABLE),
                     help=t("console.games.table_tags.help"), looks=renderers.TAG_LOOKS),
    # Each column's own words, not a generic pair: "Hidden: Yes" is a question about a
    # question, where "Hidden / Offered" is the fact and its opposite.
    grid.column("hidden", t("word.hidden"), group=t(_IN_PLAY),
                help=t("console.games.ticked_where_frontend_not.help"),
                **{**_TICK, **grid.choice_filter(
                    _two(game_tables.HIDDEN_WORDS))}),
    grid.column("missing", t("console.games.missing"), group=t(_IN_PLAY),
                help=t("console.games.ticked_where_library_describes.help"),
                **{**_TICK, **grid.choice_filter(
                    _two(game_tables.FILE_WORDS))}),
    # Last and widest: it is the identifier of record, and the part that tells two
    # tables of one game apart sits at its end.
    grid.column("filename", game_tables.FILE, 420, group=t(_TABLE),
                help=t("console.games.vpx_itself_identifier_record.help")),
    *FEATURE_COLUMNS,
]

# The kinds `resolve_for_table` answers for. Not `library.asset_keys()`, which is the
# folder's set - a PUP pack belongs to the game and has no per-table answer.
TABLE_ASSET_KEYS = ("backglass", "ini", "script", "pov", "scv")


def table_asset_columns(keys: list[str]) -> list[dict[str, Any]]:
    """One column per asset kind, for the tables grid, saying *whose* file answers.

    Not the games grid's tick. Five kinds resolve per table - `.directb2s`, `.ini`,
    `.vbs`, `.pov`, `.scv` - so the honest answer here has three values, not two: this
    table's own file, the game's, or none. `conventions.md`: a binary fact is a tick, a
    fact with more answers is a shaped circle, and these carry the media map's own
    marks because it is the same question about a different file.

    The games grid reports these from a folder scan, so a game whose only `.directb2s`
    is named for one table reads "has one" while its sibling launches without a
    backglass. This is the grain that answers it.
    """
    labels = {key: _asset_label(key) for key in keys}
    headers = {key: grid.two_line(label)
               for key, label in sorted(labels.items(), key=lambda kv: kv[1].lower())}
    width = max((grid.header_width(header) for header in headers.values()), default=92)
    return [grid.column(f"asset_{key}", header, width,
                        cellClass="console-media-cell", group=t(_ASSETS),
                        help=t("help.table_asset_kind", label=(header)),
                        **grid.choice_filter(_STATE_CHOICES),
                        **renderers.drawable("mark"))
            for key, header in headers.items()]


TABLE_VIEWS: dict[str, list[str] | views.Preset] = {
    # Default and Hidden ride in every preset: which table a game offers and whether it
    # is offered at all are the questions this view exists to answer, and a preset that
    # hides them is a list of files.
    #
    # Named for the workbench groups. "Files" and "Play" were one question asked twice -
    # both were app and on-disk state, which is whether this thing runs - so they are
    # Launch, once.
    "console.game_tables.table_file": views.Preset(
        columns=("game", "rating", "default_state", "hidden", "filename"),
        help=t("console.view.table_file.help")),
    "console.game_tables.launch": views.Preset(
        columns=("game", "filename", "launcher", "settings", "rom", "default_state",
                 "hidden", "missing"),
        help=t("console.view.launch.help")),
    # Its own view, not seven more columns on Play: this is a matrix, the same shape as
    # Media on the games grid, and Play stays a list somebody can read across.
    _FEATURES_VIEW: views.Preset(
        columns=("game", *[f"feature_{key}" for key in table_features.LABELS]),
        help=t("console.view.features.help")),
    "console.view.updates": views.Preset(
        columns=("game", "version", "on_vps", "default_state", "hidden", "filename"),
        filters={"update": {"values": [_NEWER]}},
        help=t("console.view.updates.help")),
}


def _table_label(row: dict[str, Any]) -> str:
    """A row menu's heading: the game, then which of its tables this is.

    The pair, on one line, because a menu header has one. `subject` owns the second
    half so this cannot drift from the header, the collection row and the panel.
    """
    said = game_tables.table_name(row)
    game = row.get("game") or ""
    return f"{game}{game_tables.JOIN}{said}" if game and said else (game or said)


def _launcher_word(row: dict[str, Any]) -> str:
    """What plays this table, marked where the table chose it rather than inherited it."""
    name = str(row.get("launcher_name") or "")
    if not name:
        return ""
    return f"{SET_HERE_MARK}{name}" if row.get("launcher_set_here") else name


def _resolved_word(entry: dict[str, Any] | None) -> str:
    """A per-table asset resolution as the tier word a cell draws from. Empty for none,
    which is what a blank cell means everywhere else in these matrices."""
    tier = media_ownership.for_resolution((entry or {}).get("resolution"))
    return "" if tier.key == media_ownership.MISSING else tier.noun


def row_transaction(showing: dict[str, dict[str, Any]], game_id: str,
                    fresh: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """What to tell the grid after one game's rows were rewritten.

    Which of add, update and remove is needed is decided by comparing what came back
    with what is on screen, so one call answers for a table arriving, one changing and
    one going without being told which happened - and a write that does two of those at
    once, which giving a game its first table does: a row arrives and the default moves.

    Only that game's rows are considered on either side. Every other row on screen
    belongs to a game this write did not touch, and offering them as removals would
    empty the grid.
    """
    here = {row_id for row_id, row in showing.items()
            if row.get("game_id") == game_id}
    came_back = {row["id"] for row in fresh}
    transaction: dict[str, list[dict[str, Any]]] = {}
    arrived = [row for row in fresh if row["id"] not in here]
    changed = [row for row in fresh if row["id"] in here]
    gone = [{"id": row_id} for row_id in sorted(here - came_back)]
    if arrived:
        transaction["add"] = arrived
    if changed:
        transaction["update"] = changed
    if gone:
        transaction["remove"] = gone
    return transaction


def add_index(built: list[dict[str, Any]], game_id: str,
              transaction: dict[str, Any]) -> None:
    """Set the transaction's `addIndex` so what arrived follows its game's rows. Without
    it an unsorted grid puts an add after the last row of all."""
    if not transaction.get("add"):
        return
    at = next((index for index, row in enumerate(built) if row.get("game_id") == game_id),
              len(built))
    transaction["addIndex"] = at + len(transaction.get("update", ()))


def table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The API's tables, flattened for a grid.

    `missing` rather than the API's `available`, so all three flags read the same way:
    true is the notable state and the tick means "this row is one of those". Sorting or
    filtering on a column where true means nothing is wrong is a trap.

    `rows` holds every table of each game it covers: whether a game has a choice is
    counted from them.
    """
    held = Counter(str(row.get("game_id") or "") for row in rows)
    return [{**row,
             "missing": not row.get("available", True),
             # The file where there is one, and the name its program knows it by where
             # there is not. A blank cell in the column that identifies the row would
             # read as a fault rather than as a different kind of thing.
             "filename": (row.get("filename") or row.get("key")
                          or row.get("reference") or ""),
             # Whose file answers for this table, in the media map's own words - the
             # cell holds the word and the mark is drawn from it, the way media cells
             # do. Five kinds resolve per table; the rest belong to the folder.
             **{f"asset_{key}": _resolved_word((row.get("assets") or {}).get(key))
                for key in TABLE_ASSET_KEYS},
             "author": ", ".join(row.get("authors") or []),
             "on_vps": str((row.get("source") or {}).get("version") or ""),
             "update": _NEWER if row.get("update_available") else "",
             **_mod_cell((row.get("source") or {}).get("mod_of")),
             "tags": [*((row.get("user") or {}).get("tags") or []),
                      *(row.get("derived_tags") or [])],
             "said": game_tables.made(row),
             "said_built": game_tables.table_name(row),
             "said_built_file": game_tables.names_a_file(row),
             # The name, not the id: `app_name` says why, and the column has to sort
             # and filter on what a reader can see rather than on what is stored.
             # The name plus a mark for chosen against inherited. One cell, because the
             # answer is one fact - what plays this table - and which of the two it is
             # only matters as a qualifier on it.
             "launcher": _launcher_word(row),
             "launcher_falls_back": bool(row.get("launcher_falls_back")),
             **_settings_cell(row),
             # One field per feature: a grid column reads a field, and the payload's
             # nested dict would have every column reaching into the same object.
             # `.get` rather than a default of False - a table nobody parsed answers
             # null for all seven, and inventing False here would lose that.
             **{f"feature_{key}": (row.get("features") or {}).get(key)
                for key in table_features.LABELS},
             "default_state": _default_cell(row, held[str(row.get("game_id") or "")])}
            for row in rows]


def _mod_cell(mod: dict[str, Any] | None) -> dict[str, Any]:
    said = game_tables.mod_of_said(mod)
    return {"mod_of": _MOD if said else "", "mod_of_said": said}


def _settings_cell(row: dict[str, Any]) -> dict[str, Any]:
    """What the table's settings file changes for it: the kind, its words, and how many.
    None where the launcher playing it runs a program that keeps no settings."""
    configurable = bool(row.get("launcher_app_configurable"))
    here = int(row.get("launcher_settings_here") or 0) if configurable else 0
    from_game = int(row.get("launcher_settings_from_folder") or 0) if configurable else 0
    if here == 1 and row.get("launcher_point_of_view"):
        kind, said = _POINT_OF_VIEW, t("asset.kind.pov.label")
    elif here:
        kind, said = _OWN_SETTINGS, t("console.games.settings_own", count=here)
    elif from_game:
        kind, said = _FROM_GAME, t("console.games.settings_from_game", count=from_game,
                                   scope=_GAME_SCOPE)
    else:
        kind, said = "", ""
    return {"settings": kind, "settings_said": said, "settings_count": here or from_game,
            OWN_SETTINGS_COLUMN: list(row.get("launcher_settings_keys") or []) if configurable
            else []}


def setting_their_own(rows: list[dict[str, Any]], launcher_id: str,
                      keys: str) -> dict[str, Any] | None:
    """A filter on the launcher's tables that set any of `keys`, comma separated, for
    themselves, as an address asks for one. None where it names no launcher a table
    uses, or no setting."""
    name = next((str(row.get("launcher_name") or "") for row in rows
                 if launcher_id and row.get("launcher") == launcher_id), "")
    wanted = [key for key in keys.split(",") if key]
    if not name or not wanted:
        return None
    return {"launcher": {"filterType": "text", "operator": "OR", "conditions": [
                {"filterType": "text", "type": "equals", "filter": said}
                for said in (name, f"{SET_HERE_MARK}{name}")]},
            OWN_SETTINGS_COLUMN: {"values": wanted}}


def _default_cell(row: dict[str, Any], held: int) -> str:
    kind = str(row.get("default_kind") or "")
    return _ONLY_TABLE if kind == game_tables.DERIVED and held < 2 else kind


def _tables_said(built: list[dict[str, Any]], shown: int) -> str:
    if shown == len(built):
        return t("console.games.tables_games", len=len(built),
                 len2=len({row["game_id"] for row in built}))
    return t("console.games.tables_of", value=shown, len=len(built))


def build_tables(rows: list[dict[str, Any]], library: Any,
                 on_select: Callable[[dict | None], Any],
                 state: dict[str, Any] | None = None,
                 rerender: Callable[[], None] | None = None,
                 rescan: Callable[[], Any] | None = None) -> None:
    """The library seen by launchable file rather than by folder.

    Its own builder rather than a branch inside the games grid: the columns, the views
    and the row identity are all different, and the two sharing one function would be a
    long argument about which subject each line is for.
    """
    state = state if state is not None else {}
    tag_chips.install(library.tag_looks())
    renderers.install_setting_names(
        {key: said for groups in library.setting_groups().values()
         for key, said in workbench.setting_names(groups).items()})
    built = table_rows(rows)
    # Taken once, as the Games grid takes its own.
    arriving = setting_their_own(rows, str(state.pop("launcher", None) or ""),
                                 str(state.pop("sets", None) or ""))
    table_columns = TABLE_COLUMNS + table_asset_columns(list(TABLE_ASSET_KEYS))
    fields = [definition["field"] for definition in table_columns]

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                                  "console-panel console-grid-bar"):
        bar = panel.grid_bar()
        presets = {**TABLE_VIEWS,
                   _ASSETS: views.Preset(
                       columns=("game",
                                *[f"asset_{key}" for key in TABLE_ASSET_KEYS]),
                       help=t("console.view.table_assets.help"))}

        def annotate() -> None:
            """Every glyph column carries a key, including the state drawn as nothing,
            which is the one a reader is least able to work out from the grid.

            The states this library actually has, though: a table is unparsed only
            between discovery finding it and the enrichment job reaching it, so a line
            explaining a mark nobody can see is spent on every visit for a window most
            people never look through.
            """
            with ui.row().classes("items-center gap-3 no-wrap shrink-0 text-xs "
                                  "opacity-60 console-tier-key") as legend:
                # `shown`, not `state`: this function's own `state` is the page's, and a
                # loop variable by that name quietly replaced it for everything after the
                # legend - which nothing noticed until something further down wrote to it.
                for key in table_features.states_in(built):
                    shown = table_features.state_for(key)
                    with ui.row().classes("items-center gap-1 no-wrap") \
                            .tooltip(shown.why):
                        if shown.glyph:
                            ui.label(shown.glyph).classes(shown.glyph_class)
                        else:
                            ui.element("span").classes(
                                f"console-mark {shown.mark}".strip()
                                if shown.mark else "console-mark-none")
                        ui.label(shown.noun)
            legend.bind_visibility_from(view_picker, "value",
                                        lambda value: value == views.builtin_id(_FEATURES_VIEW))

        wire_views, view_picker, showing, describe = view_control(
            library, f"{SCOPE}.tables", presets, fields, table_columns, bar=bar,
            annotate=annotate, arriving=arriving)
        describe()
        with bar.top, panel.bar_end():
            search = panel.search(t("console.games.search_tables"))
        with bar.bottom, panel.bar_end():
            count = ui.label(_tables_said(built, len(built))) \
                .classes("text-xs console-label")
            actions = ui.button(icon=verbs.MORE).props("flat round dense") \
                .tooltip(t("console.games.actions_selected_tables"))
            with actions:
                bulk_menu = ui.menu().props("no-parent-event")
            actions.set_visibility(False)
            if rescan is not None:
                panel.refresh(rescan, t("console.games.read_library_disk_pick"))

    # The workbench follows the focused row, the same way it does under Games - focus
    # rather than selection, so arrowing down the list is a sweep and the checkboxes
    # stay whatever a bulk action left them.
    by_id = {row["id"]: row for row in built}
    rate_row = stars.rating_handler(built, by_id, lambda: table, ApiClient)

    def focused(event: Any) -> Any:
        row = by_id.get(grid.focused_row(event))
        section = TABLE_COLUMN_SECTIONS.get(grid.focused_column(event))
        if row and section and state.get("section") != workbench.COLLAPSED:
            state["section"] = section
        return on_select(row)

    grid.on_row_focus(f"{SCOPE}.tables", focused)
    state["rate"] = rate_row
    ui.run_javascript(stars.CLICK_JS)

    row_menu: dict[str, Any] = {}
    selected: list[dict[str, Any]] = []
    displayed: dict[str, int] = {"rows": len(built)}

    def said() -> str:
        if selected:
            return grid.selection_said(table, len(selected), t(
                "console.games.selected", len=len(selected), len2=displayed["rows"]))
        return _tables_said(built, displayed["rows"])

    def on_select_rows(rows_selected: list[dict[str, Any]]) -> None:
        selected[:] = rows_selected
        actions.set_visibility(bool(rows_selected))
        count.text = said()

    async def on_context(row: dict | None) -> None:
        # The menu acts on the row under the cursor, not on the selection. Conflating
        # the two is how people act on the wrong thing.
        row_menu["row"] = row
        known = await collection_adds.read(library) if row else None
        _fill(row, known=known)

    def offer(tables: list[dict[str, Any]], subject: str) -> collection_adds.Offer:
        return collection_adds.Offer(
            library, [collection_adds.Row(str(one["game_id"]), str(one["id"]))
                      for one in tables],
            collection_adds.TABLES, subject,
            then=partial(tables_added, [str(one["game_id"]) for one in tables]))

    async def tables_added(games: list[str]) -> None:
        """The panel, where it is showing the Collections of one of these."""
        if table.is_deleted or state.get("view") != "tables":
            return
        if state.get("game") in games and state.get("section") == "collections":
            answer = on_select(by_id.get(str(state.get("table") or "")))
            if inspect.isawaitable(answer):
                await answer

    async def fill_bulk() -> None:
        chosen = grid.selection(table)
        known = await collection_adds.read(library)
        bulk_menu.clear()
        with bulk_menu:
            collection_adds.draw(offer(chosen, ""), known, bulk_menu.close)
            ui.separator()
            panel.menu_entry(t("word.clear_selection"),
                             lambda: table.run_grid_method("deselectAll"))
        bulk_menu.open()

    actions.on_click(fill_bulk)

    async def on_header_context(col_id: str | None) -> None:
        # Asked of the grid rather than tracked here: the column can also be dragged in
        # and out of the pinned area, and a local flag would then be wrong.
        state_now: list[dict[str, Any]] = \
            await table.run_grid_method("getColumnState") or []
        entry = next((c for c in state_now if c.get("colId") == col_id), {})
        _fill(None, col_id=col_id, pinned=bool(entry.get("pinned")))

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        # The selection feeds the bulk menu, never `on_select`: that one is about the
        # focused row, and the grid hands this handler the whole selected list.
        table = grid.build(table_columns, built, f"{SCOPE}.tables", on_select_rows,
                           on_context=on_context,
                           on_header_context=on_header_context, view_of=showing)
        menu: ui.context_menu = ui.context_menu()

    async def counted() -> None:
        seen = await table.run_grid_method("getDisplayedRowCount")
        displayed["rows"] = seen if isinstance(seen, int) else len(built)
        count.text = said()

    table.on("modelUpdated", counted)

    async def refresh_game(game_id: str) -> None:
        """Put one game's rows back after something changed them.

        Every row of that game, not the one acted on: a game can gain a table or lose
        one, and the default moves between them in the same write. Which of the three a
        row needs is decided by comparing what came back with what is showing, so this
        answers for an add, an edit and a removal without being told which it was.
        """
        # From the by-file lens, which is what the grid was built from. The game's own
        # sub-resource describes a table and not where it sits in a library, so it
        # carries no game name, manufacturer, year or resolved rom: patching from it
        # blanks four columns on exactly the rows just acted on.
        rows_now = await offload.io(library.load_tables)
        fresh = table_rows([item for item in rows_now
                            if item.get("game_id") == game_id])
        transaction = row_transaction(by_id, game_id, fresh)
        add_index(built, game_id, transaction)
        if transaction:
            grid.transact(table, built, transaction, by_id)

    async def open_table(table_id: str) -> None:
        """Focus a table's row, which opens it in the panel; a row a filter hides is
        opened without it."""
        if table_id in by_id and await grid.focus_row(table, table_id, "game"):
            return
        opened = on_select(by_id.get(table_id))
        if inspect.isawaitable(opened):
            await opened

    state["refresh_game"] = refresh_game
    state["open_table"] = open_table

    async def drop_script(row: dict[str, Any]) -> None:
        """Asked, because a patched table quietly becomes an unpatched one."""
        if not await confirm.ask(
                t("console.games.delete_script_beside_table"),
                detail=t("console.games.table_goes_back_script"),
                lines=[f"{Path(str(row.get('filename') or '')).stem}.vbs"]):
            return
        await act(library.delete_script, row["game_id"], row["id"],
                  said=t("console.games.deleted_table_runs_own"), row=row)

    async def lock_default(row: dict[str, Any], *, lock: bool) -> None:
        def said(after: Any) -> str:
            return game_tables.lock_said(str(row.get("game") or ""), row,
                                         (after or {}).get("tables") or [], lock=lock)

        await act(library.set_default_table, row["game_id"], row["id"] if lock else "",
                  said=said, row=row)

    async def set_hidden(row: dict[str, Any], *, hidden: bool) -> None:
        def said(answer: Any) -> str:
            return game_tables.hidden_said(str(row.get("game") or ""), row, answer,
                                           hidden=hidden)

        await act(library.set_table_hidden, row["game_id"], row["id"], hidden,
                  said=said, row=row)

    async def act(what: Callable, *args: Any, said: str | Callable[[Any], str] = "",
                  row: dict[str, Any] | None = None) -> None:
        """Run one row-menu act, then put only what changed back on screen.

        Rebuilding the page reads as the grid flashing: scroll position, focus and the
        open panel all go, for a write that touched one game's rows.
        """
        try:
            after = await run.io_bound(what, *args)
        except Exception as exc:
            ui.notify(t("said.could_not_do_that", exc=(exc)), type="negative")
            return
        ui.notify(said(after) if callable(said) else said, type="positive")
        game_id = str((row or {}).get("game_id") or "")
        if row is None or not game_id:
            if rerender is not None:
                rerender()
            return

        await refresh_game(game_id)
        # The panel is about one of these rows and would otherwise still show what the
        # write changed. `on_select` redraws the workbench alone, not the page.
        answer = on_select(by_id.get(row["id"]))
        if inspect.isawaitable(answer):
            await answer

    def _fill(row: dict | None, col_id: str | None = None,
              pinned: bool = False, known: collection_adds.Read | None = None) -> None:
        """One menu, filled for whatever was right-clicked.

        Two menus cannot both hang off the grid wrapper, and the wrapper sees every
        right-click - so the header's entries and the row's share this one.
        """
        menu.clear()
        with menu:
            if col_id and not col_id.startswith("ag-Grid-"):
                header = next((definition.get("headerName")
                               for definition in table_columns
                               if definition.get("field") == col_id), col_id)
                ui.item_label(str(header).replace("\n", " ")).props("header") \
                    .classes("console-menu-header")
                ui.separator()
                # One entry that says what it will do, rather than two where one is
                # always a no-op.
                ui.menu_item(
                    t("word.unpin") if pinned else t("word.pin_left"),
                    lambda c=col_id, p=pinned: grid.pin(table, c, None if p else "left")) \
                    .classes("console-menu-item")
                ui.menu_item(t("word.hide_column"),
                             lambda c=col_id: table.run_grid_method(
                                 "setColumnsVisible", [c], False)) \
                    .classes("console-menu-item")
            elif row:
                ui.item_label(_table_label(row)).props("header") \
                    .classes("console-menu-header")
                ui.separator()
                # Managed here, where every candidate for the game is visible at once.
                if not row.get("default"):
                    if not game_tables.why_not_default(row):
                        panel.menu_entry(
                            t("word.make_default"),
                            lambda r=row: act(library.set_default_table, r["game_id"],
                                              r["id"], said=game_tables.now_plays(
                                                  str(r.get("game") or ""), r),
                                              row=r))
                elif locking := game_tables.lock_act(
                        row, [one for one in by_id.values()
                              if one.get("game_id") == row.get("game_id")]):
                    lock, words = locking
                    panel.menu_entry(words,
                                     lambda r=row, lock=lock: lock_default(r, lock=lock))
                hidden = bool(row.get("hidden"))
                panel.menu_entry(
                    t("console.games.unhide") if hidden else t("console.games.hide"),
                    lambda r=row, h=hidden: set_hidden(r, hidden=not h))
                # The script sidecar. VPX loads a `<table>.vbs` beside the .vpx in
                # preference to the one inside it, so this is per table and belongs on
                # the row rather than only on the panel that was carrying it.
                script = (row.get("assets") or {}).get("script") or {}
                if (script.get("resolution") or "") == "dedicated":
                    panel.menu_entry(t("console.games.delete_script"),
                                     lambda r=row: drop_script(r),
                                     classes="console-menu-danger")
                else:
                    panel.menu_entry(
                        t("console.games.extract_script"),
                        lambda r=row: act(library.extract_script, r["game_id"],
                                          r["id"],
                                          said=t("console.games.extracted_table_now_runs"),
                                          row=r))
                # Only for a table whose file is gone. While it is on disk the record
                # describes something the user owns, and hiding is what takes it out of
                # play without losing its stats.
                if not row.get("available"):
                    panel.menu_entry(
                        t("console.games.forget_table"),
                        lambda r=row: act(library.forget_table, r["game_id"], r["id"],
                                          said=t("console.games.record_dropped"),
                                          row=r))
                if known is not None:
                    ui.separator()
                    collection_adds.draw(offer([row], _table_label(row)), known, menu.close)

    wire_views(table)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                      search.value or ""))


def _by_group(columns: list[dict[str, Any]]) -> list[tuple[str, list[dict]]]:
    """The columns bucketed by their group, groups in the order first declared.

    By meaning rather than by position: File is deliberately the last column in the
    Tables grid and is still a fact about the table, so a picker that mirrored column
    order would print the Table heading twice with the play states between them. What
    the picker answers is *which columns exist*; where they sit is the grid's business
    and the user drags that themselves.
    """
    order: list[str] = []
    groups: dict[str, list[dict]] = {}
    for definition in columns:
        heading = str(definition.get(grid.GROUP_KEY) or "")
        if heading not in groups:
            order.append(heading)
            groups[heading] = []
        groups[heading].append(definition)
    return [(heading, groups[heading]) for heading in order]


def view_control(library: Any, scope: str,
                 presets: Mapping[str, list[str] | views.Preset],
                 all_fields: list[str],
                 columns: list[dict[str, Any]], *, bar: Any,
                 annotate: Callable[[], None] | None = None,
                 arriving: dict[str, Any] | None = None) -> Any:
    """One control for how the rows are presented: which view, and what is in it.

    Built here in the toolbar and wired once the grid exists, because the widgets have
    to sit above the grid and the behavior needs the grid to talk to.

    Returns `(wire, picker, showing, describe)`. Call `wire(table)` once the grid
    exists; the picker is handed back so a caller can hang a binding off which view is
    showing, `showing()` answers the same question for the grid's own geometry, and
    `describe()` draws the view's own line - called last, so it takes the row's full
    width and falls to the foot of the bar.

    `arriving` is a filter model the address asked for. It stands in for the filters of
    the first view put on the grid, and each column it filters is shown.
    """
    custom, active = views.stored(library, scope)
    known = views.builtins(presets) + custom
    if active not in {view.id for view in known}:
        active = known[0].id
    held: dict[str, Any] = {"views": known, "active": active, "custom": custom,
                            "modified": False, "drawing": {}, "baseline": None, "over": None}

    top = bar.top
    with top:
        picker = panel.DescribedSelect(
            {view.id: _view_name(view) for view in known}, value=active,
            label=t("word.view"),
            describes={_view_name(v): (v.help or "") for v in known}) \
            .props("dense outlined").classes("w-52 console-view-picker")
    # Inside the button, not beside it: a q-menu anchors to its parent, and as a
    # sibling this one anchored to the toolbar row and opened 726px away.
    with top:
        menu_button = ui.button(icon=verbs.TUNE).props("flat dense round size=sm") \
            .classes("console-view-menu") \
            .tooltip(t("console.games.columns_saving_view"))
        with menu_button:
            menu = ui.menu()

    def current() -> Any:
        return next(v for v in held["views"] if v.id == held["active"])

    def _reoption(active: str) -> None:
        """The picker's options, and the line each one carries."""
        picker.describes = {_view_name(v): (v.help or "") for v in held["views"]}
        picker.set_options({v.id: _view_name(v) for v in held["views"]}, value=active)

    said: dict[str, Any] = {"box": None}

    def describe() -> None:
        """The view's own line, at the foot of the bar.

        Drawn for a saved view whether or not anything has been written: it is the
        control you write it in, and one that appears only once filled is one nobody
        finds.
        """
        with bar.bottom, ui.row().classes("items-center gap-3 no-wrap console-view-line"):
            said["box"] = ui.element("div").classes("min-w-0 console-view-purpose")
            if annotate is not None:
                annotate()
        _show_purpose()

    def _show_purpose() -> None:
        box = said.get("box")
        if box is None:
            return
        box.clear()
        with box:
            ui.label(getattr(current(), "help", "") or "") \
                .classes("truncate console-view-purpose-text")

    def wire(table: ui.aggrid) -> None:
        def draw(shown: list[str]) -> None:
            """Put the drawing in `held` on screen, and the row height it needs."""
            renderers.draw_as(scope, held["drawing"])
            height = renderers.row_px(held["drawing"], shown, grid.base_row_px(columns))
            table.run_grid_method("setGridOption", "rowHeight", height)
            # The same number twice: the option lays the row out, and `--ag-row-height`
            # is what a cell's line box is derived from. Set on the node - `.style()`
            # would make nicegui rebuild the grid and lose the view.
            ui.run_javascript(
                f"getElement({table.id}).$el.style.setProperty("
                f"'--ag-row-height', '{height}px')")
            table.run_grid_method("redrawRows")

        async def apply(view: Any, over: dict[str, Any] | None = None) -> None:
            """Put a view on the grid: which columns, sorted how, filtered to what -
            and then this view's own widths, which the grid does not carry across a
            switch."""
            _show_purpose()
            baseline = views.arrived(view, over, all_fields)
            held["baseline"], held["over"] = baseline, over
            wanted = views.visible_columns(baseline, all_fields)
            # Leaving the grid as it is keeps it usable, and the notify says why. The
            # old fallback showed every column instead, which reads as the view
            # misbehaving rather than as a view that has gone stale.
            if wanted is None:
                ui.notify(t("console.games.saved_columns_library_no", name=(view.name)),
                        type="warning")
                await _refresh()
                return
            table.run_grid_method("setColumnsVisible", wanted, True)
            table.run_grid_method("setColumnsVisible",
                                  [f for f in all_fields if f not in wanted], False)
            # defaultState clears the sort on every column this view does not name,
            # or an old sort would survive a switch and the view would be a lie.
            table.run_grid_method("applyColumnState",
                                  {"state": list(view.sort),
                                   "defaultState": {"sort": None}})
            # Always set, even to nothing: a view that filters nothing has to clear
            # what the last one filtered, which is what makes picking one a way out
            # rather than a hope.
            table.run_grid_method("setFilterModel", baseline.filters or None)
            held["drawing"] = dict(view.drawn)
            draw(wanted)
            # After visibility, because `applyOrder` only orders what is showing.
            await grid.apply_layout(table, scope, columns, lambda: held["active"])
            await _refresh()

        async def _seen() -> tuple:
            """What the grid is actually showing, in the terms a view is written in.

            AG Grid's own generated columns - the checkbox, chiefly - are in the state
            and are nobody's view, so they are dropped. Left in, every view reads as
            modified the moment it is applied.
            """
            state = [entry for entry in
                     (await table.run_grid_method("getColumnState") or [])
                     if not str(entry.get("colId", "")).startswith("ag-Grid-")]
            model = await table.run_grid_method("getFilterModel") or {}
            shown = tuple(entry["colId"] for entry in state if not entry.get("hide"))
            return shown, tuple(state), model

        async def _refresh() -> None:
            try:
                shown, sort, model = await _seen()
            except TimeoutError:
                # Asking the grid what it is showing is a round trip to the browser,
                # and this one is only to decide whether to mark the view modified.
                # A browser that is busy, or a tab being closed, is not worth failing
                # the thing that called us - the next interaction asks again.
                logger.debug("console: the grid did not answer in time; "
                             "leaving the view mark as it is")
                return
            changed = views.differs(held["baseline"] or current(), shown, sort, model,
                                    held["drawing"])
            # On the picker rather than beside it: the drift is a fact about the view
            # that is selected, so it belongs to the control that names it.
            picker.props(add="suffix=modified") if changed \
                else picker.props(remove="suffix")
            # Recorded, not pushed at controls. The menu is built when it opens, so it
            # reads this - which is one fewer thing to keep in step than a set of
            # buttons that show and hide themselves.
            held["modified"] = changed

        async def keep_views(active: str) -> None:
            """Write the user's views. Off the loop - this is an HTTP call, and the
            client refuses one made from a page's own handler."""
            await run.io_bound(views.remember, library, scope, held["custom"], active)

        async def pick(view_id: str) -> None:
            held["active"] = view_id
            await keep_views(view_id)
            await apply(current())

        async def save(name: str, said: str = "") -> None:
            shown, sort, model = await _seen()
            # Saving over a name replaces that view and keeps its id, so anything
            # keyed to it survives. A new name mints a new id - never a slug of the
            # name, or renaming would orphan the view's own geometry.
            wanted = name.strip()
            standing = next((v for v in held["custom"]
                             if v.name.strip().lower() == wanted.lower()), None)
            view = views.View(id=standing.id if standing else views.mint_id(),
                              name=wanted,
                              builtin=False, columns=shown,
                              sort=tuple(e for e in sort if e.get("sort")),
                              filters=model, help=said.strip(),
                              drawn=dict(held["drawing"]))
            held["custom"] = [v for v in held["custom"] if v.id != view.id] + [view]
            held["views"] = views.builtins(presets) + held["custom"]
            held["active"] = view.id
            held["baseline"], held["over"] = view, None
            await keep_views(view.id)
            _reoption(view.id)
            await _refresh()
            ui.notify(t("console.games.saved_view", name=(view.name)), type="positive")

        async def rename(name: str, said: str = "") -> None:
            """The view's words, changed without touching what it holds."""
            view = current()
            kept = [v if v.id != view.id
                    else replace(v, name=name.strip(), help=said.strip())
                    for v in held["custom"]]
            held["custom"] = kept
            held["views"] = views.builtins(presets) + kept
            await keep_views(held["active"])
            _reoption(held["active"])
            _show_purpose()

        async def delete() -> None:
            view = current()
            if view.builtin:
                return
            held["custom"] = [v for v in held["custom"] if v.id != view.id]
            held["views"] = views.builtins(presets) + held["custom"]
            held["active"] = held["views"][0].id
            await keep_views(held["active"])
            _reoption(held["active"])
            await apply(current())

        async def fill_menu() -> None:
            """Everything about how this view looks, in one menu.

            Built when it opens rather than kept in step: which columns are showing is
            the grid's to answer, and a checklist rebuilt from it cannot go stale.
            """
            column_state = await table.run_grid_method("getColumnState") or []
            hidden = {entry.get("colId") for entry in column_state if entry.get("hide")}
            view = current()
            menu.clear()
            with menu:
                ui.menu_item(t("console.games.save"), lambda: _ask_name(save)) \
                    .classes("console-menu-item")
                # Only where they mean something: there is nothing to revert to until
                # the screen has drifted, and nothing to delete unless it is the
                # user's own view.
                if held["modified"]:
                    ui.menu_item(t("console.games.revert"),
                                 lambda: apply(current(), held["over"])) \
                        .classes("console-menu-item")
                if not view.builtin:
                    ui.menu_item(t("console.games.rename_view"),
                                 lambda v=view: _ask_name(
                                     rename, named=v.name, said=v.help,
                                     title=t("console.games.rename_view"))) \
                        .classes("console-menu-item")
                if not view.builtin and not held["modified"]:
                    ui.menu_item(t("console.games.delete_view"), delete) \
                        .classes("console-menu-item console-menu-danger")
                drawings(hidden)
                ui.separator()
                # An explicit column: the menu lays its children out inline otherwise,
                # so twenty checkboxes wrap into a paragraph rather than a list.
                with ui.column().classes("gap-0 w-full py-1 items-stretch"):
                    for heading, group in _by_group(columns):
                        # Named groups only. A grid whose columns declare none reads
                        # as one list, which is right when there are eight of them.
                        if heading:
                            ui.item_label(heading).props("header") \
                                .classes("console-menu-header")
                        for definition in group:
                            field = definition["field"]
                            label = str(definition.get(grid.PICKER_KEY)
                                        or definition.get("headerName") or field) \
                                .replace("\n", " ")
                            box = ui.checkbox(label, value=field not in hidden,
                                        on_change=lambda event, f=field:
                                        table.run_grid_method("setColumnsVisible",
                                                              [f], event.value)) \
                                .props("dense").classes("console-menu-item w-full")
                            explains = str(definition.get("headerTooltip") or "")
                            if explains:
                                with box:
                                    ui.tooltip(explains).classes("console-menu-tip")

        def drawings(hidden: set[str]) -> None:
            """How each shown group of columns is drawn, where it can be drawn more
            than one way."""
            shown = [d for d in columns if d["field"] not in hidden]
            for heading, group in _by_group(shown):
                offered = [renderers.choices(d) for d in group if len(renderers.choices(d)) > 1]
                if not offered:
                    continue
                names = offered[0]
                fields = [d["field"] for d in group if renderers.choices(d) == names]
                now = held["drawing"].get(fields[0], names[0])
                ui.item_label(t("console.games.show_as", group=heading or t("word.columns"))) \
                    .props("header").classes("console-menu-header")
                ui.toggle({name: t(renderers.REGISTRY[name].label) for name in names},
                          value=now,
                          on_change=lambda event, f=fields, n=names:
                          redraw(f, n, str(event.value))) \
                    .props("dense no-caps unelevated").classes("q-mx-sm q-mb-xs")

        async def redraw(fields: list[str], names: tuple[str, ...], chosen: str) -> None:
            for one in fields:
                if chosen == names[0]:
                    held["drawing"].pop(one, None)
                else:
                    held["drawing"][one] = chosen
            state = await table.run_grid_method("getColumnState") or []
            draw([e["colId"] for e in state if not e.get("hide")])
            await _refresh()

        menu_button.on_click(fill_menu)
        picker.on_value_change(lambda event: pick(event.value))
        # The grid reports its own changes; the marker follows them rather than being
        # recomputed on a timer that would outlive the grid.
        for event in ("columnVisible", "sortChanged", "filterChanged"):
            table.on(event, lambda: _refresh(), args=[])
        ui.timer(0, lambda: apply(current(), arriving), once=True)

    return wire, picker, lambda: held["active"], describe


def _view_name(view: Any) -> str:
    """As typed, or as `views.builtins` read it. Looking it up again here would build a
    key out of the translation."""
    return str(view.name or "")


def _ask_name(save: Callable[..., Any], *, named: str = "",
              said: str = "", title: str = "") -> None:
    """Name a view and say what it is for, in one place."""
    held: dict[str, Any] = {}

    def draw_name() -> None:
        held["name"] = frame.field(named)
        held["name"].on_value_change(cleared)

    def cleared() -> None:
        held["name"].props["error"] = False

    async def keep() -> None:
        name = held["name"]
        if not (name.value or "").strip():
            name.props["error"] = True
            name.props["error-message"] = t("said.give_it_a_name")
            return
        box.close()
        await save(name.value, held["purpose"].value or "")

    with frame.opened(title or t("console.games.save_view")) as box:
        panel.facts(ui, [
            (t("word.name"), draw_name),
            (t("console.workbench.description"),
             lambda: held.update(purpose=frame.field(
                 said, placeholder=t("console.games.what_view_for"))))])
        with frame.footer():
            frame.cancel(box.close)
            go = frame.answer(t("word.save"), keep, icon=verbs.SAVE)
    frame.focus(box, held["name"])
    frame.enter_presses(go)
    box.open()
