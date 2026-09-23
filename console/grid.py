"""Grids, and the column layout kept for each.

Layout only - width, order, pinning. Which columns are shown, how they are
sorted and what is filtered belong to a view; see console/views.py.
"""

from __future__ import annotations

import inspect
import json
import logging
import weakref
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import i18n
from common.i18n import t
from console import offload, renderers

logger = logging.getLogger("vpinfe.console.grid")

DEFAULT_COL_DEF: dict[str, Any] = {
    "sortable": True,
    "resizable": True,
    "filter": True,
    "minWidth": 60,
    # Lets a header carrying a newline take the second line it needs.
    "autoHeaderHeight": True,
}

# AG Grid's own column state is the stored payload: width, order, visibility, sort, pin.
# Layout belongs to the *view*, not to the grid: a tick column wants to be narrow and a
# name column wants to be wide, and they are the same column under two views. Visibility,
# sort and filters are the view's too - what keeps a built-in a constant is that none of
# it is stored against the built-in's definition. See console/views.py.
_SAVE_EVENTS = ("columnMoved", "columnResized", "columnPinned")
_LAYOUT_FIELDS = ("colId", "width", "flex", "pinned")


# Chrome measured at 50px, plus the 8px gap the theme puts between a header and its
# filter icon; 9px/char is the widest average in the header font, so a header never has
# to wrap. Counted here because a gap the width does not know about is a gap that
# squeezes the text it was added to protect.
_HEADER_CHROME_PX = 66
_HEADER_CHAR_PX = 9


def header_width(header: str) -> int:
    """The narrowest this column can be and still show its header in full.

    Measured per line: a header broken over two lines needs the width of its longest
    line, not of the whole string.
    """
    longest = max((len(line) for line in header.split("\n")), default=0)
    # No header, no floor: a column of pictures carries no text, no sort arrow and no
    # filter button, so charging it for their chrome makes it wider than it needs.
    return longest * _HEADER_CHAR_PX + _HEADER_CHROME_PX if longest else 0


# A picker in the funnel, where AG Grid's text box would be: on a column of marks that
# box asks the reader to know the word behind a circle, and on a boolean it offers
# "Choose one / True / False". The set filter that would fix it is Enterprise; a custom
# filter is not, and community takes any class implementing the interface.
#
# `choices` is [{value, label, mark, repeat}], the value being what the cell holds - so
# a blank cell is a choice like any other rather than the one state a filter cannot
# express.
CHOICE_FILTER = "window.HubChoiceFilter"
_FILTER_THIS_LIST = t("console.grid.filter_this_list")

_CHOICE_FILTER_JS = """
if (!window.HubChoiceFilter) {
  window.HubChoiceFilter = class {
    init(params) {
      this.params = params;
      this.picked = new Set();
      this.gui = document.createElement('div');
      this.gui.className = 'console-filter';
      this.draw(params.choices || []);
    }
    draw(choices) {
      this.gui.replaceChildren();
      this.boxes = new Map();
      this.rows = new Map();
      this.counts = new Map();
      this.labels = new Map();
      // A list past this is read by typing, not by scrolling. Below it a box to type in
      // is one more thing to look at for no gain.
      if (choices.length > 8) {
        const search = document.createElement('input');
        search.type = 'text';
        search.className = 'console-filter-search';
        search.placeholder = (this.params.words || {}).search || '';
        search.addEventListener('input', () => {
          const said = search.value.trim().toLowerCase();
          for (const [value, row] of this.rows) {
            const label = String(this.labels.get(value) || '').toLowerCase();
            // A picked choice stays visible whatever is typed: hiding it would leave a
            // filter in force with nothing on screen saying so.
            row.hidden = said && !label.includes(said) && !this.picked.has(value);
          }
        });
        this.gui.appendChild(search);
      }
      for (const choice of choices) {
        const row = document.createElement('label');
        row.className = 'console-filter-row';
        if (choice.tip) row.title = choice.tip;
        const box = document.createElement('input');
        box.type = 'checkbox';
        box.checked = this.picked.has(choice.value);
        box.addEventListener('change', () => {
          box.checked ? this.picked.add(choice.value) : this.picked.delete(choice.value);
          this.params.filterChangedCallback();
        });
        row.appendChild(box);
        // One leading slot, always, so an item that draws nothing indents to where the
        // marks are and every label starts on the same edge. `docs/conventions.md`.
        const slot = document.createElement('span');
        slot.className = 'console-filter-mark';
        // `repeat` draws the mark more than once, which is how a rating says three
        // rather than saying "3" beside a picture of one star.
        for (let n = 0; n < (choice.mark ? (choice.repeat || 1) : 0); n++) {
          const mark = document.createElement('span');
          mark.className = choice.mark;
          slot.appendChild(mark);
        }
        // A state drawn as a character rather than a shape - presence is a tick here.
        if (choice.glyph) {
          const tick = document.createElement('span');
          tick.className = choice.glyphClass || 'console-tick';
          tick.textContent = choice.glyph;
          slot.appendChild(tick);
        }
        row.appendChild(slot);
        const word = document.createElement('span');
        word.textContent = choice.label;
        row.appendChild(word);
        const tally = document.createElement('span');
        tally.className = 'console-filter-count';
        row.appendChild(tally);
        this.counts.set(choice.value, tally);
        this.labels.set(choice.value, choice.label);
        this.boxes.set(choice.value, box);
        this.rows.set(choice.value, row);
        this.gui.appendChild(row);
      }
    }
    // What a row is counted under and matched on. A cell with nothing in it is the
    // "missing" choice, whose value is "".
    buckets(node) {
      const held = this.params.getValue(node);
      return [held === null || held === undefined ? '' : held];
    }
    // How big the bucket is, over the whole library rather than over what the other
    // filters have left: a number that moved every time something else was picked would
    // be a different fact under the same label.
    tally() {
      if (!this.params.api || !this.counts.size) return;
      const seen = new Map();
      this.params.api.forEachNode(node => {
        for (const key of new Set(this.buckets(node))) seen.set(key, (seen.get(key) || 0) + 1);
      });
      for (const [value, el] of this.counts) {
        const n = seen.get(value) || 0;
        el.textContent = n ? String(n) : '';
      }
    }
    afterGuiAttached() { this.tally(); }
    getGui() { return this.gui; }
    isFilterActive() { return this.picked.size > 0; }
    doesFilterPass(params) {
      return this.buckets(params.node).some(key => this.picked.has(key));
    }
    getModel() { return this.picked.size ? {values: [...this.picked]} : null; }
    setModel(model) {
      this.picked = new Set((model && model.values) || []);
      for (const [value, box] of this.boxes) box.checked = this.picked.has(value);
    }
  };
}
if (!window.HubListFilter) {
  // For a cell holding a list; "" is the row that holds nothing.
  window.HubListFilter = class extends window.HubChoiceFilter {
    init(params) {
      this.all = false;
      window.HubListFilter.made = (window.HubListFilter.made || 0) + 1;
      this.group = 'console-filter-mode-' + window.HubListFilter.made;
      super.init(params);
    }
    buckets(node) {
      const held = this.params.getValue(node);
      return Array.isArray(held) && held.length ? held : [''];
    }
    // Read again at every opening, so a value given a minute ago is a choice. A picked
    // value nothing holds any more stays one, or the filter would be in force unseen.
    present() {
      const looks = (window.__vpinfeChipLooks || {})[this.params.looks] || (() => ({}));
      const seen = new Set([...this.picked].filter(value => value !== ''));
      this.params.api.forEachNode(node => {
        for (const value of this.buckets(node)) if (value !== '') seen.add(value);
      });
      return [...[...seen].sort(__ORDER__).map(value => {
        const look = looks(value) || {};
        return {value: value, label: value, mark: look.dot || '', glyph: look.mark || '',
                glyphClass: __MARK_CLASS__, tip: look.tip || ''};
      }), {value: '', label: (this.params.words || {}).none || ''}];
    }
    draw(choices) {
      super.draw(choices);
      const words = this.params.words || {};
      const mode = document.createElement('div');
      mode.className = 'console-filter-mode';
      this.modes = [[false, words.any], [true, words.all]].map(([all, said]) => {
        const label = document.createElement('label');
        const radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = this.group;
        radio.checked = this.all === all;
        radio.addEventListener('change', () => {
          this.all = all;
          if (this.picked.size) this.params.filterChangedCallback();
        });
        label.append(radio, document.createTextNode(said || ''));
        mode.appendChild(label);
        return [all, radio];
      });
      this.gui.prepend(mode);
    }
    afterGuiAttached() {
      this.draw(this.present());
      this.tally();
    }
    doesFilterPass(params) {
      const held = this.buckets(params.node);
      const wanted = [...this.picked];
      return this.all ? wanted.every(value => held.includes(value))
                      : wanted.some(value => held.includes(value));
    }
    getModel() {
      if (!this.picked.size) return null;
      const model = {values: [...this.picked].sort(__ORDER__)};
      if (this.all) model.all = true;
      return model;
    }
    setModel(model) {
      super.setModel(model);
      this.all = Boolean(model && model.all);
      for (const [all, radio] of this.modes || []) radio.checked = this.all === all;
    }
  };
}
""".replace("__ORDER__", renderers.ORDER).replace("__MARK_CLASS__",
                                                   json.dumps(renderers.MARK_CLASS))


def install_filters() -> None:
    """Put the filter components on the page. Once per page, before any grid is built."""
    ui.add_body_html(f"<script>{_CHOICE_FILTER_JS}</script>")


def choice_filter(choices: list[dict[str, Any]], *,
                  formatted: bool = False) -> dict[str, Any]:
    """Column options that filter by picking a state rather than by typing one.

    The cell holds the value, not the label - a filter matches on what the row says and
    a saved view records that, so the stored token must not move when the language
    does. `valueFormatter` is what puts the label on screen.

    `formatted=True` where the column writes its own: a tick column formats a boolean
    and would collide with one written here.
    """
    # Only a string value is a token with a word for it. A boolean or a number is the
    # cell's own content and the column formats it - keying this on `str(True)` built a
    # map a JavaScript `true` never matched, and it landed *after* the column's own
    # formatter in the dict, so every tick column printed `true`/`false`.
    shown = {} if formatted else {
        one["value"]: str(one.get("label"))
        for one in choices
        if isinstance(one.get("value"), str) and one["value"]
        and str(one.get("label") or "") != one["value"]}
    out: dict[str, Any] = {":filter": CHOICE_FILTER,
                           "filterParams": {"choices": choices,
                                            "words": {"search": _FILTER_THIS_LIST}}}
    if shown:
        out[":valueFormatter"] = (
            f"params => ({json.dumps(shown)})[params.value] ?? params.value")
    return out


LIST_FILTER = "window.HubListFilter"

# The grid turns a descending result round itself, so an empty row answers the other way
# round there to stay last.
LIST_COMPARATOR = (
    "(a, b, nodeA, nodeB, descending) => {"
    f" const order = {renderers.ORDER};"
    " const drawn = v => (Array.isArray(v) ? [...v] : []).sort(order);"
    " const x = drawn(a), y = drawn(b);"
    " if (!x.length || !y.length) {"
    "  if (x.length === y.length) return 0;"
    "  const last = x.length ? -1 : 1;"
    "  return descending ? -last : last; }"
    " for (let i = 0; i < Math.min(x.length, y.length); i++) {"
    "  const said = order(x[i], y[i]); if (said) return said; }"
    " return x.length - y.length; }"
)

_LIST_WORDS = {"none": t("word.none"), "any": t("console.grid.any_of"),
               "all": t("console.grid.all_of"), "search": _FILTER_THIS_LIST}


def list_column(field: str, header: str, width: int = 0, help: str = "", *,
                looks: str = "", **extra: Any) -> dict[str, Any]:
    """A column whose row holds a list under `field`: drawn as chips, filtered by the
    values the rows hold, sorted by the first chip as drawn.

    `looks` names where a chip takes its looks from, one of `renderers.LOOKS`; empty
    draws the word alone.
    """
    return column(field, header, width, help,
                  **renderers.drawable("chips", looks=looks),
                  **{":filter": LIST_FILTER,
                     "filterParams": {"looks": looks, "words": _LIST_WORDS},
                     ":comparator": LIST_COMPARATOR,
                     ":getQuickFilterText": "params => (params.value || []).join(' ')",
                     ":valueFormatter": "params => (params.value || []).join(', ')"},
                  **extra)


def on_row_focus(scope: str, handler: Callable[[Any], Any]) -> None:
    """Call `handler` for focus events from this grid, and no other."""
    held = _row_focus_handlers()
    held[scope] = handler
    if held.get("__listening__") is None:
        held["__listening__"] = True

        def dispatch(event: Any) -> Any:
            args = event.args if isinstance(event.args, dict) else {}
            mine = _row_focus_handlers().get(str(args.get("scope") or ""))
            return mine(event) if mine is not None else None

        ui.on("hub_row_focus", dispatch)


# Weak, so a client that has gone takes its handlers with it.
_ROW_FOCUS: weakref.WeakKeyDictionary[Any, dict[str, Any]] = weakref.WeakKeyDictionary()


def _row_focus_handlers() -> dict[str, Any]:
    return _ROW_FOCUS.setdefault(ui.context.client, {})


def focused_row(event: Any) -> str:
    """The row id out of a focus event, and `focused_column` the column it landed in.

    The column travels with it because a cell is a more specific place than a row: the
    Games grid opens the workbench on the part of the game the column is about. Older
    payloads were the bare id, so both read either shape.
    """
    args = event.args
    return str((args.get("id") if isinstance(args, dict) else args) or "")


def focused_column(event: Any) -> str:
    args = event.args
    return str((args.get("col") if isinstance(args, dict) else "") or "")


def replace_rows(table: Any, held: list[dict[str, Any]], by_id: dict[str, Any],
                 fresh: list[dict[str, Any]], belongs: Callable[[dict], bool]) -> None:
    """Swap the rows `belongs` picks for `fresh` in one transaction, so what stayed keeps
    its place, focus and selection while what was added or went away does."""
    old = [row for row in held if belongs(row)]
    old_ids = {row["id"] for row in old}
    fresh_ids = {row["id"] for row in fresh}
    held[:] = [row for row in held if not belongs(row)] + fresh
    for row in old:
        by_id.pop(row["id"], None)
    by_id.update({row["id"]: row for row in fresh})
    table.run_grid_method("applyTransaction", {
        "remove": [{"id": row["id"]} for row in old if row["id"] not in fresh_ids],
        "update": [row for row in fresh if row["id"] in old_ids],
        "add": [row for row in fresh if row["id"] not in old_ids]})


def two_line(header: str) -> str:
    """Break the last word onto its own line, so a long header stays a narrow column."""
    words = header.split()
    return header if len(words) < 2 else " ".join(words[:-1]) + "\n" + words[-1]


def column(field: str, header: str, width: int = 0, help: str = "",
           **extra: Any) -> dict[str, Any]:
    """A column sized to fit, which is its header unless the content needs more.

    **Omit `width`.** Pass one only where the values are longer than the header - a
    title, an author, a filename - and it is a floor, not a target. Hand-picking every
    width makes a column of one-digit counts as wide as somebody guessed rather than as
    wide as it needs to be. Dragging narrower still works, and what the user drags to is
    what persists.

    Every multi-word header wraps, here rather than at each call site: applied per call
    site it reaches only the generated columns, and `Table Count` sits on one line beside
    media headers that do not.
    """
    header = two_line(header)
    # `help` earns its place only where the header does not already say it. What the
    # column is, and what its values mean - a line that restates the header is a
    # tooltip charged for nothing.
    tip = {"headerTooltip": help} if help else {}
    return {"field": field, "headerName": header,
            "width": max(width, header_width(header))} | tip | extra


# `console-base.css` colors this class.
IDENTIFIER_CLASS = "console-cell-identifier"


SUBTITLE_CLASS = "console-cell-said"
TWO_LINE_CLASS = "console-cell-two-line"
PICTURED_CLASS = "console-cell-art-lead"
ONE_LINE_ROW_PX = 42
TWO_LINE_ROW_PX = 56
PICTURED_ROW_PX = 88
_ROW_CLASS = {TWO_LINE_ROW_PX: "console-grid-two-line", PICTURED_ROW_PX: "console-grid-pictured"}

_SUBTITLE_RENDERER = (
    "params => {"
    " const d = params.data || {};"
    " const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')"
    ".replace(/\"/g, '&quot;');"
    " const made = d['{made}'] || '';"
    " const built = {built};"
    " const name = params.valueFormatted != null ? params.valueFormatted"
    " : (params.value == null ? '' : params.value);"
    " let said = '';"
    " if (made) said += '<span class=\"console-cell-made\">' + esc(made) + '</span>';"
    " if (made && built) said += '<span class=\"console-cell-join\"> \u00b7 </span>';"
    " if (built) said += '<span class=\"console-cell-built\">' + esc(built) + '</span>';"
    " const href = d['{link}_href'] || '';"
    " const named = href ? '<a class=\"console-link\" href=\"' + esc(href) + '\" title=\"'"
    " + esc(d['{link}_tip'] || '') + '\">' + esc(name) + '</a>' : esc(name);"
    " const lines = '<span class=\"console-cell-named\">' + named"
    " + '</span><span class=\"{cls}\">' + said + '</span>';"
    " const art = {picture};"
    " if (art === null) return lines;"
    " const shown = art ? '<img loading=\"lazy\" alt=\"\" src=\"' + esc(art) + '\">'"
    " : '<i class=\"material-icons console-cell-noart\">image_not_supported</i>';"
    " return '<span class=\"console-cell-pictured\"><span class=\"console-cell-art-box\">'"
    " + shown + '</span><span class=\"console-cell-lines\">' + lines + '</span></span>'; }"
)


def identifier(field: str, header: str, width: int = 0, help: str = "",
               subtitle: str | tuple[str, str, str] = "", link: str = "",
               picture: str = "", **extra: Any) -> dict[str, Any]:
    """The column this grid's rows are scanned *by*, which is not their unique key.

    Exactly one per grid; `build` refuses anything else.

    `subtitle` names the field holding the line drawn under the value, or a
    `(made, "", built)` triple where the line has two parts to tell apart. Sorting and
    filtering stay on `field`, so the line is shown and never scanned.

    `link` makes the value an anchor on rows carrying `<link>_href`, titled `<link>_tip`.
    `picture` names the field holding an image address drawn ahead of both lines. Both
    need a subtitle to be drawn.
    """
    extra_classes = extra.pop("cellClass", "")
    classes = f"{extra_classes} {IDENTIFIER_CLASS}".strip() if extra_classes \
        else IDENTIFIER_CLASS
    if subtitle:
        made, _, built = (subtitle if isinstance(subtitle, tuple)
                          else (subtitle, "", ""))
        classes = f"{classes} {TWO_LINE_CLASS}" + (f" {PICTURED_CLASS}" if picture else "")
        extra.setdefault(":cellRenderer", _SUBTITLE_RENDERER
                         .replace("{picture}", f"(d['{picture}'] || '')" if picture else "null")
                         .replace("{link}", link or "_")
                         .replace("{made}", made)
                         .replace("{built}", f"d['{built}'] || ''" if built else "''")
                         .replace("{cls}", SUBTITLE_CLASS))
    return column(field, header, width, help, cellClass=classes, **extra)


# Ours, not AG Grid's: what the picker calls a column that draws no header of its own.
# Without it the picker falls back to the field name and prints `icon`.
PICKER_KEY = "picker"


# Ours, not AG Grid's: it names the group a column sits under in the column picker.
# Carried on the definition so the list that declares the columns also declares their
# order and their grouping, and stripped before the defs reach the grid.
GROUP_KEY = "group"


def for_grid(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The definitions as AG Grid wants them, without our own keys."""
    return [{k: v for k, v in column.items()
             if k not in (GROUP_KEY, PICKER_KEY, renderers.CHOICES_KEY)}
            for column in columns]


def base_row_px(columns: list[dict[str, Any]]) -> int:
    """The row height the grid's own cells need, before any drawing asks for more."""
    classes = " ".join(str(definition.get("cellClass") or "") for definition in columns)
    if PICTURED_CLASS in classes:
        return PICTURED_ROW_PX
    return TWO_LINE_ROW_PX if TWO_LINE_CLASS in classes else ONE_LINE_ROW_PX


def build(columns: list[dict[str, Any]], rows: list[dict[str, Any]], scope: str,
          # Any, not None: NiceGUI takes a sync or an async handler and so do these,
          # so a coroutine is as valid a return as nothing. Its own Handler type is
          # spelled the same way, for the same reason.
          on_select_rows: Callable[[list[dict[str, Any]]], Any] | None = None,
          on_context: Callable[[dict | None], Any] | None = None,
          on_header_context: Callable[[str | None], Any] | None = None,
          html_fields: list[str] | None = None,
          view_of: Callable[[], str] | None = None,
          rows_without_a_menu: list[str] | None = None) -> ui.aggrid:
    """A grid whose column layout is restored from, and saved to, the API.

    `view_of` names the view showing now. Given one, geometry is stored per view - the
    grid outlives a view change, so without it every view shares one set of widths.

    Raises `ValueError` unless exactly one column is a `grid.identifier()`.
    """
    marked = [definition.get("field") for definition in columns
              if IDENTIFIER_CLASS in str(definition.get("cellClass") or "")]
    if len(marked) != 1:
        raise ValueError(
            f"{scope}: a grid declares exactly one grid.identifier() column, "
            f"the one its rows are scanned by; this one declares {len(marked)}"
            + (f" ({', '.join(str(m) for m in marked)})" if marked else ""))
    grid = ui.aggrid({
        "columnDefs": for_grid(columns),
        "rowData": rows,
        "rowHeight": base_row_px(columns),
        # Which grid a cell belongs to, for a column drawn by name.
        "context": {"scope": scope},
        "defaultColDef": DEFAULT_COL_DEF,
        # Clicking a cell takes focus and nothing else. Click-selection in multiRow
        # mode *replaces* the set, so a cell click would clear every checkbox a bulk
        # action is about to read.
        "rowSelection": {"mode": "multiRow", "checkboxes": True,
                         "headerCheckbox": True, "enableClickSelection": False},
        # The ":" prefix marks this as JavaScript. Without it AG Grid calls a string and
        # the grid dies as an empty table rather than an error.
        ":getRowId": "params => params.data.id",
        # The checkbox belongs to the row, so it stays with the row's left edge.
        "selectionColumnDef": {"pinned": "left"},
        # The workbench follows the focused row, and focus is not selection: arrowing
        # must not disturb the checkboxes a bulk action reads.
        #
        # Marked on every fragment: AG Grid splits a row across the pinned and center
        # containers, each its own .ag-row.
        ":onCellFocused":
            "params => { const r = params.api.getDisplayedRowAtIndex(params.rowIndex); "
            "if (r) emitEvent('hub_row_focus', "
            "{id: r.data.id, col: params.column && params.column.getColId(), "
            f"scope: {json.dumps(scope)}}}); "
            "window.__hubFocusRow = params.rowIndex; "
            "window.__hubMarkFocus && window.__hubMarkFocus(); }",
        # Rows are recycled as you scroll, so the mark rides the wrong row without
        # this.
        ":onBodyScroll": "() => { window.__hubMarkFocus && window.__hubMarkFocus(); }",
        # AG Grid's own words - the filter menu on every column, "No Rows To Show", the
        # column menu. Empty in English, where its built-ins are already right.
        **({"localeText": grid_locale} if (grid_locale := i18n.under("grid")) else {}),
        "suppressDragLeaveHidesColumns": True,
        "animateRows": False,
        # False deliberately: preventing the default stops the event reaching Quasar,
        # and ui.context_menu never opens.
        "preventDefaultOnContextMenu": False,
    }, html_columns=[i for i, d in enumerate(columns)
                     if d["field"] in (html_fields or [])],
        theme="quartz",
        # nicegui defaults this True, which fits columns to the grid width and so
        # overrides both the declared widths and any the user saved.
        auto_size_columns=False,
    ).classes(f"w-full grow min-h-0 {_ROW_CLASS.get(base_row_px(columns), '')}".strip())

    ui.run_javascript(
        f"if (window.__hubFocusScope !== {json.dumps(scope)}) {{"
        f" window.__hubFocusScope = {json.dumps(scope)};"
        " window.__hubFocusRow = null; }")
    # Installed once per page. Idempotent, so a second grid does not stack it.
    ui.run_javascript("""
    window.__hubMarkFocus = () => {
      const i = window.__hubFocusRow;
      document.querySelectorAll('.ag-row.console-row-focus')
        .forEach(e => e.classList.remove('console-row-focus'));
      if (i === undefined || i === null) return;
      document.querySelectorAll(`.ag-row[row-index="${i}"]`)
        .forEach(e => e.classList.add('console-row-focus'));
    };
    """)
    renderers.install()
    _restore(grid, scope, columns, view_of)
    _save_on_change(grid, scope, view_of)
    if on_select_rows is not None:
        async def changed() -> None:
            rows = await grid.get_selected_rows()
            # The count only; the focused row owns which game is on screen.
            result = on_select_rows(rows)
            if inspect.isawaitable(result):
                await result

        # Queried, not read off rowSelected: that payload can fail to serialize and its
        # `selected` field arrives undefined.
        grid.on("selectionChanged", changed)
    if on_context is not None:
        # Only `data`: the full payload can fail to serialize and is then never sent.
        grid.on("cellContextMenu",
                lambda event: on_context((event.args or {}).get("data")), args=["data"])
    if on_header_context is not None:
        # Fires in Community and carries colId. The native column menu is Enterprise.
        grid.on("columnHeaderContextMenu",
                lambda event: on_header_context((event.args or {}).get("colId")),
                args=["colId"])
    _suppress_empty_menu(grid, rows=on_context is not None,
                         headers=on_header_context is not None,
                         without=rows_without_a_menu)
    return grid


def _suppress_empty_menu(grid: Any, *, rows: bool, headers: bool,
                         without: list[str] | None = None) -> None:
    """Stop a right-click with nothing behind it from opening this grid's menu.

    `rows` and `headers` say whether this grid has a menu for each; `without` names the
    row ids that have nothing even where the rest do. Guarded by
    `tests/console/test_context_menus_are_guarded.py`.
    """
    ui.run_javascript(f"""
    (() => {{
      // Retried rather than assumed: this runs while the page is still being built, and
      // an element that is not mounted yet would take the guard silently - which reads
      // exactly like the bug it fixes.
      const install = (tries) => {{
      const found = getElement({grid.id});
      const el = found && found.$el;
      if (!el) {{ if (tries > 0) requestAnimationFrame(() => install(tries - 1)); return; }}
      if (el.__hubMenuGuard) return;
      el.__hubMenuGuard = true;
      el.addEventListener('contextmenu', (event) => {{
        const header = event.target.closest('.ag-header-cell');
        const row = event.target.closest('.ag-row');
        let offer = false;
        if (header) {{
          // AG Grid's own selection column: no name to head a menu, nothing to pin or
          // hide. `column_menu` answers False for it.
          const id = header.getAttribute('col-id') || '';
          offer = {str(headers).lower()} && !id.startsWith('ag-Grid-');
        }} else if (row) {{
          const without = {json.dumps(list(without or []))};
          offer = {str(rows).lower()}
                  && !without.includes(row.getAttribute('row-id') || '');
        }}
        if (!offer) {{
          event.stopPropagation();
        }}
      }}, true);
      }};
      install(60);
    }})()
    """)


async def header_menu(menu: Any, table: Any, columns: list[dict[str, Any]],
                      col_id: str | None) -> None:
    """Fill the menu for a right-click on a column header.

    Whether the column is pinned is asked of the grid rather than tracked beside it: a
    column can also be dragged in and out of the pinned area, and a local flag is then
    wrong.
    """
    state_now: list[dict[str, Any]] = \
        await table.run_grid_method("getColumnState") or []
    entry = next((one for one in state_now if one.get("colId") == col_id), {})
    menu.clear()
    with menu:
        column_menu(menu, table, columns, col_id, bool(entry.get("pinned")))


def column_menu(menu: Any, table: Any, columns: list[dict[str, Any]],
                col_id: str | None, pinned: bool) -> bool:
    """Fill a context menu with what can be done to a column, or answer False.

    The header half of every grid's menu, in one place. Written out per grid, it is how
    one ends up without the pinning every other one has.
    """
    if not col_id or col_id.startswith("ag-Grid-"):
        return False
    header = next((definition.get("headerName") for definition in columns
                   if definition.get("field") == col_id), col_id)
    ui.item_label(str(header).replace("\n", " ")).props("header") \
        .classes("console-menu-header")
    ui.separator()
    # One entry that says what it will do, rather than two where one is always a no-op.
    ui.menu_item(t("word.unpin") if pinned else t("word.pin_left"),
                 lambda: table.run_grid_method(
                     "applyColumnState",
                     {"state": [{"colId": col_id,
                                 "pinned": None if pinned else "left"}]})) \
        .classes("console-menu-item")
    ui.menu_item(t("word.hide_column"),
                 lambda: table.run_grid_method("setColumnsVisible", [col_id], False)) \
        .classes("console-menu-item")
    return True


def layout_scope(scope: str, view_of: Callable[[], str] | None) -> str:
    """Where this grid's geometry lives, which is per view.

    Falls back to the bare scope when no view is known - a grid without views keeps the
    one layout it always had.
    """
    showing = (view_of() if view_of else "") or ""
    return f"{scope}::{showing}" if showing else scope


async def apply_layout(grid: ui.aggrid, scope: str, columns: list[dict[str, Any]],
                       view_of: Callable[[], str] | None = None) -> None:
    """Put the showing view's geometry on the grid.

    Called on gridReady and again on every view change, because the grid outlives a
    view: switching without this leaves the last view's widths on the new one's columns.
    """
    from console.api import ApiClient

    where = layout_scope(scope, view_of)
    try:
        held = await offload.io(ApiClient().preferences, where)
        stored = (held or {}).get("columns")
    except Exception:
        logger.warning("console: could not read column state for %s", where, exc_info=True)
        return
    # Only the layout fields, in as well as out: a payload written before views existed
    # carries `hide`, which would override the view.
    saved = {entry["colId"]: {k: entry[k] for k in _LAYOUT_FIELDS if k in entry}
             for entry in (stored or []) if entry.get("colId")}
    # Every column this grid has gets a definite width, not only the ones with one
    # stored: a view with no geometry of its own must go back to the definitions rather
    # than keep the last view's. `defaultState: {"width": None}` reads as if it would do
    # this and does not - a widened column survives the switch.
    #
    # Pinning is deliberately not reset. It is set by the column definition rather than
    # by a layout, and forcing it here unpins the selection column.
    state = []
    for definition in columns:
        field_id = definition["field"]
        want = dict(saved.get(field_id) or {})
        want.setdefault("colId", field_id)
        want.setdefault("width", definition.get("width"))
        if want.get("width") is None:
            want.pop("width", None)
        state.append(want)
    # Ordered only where the view has an order of its own; otherwise the definitions'.
    grid.run_grid_method("applyColumnState",
                         {"state": state, "applyOrder": bool(saved)})


def _restore(grid: ui.aggrid, scope: str, columns: list[dict[str, Any]],
             view_of: Callable[[], str] | None) -> None:
    # gridReady rather than a timer: a timer outlives the grid when the view changes,
    # and firing under a cleared container raises "parent slot has been deleted".
    grid.on("gridReady", lambda: apply_layout(grid, scope, columns, view_of))


def _save_on_change(grid: ui.aggrid, scope: str,
                    view_of: Callable[[], str] | None) -> None:
    from console.api import ApiClient

    async def save() -> None:
        where = layout_scope(scope, view_of)
        try:
            state = await grid.run_grid_method("getColumnState")
            # Stripped to the layout: storing `hide` or `sort` would make a built-in
            # drift, which is the one thing it must never do.
            layout = [{k: entry[k] for k in _LAYOUT_FIELDS if k in entry}
                      for entry in (state or [])]
            await run.io_bound(ApiClient().put_preferences, where, {"columns": layout})
        except TimeoutError:
            # The browser did not answer in time. This fires on every resize and sort,
            # so a busy moment is ordinary and the next one saves - a stack trace for it
            # is what teaches somebody to stop reading the log.
            logger.debug("console: the grid did not answer in time; layout for %s not "
                         "saved this time", where)
        except Exception:
            # A layout that fails to save is worth a log and nothing more - it must
            # never take down the grid the user is working in.
            logger.warning("console: could not save column state for %s", where, exc_info=True)

    for event in _SAVE_EVENTS:
        # A resize fires per pixel. nicegui's own throttle, so no timer outlives the
        # element; trailing_events keeps the final width.
        grid.on(event, save, args=[], throttle=0.6, trailing_events=True)
