"""The games grid: one row per game, with views over the same rows."""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common.games import asset_registry
from common.labels import humanize
from common.media_specs import media_label_map
from hubui import features as table_features
from hubui import game_tables, grid, media_ownership, mediaview, views, workbench
from hubui.api import HubClient

logger = logging.getLogger("vpinfe.hubui.games")

SCOPE = "hubui.games.columns"

# The groups are section 13's grain distinction, surfaced in the column picker: what
# the row *is*, what it rolls up, and what it has. Media sits last because it is most
# of the list and least of the use - and last is where it already was, so the grouping
# names a seam that was there rather than moving anything.
_GAME = "Game"
_ASSETS = "Assets"
_MEDIA = "Media"

# What the games resource calls an asset is not always what `asset_registry` calls it -
# `settings` is the table INI, and one `alt_color` covers both Serum and VNI. Named
# here because the two vocabularies have not been reconciled, and a column headed
# "Settings" says nothing about which file it means.
# Only where this surface has to differ from the registry's own label. Everything
# else asks `asset_registry`, which is where a kind's acronyms are cased once.
# `alt_color` and `alt_sound` are here because the games resource still names them
# its own way - one `alt_color` covering the registry's Serum and VNI.
_ASSET_LABELS = {
    "alt_color": "Alt Color",
    "alt_sound": "AltSound",
    # The `.directb2s`, which media also calls a backglass - one is the file that
    # drives the second screen, the other is a picture of it. A column header has no
    # group heading beside it, so the two cannot both be "Backglass".
    "backglass": "B2S",
}


def _asset_label(key: str) -> str:
    """The registry's word for a kind, then this surface's override, then humanize."""
    if key in _ASSET_LABELS:
        return _ASSET_LABELS[key]
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
def _stars(subject: str) -> str:
    game = "row.id" if subject == "game" else "(row.game_id || '')"
    table = "''" if subject == "game" else "row.id"
    return (
        "params => {"
        " const row = params.data || {}; const held = Number(params.value) || 0;"
        " let out = '<span class=\"hub-stars\" data-game=\"' + " + game
        + " + '\" data-table=\"' + " + table + " + '\">';"
        " for (let n = 1; n <= 5; n++) {"
        "  out += '<span class=\"hub-star' + (n <= held ? ' hub-star--on' : '')"
        "  + '\" data-value=\"' + (n === held ? 0 : n) + '\" title=\"'"
        "  + (n === held ? 'Clear' : n + ' of 5') + '\"></span>';"
        " }"
        # Only where there is something to clear: an X on every unrated game would be a
        # column of controls, so it appears where it has work to do.
        " if (held) { out += '<span class=\"hub-star-clear\" data-value=\"0\"'"
        "  + ' title=\"Clear rating\">\u00d7</span>'; }"
        " return out + '</span>'; }"
    )


# Filtering by a rating means picking one, not typing it: the value is a number and the
# cell is five stars, so AG Grid's text box was asking the reader to guess that "3" is
# what a three-star row holds. Unrated leads, because "which of these have I not judged
# yet" is the question this column is opened for.
_RATING_CHOICES = ([{"value": 0, "label": "Unrated"}]
                   + [{"value": n, "label": "", "mark": "hub-star hub-star--on",
                       "repeat": n} for n in range(1, 6)])


# Delegated once, in the capture phase for the same reason the enlarge is: the cell's
# own click would move the focused row, and rating a row you can see is not a request
# to go and look at it.
_STARS_JS = """
if (!window.__hubStars) {
  window.__hubStars = true;
  document.addEventListener('click', (e) => {
    const star = e.target.closest && e.target.closest('.hub-stars [data-value]');
    if (!star) return;
    e.stopPropagation();
    const box = star.closest('.hub-stars');
    emitEvent('hub_rate', {game: box.dataset.game, table: box.dataset.table,
                           value: Number(star.dataset.value)});
  }, true);
}
"""



COLUMNS = [
    grid.column("name", "Name", 280, pinned="left", group=_GAME),
    # Always, including 1: it is the only thing saying the row collapses its tables,
    # and it qualifies everything to its right. HUBUI section 13. "Table Count" rather
    # than "Tables", which read as the tables themselves - this is a number about the
    # game, and it belongs with the game's other facts.
    grid.column("table_count", "Table Count", type="numericColumn", group=_GAME),
    grid.column("manufacturer", "Manufacturer", group=_GAME),
    grid.column("year", "Year", group=_GAME),
    grid.column("game_type", "Type", group=_GAME),
    grid.column("themes", "Themes", 200, group=_GAME),
    # No ROM or Version here: ROM is an asset (`asset_registry`), Version has no
    # game-level meaning, and both were the default table's shown as the game's.
    # Named for whose rating it is, because the tables grid has one too and "Rating"
    # in two places invites the reader to assume they are the same number.
    grid.column("rating", "Game Rating", group=_GAME,
                cellClass="hub-stars-cell",
                **grid.choice_filter(_RATING_CHOICES),
                **{":cellRenderer": _stars("game")}),
]

# Presets, not a replacement for choosing columns: a view sets which columns are
# shown, and anything the user changes afterwards is theirs and is what persists.
# Only fields that belong to a game. `rom` and `version` do not: game_repository reads
# them from the default table, so at this grain they report one table's and call them
# the game's. Tables is where that question is answered.
# Which part of a game a view is about, so a row lands there rather than on Details
# and one more click. Only where the view leaves no doubt - the rest open wherever the
# panel was, which is what stepping down a list needs.
VIEW_SECTIONS = {"builtin:Media": "media"}

GAME_VIEWS: dict[str, list[str]] = {
    # Named for the workbench group it matches. HUBUI section 14: a view and a panel
    # group about the same facts carry the same word, so crossing between the grid and
    # the panel is not a translation.
    game_tables.MACHINE: ["name", "table_count", "manufacturer", "year", "game_type",
                "themes", "rating"],
    # Media and Assets are built from what the library reports it has, so both are
    # filled at render time. Two views, not one: they answer different questions - what
    # a game looks like, and what it needs to play as intended - and a matrix that mixes
    # them is neither.
    "Media": [],
    "Assets": [],
}

_ALL = [definition["field"] for definition in COLUMNS]


# A renderer is a way of drawing a field, chosen per column. Two here, hardcoded, to
# see whether the idea earns a registry: the same media field as a mark or as a picture.
RENDERERS = ("Ticks", "Thumbnails")

# What one row is: three grains of the library the user owns - the folder, the
# launchable file inside it, and the asset that resolved for it. Everything here has to
# be something the workbench can answer for, which is what keeps a catalog out.
SUBJECTS = {
    "game": "Games",
    "table": "Tables",
    "media_file": "Media files",
}

SUBJECT_STUBS = {
    "media_file": "One row per file on disk, with the game it resolved to and the tier "
                  "it resolved at. This is where an orphaned file becomes visible.",
}


# An asset column asks whether the game has one, and "Missing" is the word the media
# vocabulary already uses for the same absence.
_HAS_CHOICES = [{"value": True, "label": "Present"},
                {"value": False, "label": "Missing"}]


def asset_columns(keys: list[str]) -> list[dict[str, Any]]:
    """One column per asset kind, availability only.

    A group rather than the single count that stood here, which was a count of *media*
    under an Assets heading. What a reader wants is which of them a game has, and a
    number cannot say that - the same argument that made media a group.
    """
    labels = {key: _asset_label(key) for key in keys}
    width = max((grid.header_width(label) for label in labels.values()), default=92)
    return [grid.column(f"asset_{key}", label, width, group=_ASSETS,
                        cellStyle={"textAlign": "center"},
                        **{**_TICK, **grid.choice_filter(_HAS_CHOICES)})
            for key, label in sorted(labels.items(), key=lambda kv: kv[1].lower())]


# Word -> how to draw it, derived from the vocabulary rather than restated. The cell
# holds the word and the mark is drawn from it here; `hubui/data.py` has why.
_MARK_BY_WORD = {
    tier.noun: {"mark": tier.mark, "why": tier.why}
    for tier in (media_ownership.tier_for(key) for key in media_ownership.STATES)
}

# What the funnel offers on a media column, in the legend's own words and marks. The
# value is what the cell holds - "" for missing, which is a blank cell and so a choice
# like any other rather than the one state the filter cannot express.
#
# And no mark on Missing: the cell draws nothing for it, so a glyph here would offer a
# mark the grid never puts on screen. Same reason the legend leaves it out.
_STATE_CHOICES = [
    {"value": "" if key == media_ownership.MISSING
     else media_ownership.tier_for(key).noun,
     "label": media_ownership.tier_for(key).noun,
     "mark": ("" if key == media_ownership.MISSING
              else f"hub-mark {media_ownership.tier_for(key).mark}")}
    for key in media_ownership.STATES
]


# One renderer for both presentations, choosing on a flag rather than on the value.
# The alternative - swapping the column's renderer - cannot work: the ":" prefix that
# marks a string as JavaScript is resolved when the grid is built, so a definition
# pushed through `setGridOption` later arrives as a literal string.
#
# With the pictures on, a kind that has no picture - audio, video, a rule sheet - keeps
# its mark rather than emptying: the file is there either way, and a column that goes
# blank when you ask to see the art reads as one that lost its files.
_MARK_RENDERER = (
    "params => {"
    " const kind = params.colDef.field.slice(6);"
    " if (window.__hubThumbs) {"
    " const row = params.data || {}; const art = row['thumb_' + kind];"
    " if (art) return '<span class=\"hub-cell-art\">' + art"
    " + '<i class=\"material-icons hub-cell-zoom\" title=\"Enlarge\" data-game=\"'"
    " + row.id + '\" data-kind=\"' + kind + '\">open_in_full</i></span>'; }"
    " const m = " + json.dumps(_MARK_BY_WORD) + ";"
    " const t = m[params.value]; if (!t) return '';"
    " const tip = params.value + ' \u2014 ' + t.why;"
    " return '<span class=\"hub-mark ' + t.mark + '\" title=\"' + tip"
    " + '\"></span>'; }"
)


# Delegated and installed once: NiceGUI strips inline handlers off raw HTML, and a
# renderer runs again on every scroll. The click is taken in the *capture* phase,
# because AG Grid's handler sits between the cell and the document - stopping the event
# on the way back up is too late, and enlarging would also pick the slot.
_CELL_MEDIA = """
if (!window.__hubCellMedia) {
  window.__hubCellMedia = true;
  const clip = (el) => el && el.closest
    ? el.closest('.hub-media-cell')?.querySelector('video') : null;
  document.addEventListener('mouseover', (e) => {
    const v = clip(e.target);
    if (v && v.paused) v.play().catch(() => {});
  });
  document.addEventListener('mouseout', (e) => {
    const v = clip(e.target);
    if (!v) return;
    const cell = e.target.closest('.hub-media-cell');
    if (e.relatedTarget && cell && cell.contains(e.relatedTarget)) return;
    v.pause();
    v.currentTime = 0.1;
  });
  document.addEventListener('click', (e) => {
    const zoom = e.target.closest && e.target.closest('.hub-cell-zoom');
    if (!zoom) return;
    e.stopPropagation();
    emitEvent('hub_media_zoom', {game: zoom.dataset.game, kind: zoom.dataset.kind});
  }, true);
}
"""


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
               for kind in sorted(kinds, key=lambda k: labels.get(k, k).lower())}
    width = max((grid.header_width(header) for header in headers.values()), default=92)
    return [grid.column(f"media_{kind}", header, width,
                        cellClass="hub-media-cell", group=_MEDIA,
                        **grid.choice_filter(_STATE_CHOICES),
                        **{":cellRenderer": _MARK_RENDERER})
            for kind, header in headers.items()]


async def _rate(games: list[dict[str, Any]]) -> None:
    """Set a rating on every game passed in.

    The API rates one game at a time (`PUT /games/{id}/rating`), so this loops here
    rather than calling a bulk endpoint that does not exist.
    """
    from nicegui import run
    if not games:
        return

    async def apply(value: int) -> None:
        client = HubClient()
        for game in games:
            await run.io_bound(client.rate, game["id"], value)
        dialog.close()
        ui.notify(f"Rated {len(games)} game(s) {value}", type="positive")

    with ui.dialog() as dialog, ui.card():
        ui.label(f"Rate {len(games)} game(s)").classes("text-sm")
        with ui.row():
            for value in range(6):
                ui.button(str(value), on_click=lambda v=value: apply(v)).props("flat dense")
    dialog.open()


async def _launch(games: list[dict[str, Any]]) -> None:
    """Launch one game. Deliberately refuses a multi-row selection.

    Launching is device-resident and starts something on a machine; doing it for
    several rows at once has no sensible meaning, so it is refused rather than looped.
    """
    from nicegui import run
    if len(games) != 1:
        ui.notify("Select a single game to launch", type="warning")
        return
    await run.io_bound(HubClient().launch, games[0]["id"])
    ui.notify(f"Launching {games[0].get('name')}", type="positive")


def build(rows: list[dict[str, Any]], kinds: list[str], library: Any,
          on_select: Callable[[dict | None], None],
          state: dict[str, Any] | None = None,
          rerender: Callable[[], None] | None = None) -> None:
    state = state if state is not None else {}
    subject = state.get("subject", "game")
    if subject != "game":
        # Stop before the grid, not after it. A toolbar of controls acting on a table
        # that is not there is worse than an empty page.
        with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                              "hub-panel"):
            _subject_select(state, rerender, subject)
        _subject_stub(subject)
        return
    columns = COLUMNS + asset_columns(library.asset_keys()) + media_columns(kinds)
    all_fields = [definition["field"] for definition in columns]
    selected: list[dict[str, Any]] = []
    context_row: list[dict[str, Any]] = []

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 hub-panel"):
        _subject_select(state, rerender, subject)
        search = ui.input(placeholder="Search games") \
            .props("dense outlined clearable").classes("w-64")
        # The media preset is the library's own kinds, so it is only knowable here.
        presets = {**GAME_VIEWS,
                   "Media": ["name", *[f"media_{kind}" for kind in kinds]],
                   "Assets": ["name", *[f"asset_{key}" for key in library.asset_keys()]]}
        wire_views, view_picker = view_control(library, SCOPE, presets, all_fields,
                                              columns)
        cells = ui.toggle(list(RENDERERS), value="Ticks").props("dense no-caps unelevated")
        cells.bind_visibility_from(view_picker, "value",
                                   lambda value: value == "builtin:Media")
        ui.space()
        # Read from the vocabulary rather than restated here, and each entry carries
        # its own explanation on hover - a legend that names a state without saying
        # what it means is half a legend.
        with ui.row().classes("items-center gap-3 no-wrap text-xs opacity-60 "
                              "hub-tier-key") as legend:
            for key in media_ownership.LEGEND:
                tier = media_ownership.tier_for(key)
                with ui.row().classes("items-center gap-1 no-wrap").tooltip(tier.why):
                    ui.element("span").classes(f"hub-mark {tier.mark}")
                    ui.label(tier.noun)
        legend.bind_visibility_from(view_picker, "value",
                                    lambda value: value == "builtin:Media")
        # The selection count sits with the total: it is the same fact - how much am I
        # looking at - and it costs no vertical space of its own.
        count = ui.label(f"{len(rows)} games").classes("text-xs hub-label")
        actions = ui.button(icon="more_vert").props("flat round dense") \
            .tooltip("Actions for the selected games")
        with actions:
            with ui.menu():
                ui.menu_item("Rate selected", lambda: _rate(selected))
                ui.separator()
                ui.menu_item("Clear selection",
                             lambda: table.run_grid_method("deselectAll"))
        actions.set_visibility(False)

    def on_select_rows(rows_selected: list[dict[str, Any]]):
        selected[:] = rows_selected
        actions.set_visibility(bool(rows_selected))
        count.text = (f"{len(rows_selected)} of {len(rows)} selected"
                      if rows_selected else f"{len(rows)} games")

    by_id = {row["id"]: row for row in rows}

    def focused(event) -> Any:
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
            section = VIEW_SECTIONS.get(str(view_picker.value or ""))
            if section:
                state["section"] = section
        return on_select(row)

    def zoom_media(event) -> None:
        """Enlarge the file a cell is showing - the same viewer the media map opens."""
        args = event.args if isinstance(event.args, dict) else {}
        game_id, kind = str(args.get("game") or ""), str(args.get("kind") or "")
        if game_id and kind:
            mediaview.open_viewer(f"/api/v1/games/{game_id}/media/{kind}", kind,
                                  media_label_map().get(kind, kind))

    async def rate_row(event) -> None:
        """Set a rating from the stars, and redraw the one row that changed.

        A whole-grid refresh would cost the scroll position and the selection for one
        number - and the row is the only thing that knows it changed.
        """
        args = event.args if isinstance(event.args, dict) else {}
        game_id, table_id = str(args.get("game") or ""), str(args.get("table") or "")
        value = int(args.get("value") or 0)
        if not game_id:
            return
        client = HubClient()
        try:
            if table_id:
                await run.io_bound(client.rate_table, game_id, table_id, value)
            else:
                await run.io_bound(client.rate, game_id, value)
        except Exception as exc:
            ui.notify(f"Could not save that rating: {exc}", type="negative")
            return
        row = by_id.get(table_id or game_id)
        if row is not None:
            row["rating"] = value
            table.run_grid_method("applyTransaction", {"update": [row]})

    ui.on("hub_row_focus", focused)
    ui.on("hub_media_zoom", zoom_media)
    ui.on("hub_rate", rate_row)
    ui.run_javascript(_CELL_MEDIA)
    ui.run_javascript(_STARS_JS)

    def on_context(row: dict | None) -> None:
        # The row menu acts on the row under the cursor, which is not necessarily the
        # selection. Conflating the two is how people act on the wrong thing.
        context_row[:] = [row] if row else []
        _fill_menu(row=row)

    async def on_header_context(col_id: str | None) -> None:
        # Asked of the grid rather than tracked here: the column can also be dragged in
        # and out of the pinned area, and a local flag would then be wrong.
        current = await table.run_grid_method("getColumnState")
        entry = next((c for c in current if c.get("colId") == col_id), {})
        _fill_menu(col_id=col_id, pinned=bool(entry.get("pinned")))

    async def set_pinned(col_id: str, pinned: str | None) -> None:
        table.run_grid_method("applyColumnState",
                              {"state": [{"colId": col_id, "pinned": pinned}]})

    async def hide_column(col_id: str) -> None:
        table.run_grid_method("setColumnsVisible", [col_id], False)

    def _fill_menu(row: dict | None = None, col_id: str | None = None,
                   pinned: bool = False) -> None:
        """One menu, filled for whatever was right-clicked.

        Two menus cannot both hang off the grid wrapper, and the wrapper sees every
        right-click - which is why the row menu used to appear over a header offering to
        launch a column.
        """
        context_menu.clear()
        with context_menu:
            if col_id and not col_id.startswith("ag-Grid-"):
                header = next((definition.get("headerName") for definition in columns
                               if definition.get("field") == col_id), col_id)
                ui.item_label(str(header).replace("\n", " ")) \
                    .props("header").classes("hub-menu-header")
                ui.separator()
                # One entry that says what it will do, rather than two where one is
                # always a no-op.
                if pinned:
                    ui.menu_item("Unpin", lambda: set_pinned(col_id, None)) \
                        .classes("hub-menu-item")
                else:
                    ui.menu_item("Pin left", lambda: set_pinned(col_id, "left")) \
                        .classes("hub-menu-item")
                ui.menu_item("Hide column", lambda: hide_column(col_id)) \
                    .classes("hub-menu-item")
            elif row:
                ui.item_label(row.get("name") or "").props("header") \
                    .classes("hub-menu-header")
                ui.separator()
                ui.menu_item("Launch", lambda: _launch(context_row)).classes("hub-menu-item")

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
        table = grid.build(columns, rows, SCOPE, on_select_rows, on_context,
                           on_header_context)
        context_menu = ui.context_menu()

    def apply_renderer() -> None:
        """Redraw the media cells as marks or as pictures.

        The *renderer* changes; the value never does. Swapping the picture into the
        value left the filter matching whichever presentation was showing, so filtering
        by "All tables" broke the moment the thumbnails came on.
        """
        thumbs = cells.value == "Thumbnails"
        height = 60 if thumbs else 42
        ui.run_javascript(f"window.__hubThumbs = {str(thumbs).lower()}")
        table.run_grid_method("setGridOption", "rowHeight", height)
        # The same number twice, because AG Grid keeps two: the option lays the row out,
        # `--ag-row-height` is what its stylesheet derives a cell's line height from and
        # it does not follow the option. Left behind, every cell in a taller row - the
        # name as much as the picture - drew against a 39px line box and sat high in it.
        table.style(f"--ag-row-height: {height}px")
        table.run_grid_method("redrawRows")

    cells.on_value_change(apply_renderer)
    wire_views(table)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText", search.value or ""))


# A tick where it is true and nothing where it is not, so a column of them is scanned
# rather than read. The value stays boolean underneath, which is what lets the column
# sort and filter - a column of "Yes"/"" strings would sort alphabetically and filter
# as text.
# The community text filter does not read a boolean fine, which is what this used to
# say: it offers a select reading "Choose one / True / False" - "Choose one" twice, since
# the placeholder is also the first option, and the two words that follow are the wire's,
# not a person's. Two choices in the column's own terms instead.
def _two(words: tuple[str, str]) -> list[dict[str, Any]]:
    """A fact's own pair as the funnel's two choices, true first - which is the notable
    state, because that is the direction every one of these columns reads."""
    return [{"value": True, "label": words[0]}, {"value": False, "label": words[1]}]


_TICK = {
    ":valueFormatter": "params => params.value ? '\u2713' : ''",
    "cellClass": "hub-tick",
    ":cellRenderer": None,
    # Yes and No, because the column's own header is the noun: "Hidden" answers yes or
    # no, and a pair naming the thing again would read as "Hidden: Present". A column
    # whose subject has better words passes its own.
    **grid.choice_filter([{"value": True, "label": "Yes"},
                          {"value": False, "label": "No"}]),
}


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
    " return '<span class=\"hub-mark ' + t.mark + '\" title=\"' + why"
    " + '\"></span>'; }"
)

# The value is a boolean and null, so the funnel offers the three words rather than a
# text box somebody has to know to type "true" into. Null arrives as "" - the component
# reads an absent value that way, which is what makes "not parsed yet" pickable.
_FEATURE_CHOICES = [
    {"value": True, "label": table_features.state_for(table_features.IN_SCRIPT).noun,
     "glyph": table_features.state_for(table_features.IN_SCRIPT).glyph,
     "glyphClass": table_features.state_for(table_features.IN_SCRIPT).glyph_class},
    {"value": False, "label": table_features.state_for(table_features.UNUSED).noun},
    {"value": "", "label": table_features.state_for(table_features.UNKNOWN).noun,
     "glyph": table_features.state_for(table_features.UNKNOWN).glyph,
     "glyphClass": table_features.state_for(table_features.UNKNOWN).glyph_class},
]

_FEATURES = "Features"

FEATURE_COLUMNS = [
    grid.column(f"feature_{key}", label, group=_FEATURES,
                cellClass="hub-media-cell",
                **grid.choice_filter(_FEATURE_CHOICES),
                **{":cellRenderer": _FEATURE_RENDERER})
    for key, label in table_features.LABELS.items()
]


# One row per launchable file. The game's name leads, because a filename alone does not
# say what the thing is - and it is pinned, because scrolling right to see which game a
# row belongs to is the failure this subject exists to fix.
_TABLE = "Table"
_IN_PLAY = "In this library"

TABLE_COLUMNS = [
    grid.column("game", "Game", 240, pinned="left", group=_GAME),
    grid.column("version", "Version", group=_TABLE),
    grid.column("author", "Author", 160, group=_TABLE),
    grid.column("rom", "ROM", 110, group=_TABLE),
    grid.column("app", "App", group=_TABLE),
    # One column per fact rather than one word folding three together. "Status" cannot
    # stay one column anyway - has an update, missing its rom and the rest are all
    # status - and folded, a table that is both the default and hidden reads as only
    # one of them. Each of these sorts and filters on its own, which is what a list is
    # for. A summary column can be built later, deliberately, from these.
    # Not a tick: a chosen default and a derived one are different facts.
    grid.column("default_state", game_tables.DEFAULT_LABEL, group=_IN_PLAY,
                **grid.choice_filter(
                    [{"value": word, "label": word}
                     for word, _why in game_tables.DEFAULT_WORDS.values()]
                    + [{"value": "", "label": "Not the default"}])),
    grid.column("rating", "Table Rating", group=_TABLE,
                cellClass="hub-stars-cell",
                **grid.choice_filter(_RATING_CHOICES),
                **{":cellRenderer": _stars("table")}),
    # Each column's own words, not a generic pair: "Hidden: Yes" is a question about a
    # question, where "Hidden / Offered" is the fact and its opposite.
    grid.column("hidden", "Hidden", group=_IN_PLAY,
                **{**_TICK, **grid.choice_filter(
                    _two(game_tables.HIDDEN_WORDS))}),
    grid.column("missing", "Missing", group=_IN_PLAY,
                **{**_TICK, **grid.choice_filter(
                    _two(game_tables.FILE_WORDS))}),
    # Last and widest: it is the identifier of record, and the part that tells two
    # tables of one game apart sits at its end.
    grid.column("filename", game_tables.FILE, 420, group=_TABLE),
    *FEATURE_COLUMNS,
]

TABLE_VIEWS: dict[str, list[str]] = {
    # Default and Hidden ride in every preset: which table a game offers and whether it
    # is offered at all are the questions this view exists to answer, and a preset that
    # hides them is a list of files.
    #
    # Named for the workbench groups. "Files" and "Play" were one question asked twice -
    # both were app and on-disk state, which is whether this thing runs - so they are
    # Launch, once. HUBUI section 14.
    game_tables.FILE: ["game", "version", "author", "rating", "default_state",
                       "hidden", "filename"],
    game_tables.LAUNCH: ["game", "filename", "app", "rom", "default_state", "hidden",
                         "missing"],
    # Its own view, not seven more columns on Play: this is a matrix, the same shape as
    # Media on the games grid, and Play stays a list somebody can read across.
    game_tables.FEATURES: ["game", "version", "author",
                 *[f"feature_{key}" for key in table_features.LABELS]],
}


def _table_label(row: dict[str, Any]) -> str:
    """A row menu's heading: the game, then which of its tables this is.

    The pair, on one line, because a menu header has one. `subject` owns the second
    half so this cannot drift from the header, the collection row and the panel.
    """
    said = game_tables.table_name(row)
    game = row.get("game") or ""
    return f"{game}{game_tables.JOIN}{said}" if game and said else (game or said)


def table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The API's tables, flattened for a grid.

    `missing` rather than the API's `available`, so all three flags read the same way:
    true is the notable state and the tick means "this row is one of those". Sorting or
    filtering on a column where true means nothing is wrong is a trap.
    """
    return [{**row,
             "missing": not row.get("available", True),
             "author": ", ".join(row.get("authors") or []),
             # One field per feature: a grid column reads a field, and the payload's
             # nested dict would have every column reaching into the same object.
             # `.get` rather than a default of False - a table nobody parsed answers
             # null for all seven, and inventing False here would lose that.
             **{f"feature_{key}": (row.get("features") or {}).get(key)
                for key in table_features.LABELS},
             # The word, not the flag, and always one of the two on the table that is
             # the default. Blanking it where a game has one table made "not
             # applicable" a third state read from an empty cell - and a column that
             # is sometimes populated cannot be sorted or filtered on.
             "default_state": (game_tables.default_state(row.get("default_kind") or "")
                               or ("", ""))[0]}
            for row in rows]


def build_tables(rows: list[dict[str, Any]], library: Any,
                 on_select: Callable[[dict | None], None],
                 state: dict[str, Any] | None = None,
                 rerender: Callable[[], None] | None = None) -> None:
    """The library seen by launchable file rather than by folder.

    Its own builder rather than a branch inside the games grid: the columns, the views
    and the row identity are all different, and the two sharing one function would be a
    long argument about which subject each line is for.
    """
    state = state if state is not None else {}
    built = table_rows(rows)
    fields = [definition["field"] for definition in TABLE_COLUMNS]

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 hub-panel"):
        _subject_select(state, rerender, state.get("subject", "table"))
        search = ui.input(placeholder="Search tables") \
            .props("dense outlined clearable").classes("w-64")
        wire_views, view_picker = view_control(library, f"{SCOPE}.tables",
                                               TABLE_VIEWS, fields, TABLE_COLUMNS)
        ui.space()
        # Every glyph column carries a legend (HUBUI section 6), including the state
        # drawn as nothing, which is the one a reader is least able to work out from
        # the grid. The states this library actually has, though: a table is unparsed
        # only between discovery finding it and the enrichment job reaching it, so a
        # line explaining a mark nobody can see is spent on every visit for a window
        # most people never look through.
        with ui.row().classes("items-center gap-3 no-wrap text-xs opacity-60 "
                              "hub-tier-key") as legend:
            for key in table_features.states_in(built):
                state = table_features.state_for(key)
                with ui.row().classes("items-center gap-1 no-wrap").tooltip(state.why):
                    if state.glyph:
                        ui.label(state.glyph).classes(state.glyph_class)
                    else:
                        ui.element("span").classes(f"hub-mark {state.mark}".strip()
                                                   if state.mark else "hub-mark-none")
                    ui.label(state.noun)
        legend.bind_visibility_from(view_picker, "value",
                                    lambda value: value == "builtin:Features")
        ui.label(f"{len(built)} tables in {len({r['game_id'] for r in built})} games") \
            .classes("text-xs hub-label")

    # The workbench follows the focused row, the same way it does under Games - focus
    # rather than selection, so arrowing down the list is a sweep and the checkboxes
    # stay whatever a bulk action left them.
    by_id = {row["id"]: row for row in built}
    async def rate_row(event) -> None:
        """Set a rating from the stars, and redraw the one row that changed.

        A whole-grid refresh would cost the scroll position and the selection for one
        number - and the row is the only thing that knows it changed.
        """
        args = event.args if isinstance(event.args, dict) else {}
        game_id, table_id = str(args.get("game") or ""), str(args.get("table") or "")
        value = int(args.get("value") or 0)
        if not game_id:
            return
        client = HubClient()
        try:
            if table_id:
                await run.io_bound(client.rate_table, game_id, table_id, value)
            else:
                await run.io_bound(client.rate, game_id, value)
        except Exception as exc:
            ui.notify(f"Could not save that rating: {exc}", type="negative")
            return
        row = by_id.get(table_id or game_id)
        if row is not None:
            row["rating"] = value
            table.run_grid_method("applyTransaction", {"update": [row]})

    ui.on("hub_row_focus",
          lambda event: on_select(by_id.get(grid.focused_row(event))))
    ui.on("hub_rate", rate_row)
    ui.run_javascript(_STARS_JS)

    row_menu: dict[str, Any] = {}

    def on_context(row: dict | None) -> None:
        # The menu acts on the row under the cursor, not on the selection. Conflating
        # the two is how people act on the wrong thing.
        row_menu["row"] = row
        _fill(row)

    async def on_header_context(col_id: str | None) -> None:
        # Asked of the grid rather than tracked here: the column can also be dragged in
        # and out of the pinned area, and a local flag would then be wrong.
        state_now = await table.run_grid_method("getColumnState") or []
        entry = next((c for c in state_now if c.get("colId") == col_id), {})
        _fill(None, col_id=col_id, pinned=bool(entry.get("pinned")))

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table = grid.build(TABLE_COLUMNS, built, f"{SCOPE}.tables", on_select,
                           on_context, on_header_context)
        menu = ui.context_menu()

    async def act(what: Callable, *args: Any, said: str = "",
                  row: dict[str, Any] | None = None, gone: bool = False) -> None:
        """Run one row-menu act, then put only what changed back on screen.

        Rebuilding the page was the whole answer here, and it reads as the grid
        flashing: scroll position, focus and the open panel all go, for a write that
        touched one game's rows. `getRowId` is already the row's id - section 6 has it
        so selection survives a refresh - which is exactly what a transaction needs.

        The whole game's rows, not the one acted on: a default moves, so the row that
        held it stops being the default in the same write.
        """
        try:
            await run.io_bound(what, *args)
        except Exception as exc:
            ui.notify(f"Could not do that: {exc}", type="negative")
            return
        ui.notify(said, type="positive")
        game_id = str((row or {}).get("game_id") or "")
        if not game_id:
            if rerender is not None:
                rerender()
            return

        # From the by-file lens, which is what the grid was built from. The game's own
        # sub-resource describes a table and not where it sits in a library, so it
        # carries no game name, manufacturer, year or resolved rom - patching from it
        # blanked four columns on exactly the rows that had just been acted on.
        rows_now = await run.io_bound(library.load_tables)
        fresh = table_rows([item for item in rows_now
                            if item.get("game_id") == game_id])
        if gone:
            table.run_grid_method("applyTransaction", {"remove": [{"id": row["id"]}]})
            by_id.pop(row["id"], None)
        by_id.update({item["id"]: item for item in fresh})
        if fresh:
            table.run_grid_method("applyTransaction", {"update": fresh})
        # The panel is about one of these rows and would otherwise still show what the
        # write changed. `on_select` redraws the workbench alone, not the page.
        answer = on_select(None if gone else by_id.get(row["id"]))
        if inspect.isawaitable(answer):
            await answer

    def _fill(row: dict | None, col_id: str | None = None,
              pinned: bool = False) -> None:
        """One menu, filled for whatever was right-clicked.

        Two menus cannot both hang off the grid wrapper, and the wrapper sees every
        right-click - so the header's entries and the row's share this one.
        """
        menu.clear()
        with menu:
            if col_id and not col_id.startswith("ag-Grid-"):
                header = next((definition.get("headerName")
                               for definition in TABLE_COLUMNS
                               if definition.get("field") == col_id), col_id)
                ui.item_label(str(header).replace("\n", " ")).props("header") \
                    .classes("hub-menu-header")
                ui.separator()
                # One entry that says what it will do, rather than two where one is
                # always a no-op.
                ui.menu_item(
                    "Unpin" if pinned else "Pin left",
                    lambda c=col_id, p=pinned: table.run_grid_method(
                        "applyColumnState",
                        {"state": [{"colId": c, "pinned": None if p else "left"}]})) \
                    .classes("hub-menu-item")
                ui.menu_item("Hide column",
                             lambda c=col_id: table.run_grid_method(
                                 "setColumnsVisible", [c], False)) \
                    .classes("hub-menu-item")
            elif row:
                ui.item_label(_table_label(row)).props("header") \
                    .classes("hub-menu-header")
                ui.separator()
                # Managed here, where every candidate for the game is visible at once.
                if not row.get("default"):
                    ui.menu_item(
                        "Make default",
                        lambda r=row: act(library.set_default_table, r["game_id"],
                                          r["id"], said="Now this game's default",
                                          row=r)) \
                        .classes("hub-menu-item")
                elif (row.get("default_kind") or "") == game_tables.CHOSEN:
                    # The way back. Clearing the choice does not clear the default - it
                    # becomes automatic, which is what the panel's chip then reads.
                    ui.menu_item(
                        "Clear choice",
                        lambda r=row: act(library.set_default_table, r["game_id"], "",
                                          said="Back to an automatic default",
                                          row=r)) \
                        .classes("hub-menu-item")
                hidden = bool(row.get("hidden"))
                ui.menu_item(
                    "Unhide" if hidden else "Hide",
                    lambda r=row, h=hidden: act(library.set_table_hidden, r["game_id"],
                                                r["id"], not h,
                                                said="Now offered" if h else "Hidden",
                                                row=r)) \
                    .classes("hub-menu-item")
                # Only for a table whose file is gone. While it is on disk the record
                # describes something the user owns, and hiding is what takes it out of
                # play without losing its stats.
                if not row.get("available"):
                    ui.menu_item(
                        "Forget this table",
                        lambda r=row: act(library.forget_table, r["game_id"], r["id"],
                                          said="Record dropped", row=r, gone=True)) \
                        .classes("hub-menu-item")

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


def view_control(library: Any, scope: str, presets: dict[str, list[str]],
                 all_fields: list[str], columns: list[dict[str, Any]]):
    """One control for how the rows are presented: which view, and what is in it.

    Built here in the toolbar and wired once the grid exists, because the widgets have
    to sit above the grid and the behavior needs the grid to talk to.

    Returns `(wire, picker)`. Call `wire(table)` once the grid exists; the picker is
    handed back so a caller can hang a binding off which view is showing.
    """
    custom, active = views.stored(library, scope)
    known = views.builtins(presets) + custom
    if active not in {view.id for view in known}:
        active = known[0].id
    held: dict[str, Any] = {"views": known, "active": active, "custom": custom,
                            "modified": False}

    picker = ui.select({view.id: _view_name(view) for view in known}, value=active,
                       label="View").props("dense outlined") \
        .classes("w-52 hub-view-picker")
    # Inside the button, not beside it: a q-menu anchors to its parent, and as a
    # sibling this one anchored to the toolbar row and opened 726px away.
    menu_button = ui.button(icon="more_vert").props("flat dense round size=sm") \
        .tooltip("Columns, and saving this view")
    with menu_button:
        menu = ui.menu()

    def current() -> Any:
        return next(v for v in held["views"] if v.id == held["active"])

    def wire(table: ui.aggrid) -> None:
        async def apply(view: Any) -> None:
            """Put a view on the grid: which columns, sorted how, filtered to what."""
            wanted = [f for f in view.columns if f in all_fields] or all_fields
            table.run_grid_method("setColumnsVisible", wanted, True)
            table.run_grid_method("setColumnsVisible",
                                  [f for f in all_fields if f not in wanted], False)
            # defaultState clears the sort on every column this view does not name,
            # or an old sort would survive a switch and the view would be a lie.
            table.run_grid_method("applyColumnState",
                                  {"state": list(view.sort),
                                   "defaultState": {"sort": None}})
            # Always set, even to nothing: a built-in carries no filters, and clearing
            # them is what makes going back to one a way out rather than a hope.
            table.run_grid_method("setFilterModel", view.filters or None)
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
            shown, sort, model = await _seen()
            view = current()
            changed = views.differs(view, shown, sort, model)
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

        async def save(name: str) -> None:
            shown, sort, model = await _seen()
            view = views.View(id=f"view:{name.strip().lower()}", name=name.strip(),
                              builtin=False, columns=shown,
                              sort=tuple(e for e in sort if e.get("sort")),
                              filters=model)
            held["custom"] = [v for v in held["custom"] if v.id != view.id] + [view]
            held["views"] = views.builtins(presets) + held["custom"]
            held["active"] = view.id
            await keep_views(view.id)
            picker.set_options({v.id: _view_name(v) for v in held["views"]},
                               value=view.id)
            await _refresh()
            ui.notify(f"Saved the view \u201c{view.name}\u201d", type="positive")

        async def delete() -> None:
            view = current()
            if view.builtin:
                return
            held["custom"] = [v for v in held["custom"] if v.id != view.id]
            held["views"] = views.builtins(presets) + held["custom"]
            held["active"] = held["views"][0].id
            await keep_views(held["active"])
            picker.set_options({v.id: _view_name(v) for v in held["views"]},
                               value=held["active"])
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
                ui.menu_item("Save as\u2026", lambda: _ask_name(save)) \
                    .classes("hub-menu-item")
                # Only where they mean something: there is nothing to revert to until
                # the screen has drifted, and nothing to delete unless it is the
                # user's own view.
                if held["modified"]:
                    ui.menu_item("Revert", lambda: apply(current())) \
                        .classes("hub-menu-item")
                if not view.builtin and not held["modified"]:
                    ui.menu_item("Delete view", delete) \
                        .classes("hub-menu-item hub-menu-danger")
                ui.separator()
                # An explicit column: the menu lays its children out inline otherwise,
                # so twenty checkboxes wrap into a paragraph rather than a list.
                with ui.column().classes("gap-0 w-full py-1 items-stretch"):
                    for heading, group in _by_group(columns):
                        # Named groups only. A grid whose columns declare none reads
                        # as one list, which is right when there are eight of them.
                        if heading:
                            ui.item_label(heading).props("header") \
                                .classes("hub-menu-header")
                        for definition in group:
                            field = definition["field"]
                            label = str(definition.get("headerName") or field) \
                                .replace("\n", " ")
                            ui.checkbox(label, value=field not in hidden,
                                        on_change=lambda event, f=field:
                                        table.run_grid_method("setColumnsVisible",
                                                              [f], event.value)) \
                                .props("dense").classes("hub-menu-item w-full")

        menu_button.on_click(fill_menu)
        picker.on_value_change(lambda event: pick(event.value))
        # The grid reports its own changes; the marker follows them rather than being
        # recomputed on a timer that would outlive the grid.
        for event in ("columnVisible", "sortChanged", "filterChanged"):
            table.on(event, lambda: _refresh(), args=[])
        ui.timer(0, lambda: apply(current()), once=True)

    return wire, picker


def _view_name(view: Any) -> str:
    """Whatever it is called. A name somebody typed is shown as they typed it - the
    built-ins come first in the list and only a view of theirs offers to be deleted,
    which is enough to tell them apart without editing anybody's words."""
    return view.name


def _ask_name(save) -> None:
    with ui.dialog() as dialog, ui.card():
        ui.label("Save this view as").classes("hub-card-title")
        # debounce=0 so the model is current the moment Save is pressed. Focus is put
        # here by the script below - Quasar's autofocus does not land in this dialog.
        name = ui.input(placeholder="Name this view") \
            .props("outlined dense debounce=0").classes("w-72")

        async def keep() -> None:
            if not (name.value or "").strip():
                # Said rather than ignored. A dialog that does nothing when you press
                # the button reads as broken, and this one did.
                name.props('error error-message="Give it a name"')
                return
            dialog.close()
            await save(name.value)

        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            save_button = ui.button("Save", on_click=keep).props("no-caps")
    # Focused when Quasar says the dialog has finished opening. Anything earlier is
    # overridden by its own focus handling, whatever the delay.
    dialog.on("show", lambda: ui.run_javascript(
        f"document.getElementById('c{name.id}').focus()"))
    dialog.open()
    # Enter is bound in the browser rather than through an event handler: nicegui does
    # not forward a keyup from a Quasar input inside a dialog, so nothing arrives to
    # handle. Clicking the button is the same path the mouse takes, which is the point.
    ui.run_javascript(f"""
        (() => {{
          // The dialog mounts after this runs, so the elements are waited for rather
          // than assumed. Bounded, because a dialog that never appears must not leave
          // a timer running behind it.
          let tries = 0;
          const wire = () => {{
            const field = document.getElementById('c{name.id}');
            const button = document.getElementById('c{save_button.id}');
            if (!field || !button) {{
              if (++tries < 40) setTimeout(wire, 25);
              return;
            }}
            // On the dialog, not the field: Quasar's autofocus does not land, so
            // focus can be on the dialog itself when the first key arrives and a
            // listener on the input would never hear it.
            const dialog = button.closest('.q-dialog') || field;
            dialog.addEventListener('keyup', (event) => {{
              if (event.key === 'Enter') button.click();
            }});

          }};
          wire();
        }})()
    """)


def _subject_stub(subject: str) -> None:
    with ui.column().classes("w-full items-start gap-2 p-6"):
        ui.label(SUBJECTS.get(subject, subject)).classes("hub-card-title")
        ui.label(SUBJECT_STUBS.get(subject, "")).classes("hub-help")
        ui.label("Not built. The grid, the views and the details pane are the same "
                 "machinery - what a new subject needs is a field registry entry and a "
                 "reader, not a new page.").classes("hub-help mt-2 opacity-70")


def _subject_select(state: dict[str, Any], rerender: Callable[[], None] | None,
                    subject: str) -> None:
    def pick(value: str) -> None:
        state["subject"] = value
        if rerender is not None:
            rerender()

    # "Rows" rather than "Show", which was a synonym of the View control beside it.
    ui.select(SUBJECTS, value=subject, label="Rows",
              on_change=lambda e: pick(e.value)) \
        .props("dense outlined").classes("w-40")
