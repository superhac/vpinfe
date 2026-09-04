"""VPinFE's palette, expressed as Quasar brand tokens rather than a stylesheet."""

from __future__ import annotations

from nicegui import ui

# Taken from managerui/static/manager.css, which is where the brand already lives: the
# dark set is :root, the light set is [data-theme="light"] with the neons darkened for
# contrast on white. Mapped onto Quasar's tokens so every component follows the palette
# and nothing needs styling by hand.
DARK: dict[str, str] = {
    "primary": "#b429f9",
    "secondary": "#00d9ff",
    "accent": "#ff0a78",
    "positive": "#00ff9f",
    # Darker than the accent it used to share. Quasar fills an error toast with this
    # and writes white on it: at #ff0a78 that measured 3.77:1, under the 4.5:1 that
    # 14px needs, on the surface that reports failure.
    "negative": "#e00068",
    "warning": "#ffd93d",
    "info": "#00d9ff",
    "dark": "#1a0f35",
    "dark_page": "#0a0518",
}

LIGHT: dict[str, str] = {
    "primary": "#8e24c7",
    "secondary": "#0099cc",
    "accent": "#d4006d",
    "positive": "#00a876",
    "negative": "#c7004f",
    "warning": "#d4a500",
    "info": "#0099cc",
}

LOGO = "/static/img/vpinfe-logo.png"

# The 2.x header treatment, from manager.css. A flat bar read as the same surface as the
# side rails, which is what made the whole shell look like one undifferentiated panel.
HEADER_GRADIENT = "linear-gradient(135deg, #b429f9 0%, #4a1e7c 50%, #0a0518 100%)"


# The 2.x visual treatment, from manager.css: a synthwave grid over the page, and the
# table's own row colors. AG Grid reads its palette from --ag-* custom properties, so
# the brand values are mapped onto those rather than restyling any of its parts.
# The design tokens. Everything below refers to these rather than to a hex or a pixel
# count, so a decision about the palette or the type scale is made once.
_TOKENS = """
:root {
  --ink: #eef9ff;        /* primary text            18.7:1 */
  --ink-2: #cbb8ea;      /* secondary text          11.1:1 */
  --ink-3: #9b8bbd;      /* help and hints           6.5:1 */
  --accent: #00d9ff;     /* interactive text        11.8:1 */
  --positive: #00ff9f;   /* present, installed, in use */
  /* Fills, borders and gradients only: magenta measures 4.4:1, under the 4.5:1 text
     needs. Text that must look interactive takes --accent. */
  --flair: #b429f9;
  --danger: #ff6b9d;     /* destructive, and absent in a way that costs you */
  /* Hover lifts the same hue. It used to move to orange, which was a transposition of
     the resting value rather than a decision. */
  --danger-hover: #ff8fb8;

  --surface-0: #0a0518;
  --surface-1: #150a2e;
  --surface-2: #1a0f35;
  --line: #2b1a4d;
  /* The visible edge, against --line's hairline: a menu, a dropped-file target and a
     panel header all need to be seen as an edge rather than felt as one. */
  --line-strong: #3d2461;
  --line-soft: #1f1338;
  /* Structure, not a hairline: the rule between stacked section bands has to be seen
     across a dark panel, and --line-soft sits close enough to the background that it
     read as nothing at all. */
  --line-band: rgba(203, 184, 234, 0.22);
  /* What a panel is, against the page under it. Named because two surfaces need to
     agree on it now that the workbench paints itself in parts. */
  --panel-ground: #150a2e;
  /* A row you are pointing at, and the place you are actually on. Two steps, because
     they are two states - and the second has to be the louder one. It was not: the
     nav's current entry sat below the hover it competes with. */
  --surface-hover: #2a1a4a;
  --surface-current: #332057;

  --fs-caption: 12px;
  --fs-body: 14px;
  --fs-title: 20px;
  /* A stat, not prose - the one place a number is the content. */
  --fs-display: 30px;

  /* 44px where a finger is in scope; the Console is desk-first, so this is the floor. */
  --target-min: 32px;
  /* An action that sits beside a value rather than owning its row - see
     `.console-action--inline`. Below the floor deliberately, and raised back to it where the
     pointer is a finger. */
  --target-inline: 22px;
  /* A field sits in the fact rhythm rather than standing above it. Raised on touch
     with the rest, below. */
  --field-h: 26px;

  /* One row of facts, sized as text. A row that *is* a field keeps the field's own
     height; since such a field is never a swapped-in box, nothing jumps. */
  /* The row, not the value: every kind of value - text, a chip, a field, a switch -
     centres in a box this tall, so the air around one does not depend on which kind it
     is. At 26 a text value sat 21px in 26 while a chip carried its own padding and read
     roomier, which is the mismatch a reader sees as inconsistent spacing. */
  --fact-row: 30px;

  /* How far a label column may grow before a long label wraps instead. One long label
     should cost its own row two lines, not push every control on the page away from the
     label naming it. The pane's labels sit under this and never wrap. */
  --label-max: 200px;
  /* The floor under a select, for the caret and the longest option name a set happens
     to hold. Text stretches because what you type has no length; a closed list of named
     things does not. */
  --select-min: 200px;

  /* What a draggable divider looks like, wherever one appears - a border color here
     reads as an edge rather than a handle. */
  /* The one warm color in this palette, and the reason both uses below read at a
     glance: nothing else here is warm. Named for what it is rather than for either
     use, so the second one did not have to invent a second amber.
     Measured against the surfaces it sits on: 11.1:1 and 5.9:1. */
  --warm: #ffc061;

  /* Who owns a media file. Amber is what makes "one table's own" legible in a map of
     twenty tiles; the folder-wide case is the norm and stays quiet. */
  --tier-table: var(--warm);
  --tier-quiet: var(--ink-3);
  --resize-line: rgba(255, 255, 255, 0.28);

  /* The gutter a panel keeps from whatever it sits against. One value, so the browse
     region and the work region do not each pick their own and land 4px apart. */
  --panel-gutter: 16px;

  /* Quiet, not invisible: a scrollbar says a region has more in it, so hiding one
     hides that there is more to see. */
  --scrollbar-size: 10px;
  --scrollbar-thumb: rgba(155, 139, 189, 0.32);
  --scrollbar-thumb-hover: rgba(155, 139, 189, 0.62);
}

/* Both engines: pseudo-elements for WebKit and Blink, properties for Firefox. */
* {
  scrollbar-width: thin;
  scrollbar-color: var(--scrollbar-thumb) transparent;
}
::-webkit-scrollbar {
  width: var(--scrollbar-size);
  height: var(--scrollbar-size);
}
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 999px;
  /* Inset, so the thumb floats in the gutter rather than filling it. */
  border: 2px solid transparent;
  background-clip: content-box;
}
::-webkit-scrollbar-thumb:hover { background: var(--scrollbar-thumb-hover);
                                  background-clip: content-box; }
::-webkit-scrollbar-corner { background: transparent; }
"""


_FLAIR = """
/* The base color goes on body alone. Painting it on .q-page-container too put an
   opaque element over body::before, which is where the grid lives - so the backdrop was
   still being drawn, just covered. */
body { background: var(--surface-0); }

/* nicegui gives .q-drawer__content 16px of padding and a 16px flex gap - the source of
   the workbench's 54px top gap, not anything the rows were doing. Scoped to the
   right drawer on purpose: the nav wants that breathing room, the workbench does not,
   because it has far more to fit. */
.console-workbench {
  /* Gap goes, top padding stays: the gap was the double-spacing, but the 16px top is
     what puts this header level with the nav's, which keeps it. */
  padding: 16px 0 0 !important;
  gap: 0 !important;
}
/* 18px is what centring a 20px icon in the 57px rail produces, so matching it here
   means the icon does not move horizontally when the workbench collapses. */
.console-workbench .console-panel-header { padding-right: 18px !important; }
.q-page-container, .q-page { background: transparent !important; }
.q-drawer { background: var(--panel-ground) !important; }

/* The rail is three bands and only the middle one scrolls. The drawer's own content is
   the flex column; left to itself it scrolls whole, which took the title and the
   version off the top and bottom as soon as the entries outgrew the height. */
.q-drawer--left .q-drawer__content {
  display: flex; flex-direction: column; overflow: hidden;
}
.q-drawer--left .console-nav-header,
.q-drawer--left .console-nav-body ~ * { flex: none; }
.console-nav-body {
  flex: 1 1 auto; min-height: 0; overflow-y: auto; overflow-x: hidden;
}
/* A rail entry is an anchor so the browser can offer it in a new tab, and an anchor
   arrives underlined and in the link color. It is a place in a list of places, and it
   is lit by `console-nav-active` when you are on it - a rule already answering "which one
   is this", which an underline under every one of them would not help with. */
a.console-nav-row, a.console-nav-row:hover, a.console-nav-row:visited {
  text-decoration: none;
  color: inherit;
}

body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image:
    linear-gradient(0deg, rgba(0, 217, 255, 0.2) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 217, 255, 0.2) 1px, transparent 1px);
  background-size: 40px 40px; opacity: 0.3;
}
.nicegui-aggrid, .ag-root-wrapper { position: relative; z-index: 1; }

.nicegui-aggrid {
  /* Depth comes from the tonal range, not from saturation: the page is nearly black,
     panels step up, the grid sits between them. The row alternation is deliberately
     narrow - var(--surface-2) against #251447 read as two different colors rather than as
     banding. */
  --ag-background-color: #140a2b;
  --ag-odd-row-background-color: #190e33;
  --ag-header-background-color: #0f0722;
  --ag-row-hover-color: var(--surface-hover);
  --ag-border-color: var(--line);
  --ag-header-foreground-color: var(--ink-2);
  /* The body reads at --ink-2, not --ink. A grid is most of the text on screen - 85% of
     it here - and the top of the ink scale applied to all of it is what made the Console
     relentless rather than crisp. The name column keeps --ink below, so the thing you
     scan for is still the brightest thing in the row. */
  --ag-foreground-color: var(--ink-2);
  --ag-font-size: var(--fs-body);

  /* Cyan carries selection and focus. Purple was doing every job at once, which is
     what made it read as flat - nothing stood out because everything was the accent. */
  /* Opaque, not a wash: a translucent selection composites over the two alternating
     bands differently, so a run of selected rows never reads as one block. */
  --ag-selected-row-background-color: #14314a;
  --ag-range-selection-border-color: var(--accent);
  --ag-input-focus-border-color: var(--accent);
  --ag-checkbox-checked-color: var(--accent);
}

/* The identifier a row is scanned by stays at the top of the ink scale; everything
   beside it supports it. Pinned left is where both grids put that column. */
.ag-pinned-left-cols-container .ag-cell { color: var(--ink); }
.ag-header { border-bottom: 1px solid rgba(0, 217, 255, 0.35) !important; }
/* Two states, one color: both answer "which one", and a second hue would read as a
   third meaning. Selected is a fill, focused is a band, and a row can be both.
   Set on the row, not --ag-selected-row-background-color, which AG Grid 34 ignores. */
.ag-row-selected,
.ag-row-selected.ag-row-odd {
  background-color: #14314a !important;
  box-shadow: inset 3px 0 0 var(--accent);
}

/* Focus follows the row, not the cell: nothing in a cell can be acted on. Drawn as
   top and bottom lines because a row is three elements - pinned left, center, pinned
   right - and three outlines would show their edges through the middle of it. */
/* Above the cells: a cell paints its own background over the row, so an inset shadow
   on the row is set, computed, and invisible. */
.ag-row.console-row-focus { position: absolute; }
.ag-row.console-row-focus::after {
  content: "";
  position: absolute; inset: 0;
  pointer-events: none;
  z-index: 2;
  box-shadow: inset 0 2px 0 var(--accent), inset 0 -2px 0 var(--accent);
}
/* Only the outer edges, or the verticals show where the fragments meet. The right one
   is off screen when the columns are wider than the window - the row does continue. */
.ag-pinned-left-cols-container .ag-row.console-row-focus::after {
  box-shadow: inset 0 2px 0 var(--accent), inset 0 -2px 0 var(--accent),
              inset 2px 0 0 var(--accent);
}
.ag-center-cols-container .ag-row.console-row-focus::after {
  box-shadow: inset 0 2px 0 var(--accent), inset 0 -2px 0 var(--accent),
              inset -2px 0 0 var(--accent);
}
/* If a column is ever pinned right, that fragment owns the right edge instead. */
.ag-pinned-right-cols-container .ag-row.console-row-focus::after {
  box-shadow: inset 0 2px 0 var(--accent), inset 0 -2px 0 var(--accent),
              inset -2px 0 0 var(--accent);
}
/* The cell's own ring goes with it, or the row carries two. */
.ag-cell-focus, .ag-cell-focus:focus, .ag-cell.ag-cell-focus {
  border-color: transparent !important;
  outline: none !important;
}

/* The 2.x aesthetic proper: content sits in rounded, bordered panels that glow rather
   than on a bare page, the grid header carries the brand gradient, and cyan does the
   labelling. Values are manager.css's own - --line, --shadow, --header-gradient. */
/* Menus in the app's own idiom, and tight: Quasar's default item is 48px tall with
   16px gutters, which reads as a system menu dropped into the page. */
.q-menu {
  background: var(--surface-2) !important;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(180, 41, 249, 0.2);
  min-width: 168px;
}
.q-menu .q-item {
  min-height: 30px;
  padding: 4px 12px;
  font-size: var(--fs-body);
  color: var(--ink-2);
}
.q-menu .q-item:hover { background: var(--surface-hover); }
.q-menu .q-separator { background: var(--line-strong); margin: 2px 0; }
/* A picker over the whole library. Unconstrained, its menu is as wide as the longest
   title in it - which in a library with one 130-character name is the whole window -
   and it resizes and repositions itself as typing filters the list. Bounded here, so
   it opens the same size every time and stays under the field it belongs to. */
.console-picker-popup {
  max-height: 44vh;
  /* A width, not a max-width. The menu is portalled to <body>, so a percentage is a
     percentage of the window - and left to size itself it takes the longest title in
     the library, which is how a 130-character name made it 1375px wide. Fixed, it
     opens the same size every time; the names that do not fit ellipse. */
  width: 340px;
  max-width: 90vw;
}
/* A collection's icon, and the drop target that replaces it. Small: it identifies the
   collection in a wheel, it is not the content of this panel. */
.console-collection-icon {
  width: 64px; height: 64px;
  object-fit: contain;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-ground);
}
.console-upload .q-uploader { background: none; border: 1px dashed var(--line-strong); }

/* The rule, said in words above the controls that set it. Roomier than help text
   because it is the sentence somebody reads to check the rule says what they meant. */
.console-rule-sentence {
  color: var(--ink-2);
  font-size: var(--fs-body);
  max-width: none;
}

/* Why a row is in the collection. Quiet where the answer is ordinary, amber where it
   is something to go and fix - the same reading the rest of the app gives the colour. */
.console-member-chip {
  font-size: var(--fs-caption);
  letter-spacing: 0.04em;
  padding: 1px 7px;
  border-radius: 999px;
  white-space: nowrap;
  flex: none;
}
/* The ordinary state, dimmed so a scan passes over it, and the one that wants
   attention. Both are always present - what varies between rows is data, and reading it
   from the absence of a mark cannot be told from a row that has no table at all. */
.console-chip-quiet { color: var(--ink-3); border: 1px solid #241640; }
.console-chip-warn { color: var(--tier-table); border: 1px solid rgba(255, 192, 97, 0.45); }

/* The collection's icon in a media slot's art region. Contained, so a wide banner and a
   square logo both sit in the same box. */
.console-slot-image { max-width: 100%; max-height: 100%; object-fit: contain; }

/* A collection's picture in the list. Small and contained: it identifies a row, it is
   not the row. */
.console-collection-cell {
  height: 30px; max-width: 44px;
  object-fit: contain;
  display: block;
  margin: 3px auto;
}

/* Dynamic or Manual, the one control that converts between them. */
.console-kind-toggle { flex: none; }

/* The grip on an arrangeable row. `grab` rather than `move`, because the row is being
   picked up rather than pushed around, and `touch-action: none` or the browser scrolls
   the panel instead of letting the pointer handler have the drag. */
.console-drag-handle {
  cursor: grab;
  touch-action: none;
  font-size: 18px;
  color: var(--ink-3);
  flex: none;
}
.console-drag-handle:hover { color: var(--accent); }
/* Lifted, not swapped: the row leaves the flow and follows the pointer while the rest
   of the list holds still. Swapping moved the rows you were aiming at, so the target
   changed as you approached it. */
.console-member-row.console-dragging {
  position: fixed;
  z-index: 8000;
  background: var(--surface-hover);
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.55);
  cursor: grabbing;
  pointer-events: none;
}
/* Where it would land. A band rather than an empty gap: the gap alone reads as the
   list having lost a row. */
.console-drop-slot {
  border-radius: 6px;
  border: 1px dashed var(--accent);
  background: rgba(0, 217, 255, 0.06);
}
/* The keyboard's equivalent of being lifted. */
.console-member-row.console-grabbed {
  background: var(--surface-hover);
  outline: 1px solid var(--accent);
  border-radius: 6px;
}
.console-drag-handle:focus-visible {
  outline: 2px solid var(--accent);
  border-radius: 4px;
}

/* --- one member of a collection ------------------------------------------------ */

/* Two lines that are one answer: the game, and which of its tables this collection
   holds. Tight leading and a step down in size and weight are what make the second
   read as belonging to the first rather than as the next row. */
/* A *member* is a row in a list belonging to the selected subject - a collection's
   games, a game's tables. The word is collections' and the classes are shared on
   purpose: the two lists are the same shape and one treatment is the point. */
.console-member-row {
  padding: 5px 10px;
  border-radius: 6px;
  line-height: 1.25;
}
/* The row the panel beside this is about. Weight, not colour: accent is the chosen one
   and the default mark already spends it on this list, so a second accent here would
   have two meanings in one row. */
.console-member-name--here { color: var(--ink); font-weight: 600; }
.console-member-name { font-size: var(--fs-body); color: var(--ink-2); }
.console-member-table {
  font-size: var(--fs-caption);
  color: var(--ink-3);
  line-height: 1.2;
  /* Not `.console-help`, whose 62ch cap and looser leading are for prose. This is a
     label under another label. */
  padding-left: 1px;
}

/* Which of the two this table is, said beside the table it qualifies rather than in the
   chip slot at the row's edge - that slot is for what has happened to the row. Dimmer
   than the identity it follows, so a scan reads the names and not the qualifier. */
.console-member-qualifier {
  font-size: var(--fs-caption);
  color: var(--ink-3);
  opacity: 0.72;
  white-space: nowrap;
  flex: none;
}

/* The one row that is not what the list said it was. Read against the summary line
   above, which is the legend - a glyph without one is a puzzle, and with one it is the
   quietest mark available. Sized to the caption text it sits beside. */
/* Leading, so every row's mark sits at the same x and the column can be scanned
   without reading a word of it. A trailing mark lands after variable-length text and
   is at a different place on every row, which is why it read as litter. */
/* One diameter for every state: the circle is drawn here rather than borrowed from the
   font, where ● and ◐ are different sizes and no font-size makes them agree. Colour
   comes from `currentColor`, so a mark follows whatever text it sits beside. */
.console-mark {
  /* `inline-block` so it also works in a grid cell, which is not a flex row. */
  display: inline-block;
  vertical-align: middle;
  flex: none;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 1.5px solid currentColor;
  box-sizing: border-box;
}
/* Named for the *shape*, not for what it means. Two vocabularies use these - which
   table an entry points at, and where a media file resolved from - and section 13 is
   explicit that they share the shapes and not the nouns. A modifier called `--fixed`
   would have carried one vocabulary's meaning into the other's screens. */
.console-mark--full { background: currentColor; }
/* The base circle, named so a caller can say which end of the ramp it means rather
   than passing an empty string and hoping. */
.console-mark--outline { background: transparent; }
/* Half filled, and the fill runs to the circle's own centre rather than to the edge of
   its outline. */
.console-mark--half {
  background: linear-gradient(to right, currentColor 50%, transparent 50%);
}
/* Drawn rather than bordered. `border-style: dashed` picks its own dash length from the
   border width, which on a 34px circumference put three chunky dashes on the circle -
   the same declaration that reads as a proper dashed edge on a tile, because a tile has
   the perimeter for it. The gradient is an exact eight, at any size. */
.console-mark--dashed {
  border-color: transparent;
  background: repeating-conic-gradient(currentColor 0 22.5deg,
                                       transparent 22.5deg 45deg);
  -webkit-mask: radial-gradient(circle at center, transparent 0 4px, #000 4px);
  mask: radial-gradient(circle at center, transparent 0 4px, #000 4px);
  opacity: 0.7;
}
/* A square on its corner: the odd one out on purpose, because the state it marks is
   the one that is not a degree of the others. */
/* The legend for those marks, sitting on the toolbar beside the count. */
.console-tier-key .console-mark { margin-right: 3px; }
/* A state drawn as nothing still needs its place in the legend, or the reader is left
   matching three words against two marks. It holds a mark's width and stays empty. */
.console-mark-none { display: inline-block; width: 11px; margin-right: 3px; }

/* Five stars that are also the control. Sized to the row rather than to a dialog: this
   is the compact form of the same five, and a star big enough to admire is a column
   wide enough to hurt. */
.console-stars-cell { padding-left: 10px !important; }
.console-stars { display: inline-flex; gap: 2px; line-height: 0; }
.console-star {
  width: 13px;
  height: 13px;
  cursor: pointer;
  background: var(--ink-3);
  /* One shape, filled or not, so the two states cannot differ in size the way ★ and ☆
     do in a font - the same trap the media marks were drawn to avoid. */
  clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%,
                     50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%);
  opacity: 0.35;
  transition: opacity 90ms ease-out, background 90ms ease-out;
}
.console-star--on { background: var(--accent); opacity: 1; }
.ag-row:hover .console-star { opacity: 0.6; }
.ag-row:hover .console-star--on { opacity: 1; }
.console-star:hover { opacity: 1; background: var(--accent); }
/* The way back to unrated. Beside the stars rather than in them, because it is not a
   sixth degree of the same scale - and only on a row the pointer is over, so a rated
   library does not read as a column of dismissals. */
.console-star-clear {
  margin-left: 5px;
  font-size: 13px;
  line-height: 13px;
  color: var(--ink-3);
  cursor: pointer;
  opacity: 0.75;
  transition: opacity 90ms ease-out, color 90ms ease-out;
}
/* On the stars, in both places: the pointer is already there when somebody means to
   change a rating, and a row-wide reveal put it on screen for anyone crossing the grid.
   It is only rendered where there is a rating, so this hides nothing a reader needs.
   Gated on the input, never on the surface (`docs/conventions.md`) - a touch device
   cannot hover, so there it is simply there, and a keyboard reaches it by focus. */
@media (hover: hover) and (pointer: fine) {
  .console-star-clear { opacity: 0; }
  .console-stars:hover .console-star-clear { opacity: 0.75; }
}
.console-stars:focus-within .console-star-clear { opacity: 1; }
.console-star-clear:hover { opacity: 1; color: var(--ink); }
/* In the filter, the stars are a picture of a value and not a control. */
.console-filter-row .console-star { cursor: pointer; margin-right: -1px; }

/* One confirmation, wherever something cannot be undone. Narrow enough to read in one
   line of sight, and the named files are quiet and breakable - a path is looked at, not
   read. */
.console-confirm { min-width: 320px; max-width: 460px; }
/* A picker is a list to read down, not a question to answer, so it takes the room a
   list needs and caps its height rather than growing past the window. */
.console-picker-dialog { min-width: 520px; max-width: 640px; }
.console-picker-dialog .console-source-list { max-height: 42vh; overflow-y: auto; }
/* The question is a sentence and takes sentence case. It used to wear `.console-card-title`,
   which is the section-heading treatment - uppercase, tracked, accent - so every dialog
   opened by shouting its question. Weight and size carry it instead. */
.console-confirm-title {
  font-size: var(--fs-body);
  font-weight: 600;
  color: var(--ink);
  line-height: 1.35;
}
.console-confirm-line {
  font-size: var(--fs-caption);
  color: var(--ink-3);
  word-break: break-all;
}

/* The state picker inside a column's filter. The same words and marks as the legend,
   because a filter that named the states differently would be a third vocabulary. */
.console-filter { padding: 6px 4px; min-width: 148px; }
.console-filter-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 8px;
  border-radius: 4px;
  cursor: pointer;
  color: var(--ink);
  font-size: 13px;
  white-space: nowrap;
}
.console-filter-row:hover { background: rgba(255, 255, 255, 0.06); }
/* The leading slot, wide enough for a mark and present whether or not there is one -
   a choice that draws nothing in the grid indents to here rather than shifting its
   label left of every other. A rating draws five, so it grows rather than clipping. */
.console-filter-mark {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-width: 11px;
  flex: none;
}
.console-filter-row input { accent-color: var(--accent); cursor: pointer; margin: 0; }

/* A media cell holds one thing - a mark or a picture - so it centres that thing rather
   than leaving it on the text baseline. A picture on the baseline sat 1px below the top
   of a 60px row and 7px above the bottom. */
.ag-cell.console-media-cell {
  display: flex;
  align-items: center;
  justify-content: center;
}
/* AG Grid wraps a renderer's HTML in a bare <span> of its own, and that span - not the
   art - is what the cell centres. On a line box sized for the row it stood 76px tall in
   a 59px cell, so centring hung the picture 8px above the cell and the clip took the top
   off the enlarge. Zero line height makes it the height of what it holds. */
.console-media-cell > * {
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
}
/* The art and the control that enlarges it. Relative on the art rather than the cell,
   so the button sits on the picture's own corner - on the cell's it floats out over
   the whitespace beside a narrow one. */
.console-cell-art { position: relative; display: inline-flex; line-height: 0; }
.console-cell-zoom {
  position: absolute;
  top: 2px;
  right: 2px;
  font-size: 14px;
  padding: 2px;
  border-radius: 4px;
  color: var(--ink);
  background: rgba(10, 5, 24, 0.72);
  cursor: pointer;
  /* Hidden until the row is under the cursor: twenty of these showing at once is a
     column of buttons, and the pictures are what the row is for. */
  opacity: 0;
  transition: opacity 90ms ease-out;
}
.ag-row:hover .console-cell-zoom { opacity: 0.75; }
.console-cell-zoom:hover { opacity: 1; background: rgba(10, 5, 24, 0.9); }

.console-mark--set {
  border-radius: 0;
  background: currentColor;
  transform: rotate(45deg) scale(0.82);
}

.console-member-mark {
  /* Big enough that ● and ◐ are told apart. They differ by half a fill, which at 11px
     is two or three pixels - measured on screen, both read as the same dot. */
  font-size: 15px;
  line-height: 1;
  color: var(--ink-2);
  flex: none;
  width: 16px;
  text-align: center;
}
.console-member-row:hover .console-member-mark { color: var(--accent); }

/* The table line doubles as the control that changes which table this member names.
   The caret is the only added ink and it waits for a hover, so a list of forty rows
   reads as text; on touch, where there is no hover, it is simply always there. */
/* The second half of the pair, and it takes the pair's quieter colour: the mark draws
   itself in `currentColor`, so without this it inherited white from the row and came
   out brighter than the name above it.

   Not pulled up at all. The -4px this carried was tuned when the line held nothing but
   text; it now carries an 11px mark that makes the line taller, so any pull at all put
   the line over the name. A hairline of daylight is what makes the two read as a pair
   rather than as one crowded block. */
.console-member-table-line {
  border-radius: 4px;
  padding-right: 2px;
  margin-top: 1px;
  color: var(--ink-3);
}
.console-member-row:hover .console-member-table-line .console-mark { color: var(--accent); }
.console-member-table-line:hover { background: rgba(255, 255, 255, 0.06); }
.console-member-table-caret {
  font-size: 15px;
  color: var(--ink-3);
  flex: none;
}
/* Where the pointer is a finger, the one control that sits below the target floor takes
   it back. `pointer` is the primary device, not the presence of a touchscreen: a laptop
   with both reports `fine` and is still being driven with a trackpad. */
@media (pointer: coarse) {
  :root { --target-inline: var(--target-min); --field-h: var(--target-min); }
}
@media (hover: hover) and (pointer: fine) {
  .console-member-table-caret { opacity: 0; transition: opacity 120ms ease; }
  .console-member-row:hover .console-member-table-caret,
  .console-member-table-line:focus-within .console-member-table-caret { opacity: 1; }
}
/* Wraps rather than truncates: in the menu the whole point is telling two builds of
   one game apart, and that is exactly what a cut-off tail hides. */
/* Wraps rather than truncates: in this menu the whole point is telling two builds of
   one game apart, and that is exactly what a cut-off tail hides. The uppercase opt-out
   this used to carry is gone - no menu item is uppercase now. */
.q-menu .console-menu-item .console-menu-table-name {
  max-width: 30ch;
  white-space: normal;
}
.console-menu-check { font-size: 16px; color: var(--accent); }
/* What Game Default resolves to today, under the words that name it. A step down in
   size and colour, the same way a member row's table line sits under its game. */
.q-menu .console-menu-item .console-menu-sub {
  font-size: var(--fs-caption);
  /* A step below `--ink-3`, where the ramp stops: this is the only text on the menu
     nobody has to read - the label above carries the choice, and this answers "which
     one is that today". Opacity rather than a new ink, so it stays a step below
     whatever colour the row wears, chosen or not.
     0.85 and no further: measured over the menu's ground that is 4.58:1, and 0.72 -
     which looked right - came out at 3.64 and under AA for normal text. The palette
     states its ratios on purpose; dimming is not a licence to leave the ramp. */
  color: var(--ink-3);
  opacity: 0.85;
  line-height: 1.2;
  max-width: 30ch;
  white-space: normal;
}
/* Offered, and refused. Dimmed rather than removed: an entry that is simply absent is
   the same puzzle as a row that vanishes, which is what this state exists to avoid. */
.q-menu .console-menu-item.console-menu-blocked,
.q-menu .console-menu-item.console-menu-blocked .q-item__label,
.q-menu .console-menu-item.console-menu-blocked:hover,
.q-menu .console-menu-item.console-menu-blocked:hover .q-item__label {
  color: var(--ink-3);
  opacity: 0.55;
  cursor: default;
  background: transparent;
}
.console-menu-blocked-mark { color: var(--ink-3) !important; font-size: 15px; }
/* Which of a game's tables it offers. A radio rather than a glyph: a game has exactly
   one default, that is what a radio means, and it reads as a control - which this one
   is. Kept clear of the text glyphs in `game_tables.py`, whose question is a different
   one, by being an icon and by living on a surface those never appear on. */
.console-default-mark {
  font-size: 18px;
  color: var(--ink-3);
  flex: none;
  transition: color 120ms ease;
}
.console-default-mark--on { color: var(--accent); }
.console-default-mark.cursor-pointer:hover { color: var(--ink); }

/* Something to go and do, in the colour this theme keeps for exactly that. The rail is
   already a lit surface, so the accent would make this one more glowing thing in it
   rather than the one worth acting on. */
.console-update {
  color: var(--warm);
  font-weight: 600;
}
.console-update:hover { text-decoration: underline; }

/* The icon of a rail entry, as a box a badge can be hung on. The badge belongs to the
   icon rather than the row because the icon is in both states and the label is not. */
.console-nav-mark {
  position: relative;
  display: flex;
  align-items: center;
  flex: none;
}

/* How many of something are waiting behind a rail entry, on the icon's upper right in
   both states. Same warm as .console-update and for the same reason: it is the one thing in
   a lit rail worth acting on. A count only - what it is about is on the page it leads
   to. */
.console-nav-badge {
  background: var(--warm);
  /* The darkest surface rather than the ink: on a filled warm chip the text has to
     read against the fill, and --ink is chosen to read against a dark ground. */
  color: var(--surface-0);
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  padding: 2px 4px;
  min-width: 15px;
  text-align: center;
  /* On the icon's upper right, and it may not overhang far: the rail's body scrolls, so
     anything past the row's box is clipped once the rail is collapsed - which is exactly
     where the badge is the only thing left saying the entry wants attention. */
  position: absolute;
  top: -4px;
  right: -4px;
}

/* A log, read the way `tail` shows one: newest last, monospaced so timestamps and levels
   line up down the column, and the message under its own header line rather than beside
   it - a traceback is the case that matters and it has nowhere to go on one line. */
.console-log {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.5;
}
.console-log-row { padding-top: 6px; }
.console-log-when { color: var(--ink-3); flex: none; }
/* Fixed width, so the source names beside them start at one place down the column. */
.console-log-level { flex: none; width: 62px; font-weight: 700; }
.console-log-plain { color: var(--ink-3); }
.console-log-warn { color: var(--warm); }
.console-log-bad { color: var(--danger); }
.console-log-source { color: var(--ink-3); min-width: 0; overflow: hidden;
                      text-overflow: ellipsis; white-space: nowrap; }
/* Wrapped and indented under its header. `pre-wrap` because a traceback's own leading
   spaces are what make it readable, and collapsing them turns it into a paragraph. */
.console-log-message {
  color: var(--ink-2);
  white-space: pre-wrap;
  word-break: break-word;
  padding-left: 4px;
}
/* Where the rest of it is. Quiet - it is a fact about the page rather than a record. */
.console-log-path {
  color: var(--ink-3);
  font-size: var(--fs-caption);
  padding-top: 10px;
}

/* The dot that says a device answered, before its name in the devices rail. Its own
   class rather than a mark: the mark vocabulary is about a library's coverage, and this
   is about whether a machine is switched on. */
.console-reach-dot { margin-right: 8px; }

/* A feature is switched on and something it needs is not there. Danger rather than the
   warm above: an update waiting is worth doing when you get to it, and this is already
   broken, so the two must not read as the same kind of news. */
.console-nav-badge--error { background: var(--danger); }
/* The same finding where a count would say nothing - a settings group and the page under
   it are signposts, and what is wrong is on the page they lead to. In the corner over
   the name rather than beside it, so a row reads the same whether it carries one or
   not. */
.console-trouble-mark {
  color: var(--danger);
  position: absolute;
  /* On the label's own line. Raised into the corner it read as belonging to nothing -
     the eye joins a mark to text it is level with. Centred rather than stretched: the
     glyph carries its own height, so top and bottom together would not have moved it. */
  top: 50%;
  transform: translateY(-50%);
  right: 6px;
}

/* The sort control above the devices rail. Aligned to the rail rather than the page, so
   it reads as belonging to the list it orders. */
.console-devices-bar { padding: 8px 12px 0 12px; }
.console-devices-sort { min-width: 120px; }

/* A tooltip belonging to the control that opened a menu would sit on top of it. */
body.console-menu-open .q-tooltip { display: none !important; }

/* The grid's own tooltip, which is where a column explains itself. AG Grid renders the
   text verbatim, so `pre-line` is what makes a newline in the help a line on screen -
   an explanation that names three states runs three lines or it runs together.
   Widened past the default, which wraps a sentence into a column two words across. */
.ag-tooltip {
  white-space: pre-line;
  max-width: 340px;
  background: var(--surface-2);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: var(--fs-caption);
  line-height: 1.45;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
}

/* The key for those marks, in the header that does not scroll. */
.console-member-key {
  font-size: var(--fs-caption);
  color: var(--ink-2);
  white-space: nowrap;
  flex: none;
}

/* Alternating ground. Rows are two lines tall here, so where one ends is not obvious
   from spacing alone - which is exactly when striping earns its keep. Kept very low
   contrast: it separates, it does not decorate. */
.console-member-row:nth-child(even) { background: rgba(255, 255, 255, 0.055); }
.console-member-row:hover { background: var(--surface-hover); }

/* The row's action appears under the cursor. A column of identical glyphs down a long
   list is noise competing with the content, and the action is the same on every row.
   `opacity`, never `display`: the space stays reserved, so nothing shifts under the
   pointer as it arrives. `focus-within` so a keyboard reaches what a mouse does.
   Except where the row is already flagged - those are few by definition and are the
   ones somebody opened this panel to deal with, so their one action stays put.

   Gated on the *input*, not on the width. Hiding an action behind hover on a device
   that cannot hover makes it unreachable, and a touchscreen laptop is as wide as a
   desk one - so the question is what the pointer can do, never how big the screen is.
   Visible is the default; hover-to-reveal is the enhancement. */
/* A row of verbs, not a column: with one button the default flow was enough, and the
   second one wrapped under the first at panel width. */
.console-row-action {
  transition: opacity 120ms ease;
  display: flex; align-items: center; flex: 0 0 auto;
}
@media (hover: hover) and (pointer: fine) {
  .console-row-action { opacity: 0; }
  .console-member-row:hover .console-row-action,
  .console-member-row:focus-within .console-row-action { opacity: 1; }
  .console-member-row[data-origin="missing"] .console-row-action,
  .console-member-row[data-origin="excluded"] .console-row-action { opacity: 1; }
}

.console-picker-popup .q-item__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* --- menus ---------------------------------------------------------------------

   One language for every menu: the table-choice dropdown, the grid's header and cell
   menus, the bulk actions, the View menu and the pickers. The rules had it backwards -
   the group label was 16px and glowing while the thing you click was 11px uppercase
   cyan, so the signpost shouted louder than the destination and every entry read as a
   banner. Table names had to opt out of the uppercase to stay legible, which was the
   symptom rather than the fix.

   **The group label is chrome; the item is content.** */

/* The same treatment as `.console-group`, which is what the rest of the app uses to name a
   group. Quiet, small, tracked - a signpost recedes. */
.console-menu-header {
  color: var(--ink-3) !important;
  font-size: var(--fs-caption);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  min-height: 24px !important;
  padding: 8px 12px 2px !important;
}
/* Body voice. You read an item and click it; sentence case is how a name stays a name,
   which is what a menu over a library is full of. */
.q-menu .console-menu-item,
.q-menu .console-menu-item .q-item__label {
  color: var(--ink-2);
  font-size: var(--fs-caption);
  text-transform: none;
  letter-spacing: normal;
}
/* Every item spans the menu. NiceGUI's column carries `items-start`, so an item in one
   sized to its own text and the hover band stopped where the words did - measured at
   121px inside a 247px menu. The band *is* the affordance; a colour change alone is
   too weak to say "this row is the target". */
.q-menu .console-menu-item {
  width: 100%;
  min-height: 30px;
  border-radius: 0;
}
.q-menu .console-menu-item:hover,
.q-menu .console-menu-item:focus-visible {
  background: var(--surface-hover);
}
.q-menu .console-menu-item:hover,
.q-menu .console-menu-item:hover .q-item__label,
.q-menu .console-menu-item:focus-visible,
.q-menu .console-menu-item:focus-visible .q-item__label { color: var(--ink); }

/* Cyan is the current value and nothing else. Everything being accent-coloured is what
   left it meaning nothing. */
.q-menu .console-menu-item.console-menu-on,
.q-menu .console-menu-item.console-menu-on .q-item__label { color: var(--accent); }

/* One leading column, 16px, whatever fills it - mark, icon or nothing. Items with no
   mark still indent to it, so the labels line up down the menu. */
.console-menu-mark, .console-menu-add {
  flex: none;
  width: 16px;
  font-size: 16px;
  line-height: 1;
  text-align: center;
  color: var(--ink-3);
}
/* A drawn mark keeps its own diameter and is centred in that column rather than
   stretched across it - the column's 16px made an 11px circle into an oval. */
.q-menu .console-menu-mark.console-mark { width: 11px; margin: 0 2.5px; }
.q-menu .console-menu-item:hover .console-menu-mark,
.q-menu .console-menu-item:hover .console-menu-add { color: var(--ink); }
.q-menu .console-menu-item.console-menu-on .console-menu-mark { color: var(--accent); }

/* The act, not the row, is what is destructive: the text carries it and the hover band
   stays the ordinary one. A red row reads as an error that has already happened. */
.q-menu .console-menu-item.console-menu-danger,
.q-menu .console-menu-item.console-menu-danger .q-item__label { color: var(--danger); }
.q-menu .console-menu-item.console-menu-danger:hover,
.q-menu .console-menu-item.console-menu-danger:hover .q-item__label { color: var(--danger-hover); }

/* A checkbox item is an item: same band, same height, same leading column - the box
   is what fills the mark slot. */
.q-menu .q-checkbox.console-menu-item {
  display: flex;
  padding: 2px 12px;
  min-height: 30px;
}

/* Between groups, never as decoration. */
.q-menu .q-separator { margin: 4px 0; opacity: 0.5; }

/* Tiles are deliberately plain: the art is the content, so the chrome around it stays
   quiet enough that an outlier stands out rather than the frame. */
.console-tile { cursor: pointer; padding: 4px; border-radius: 8px; }
.console-tile:hover { background: var(--surface-hover); }
.console-tile-art {
  width: 100%;
  object-fit: contain;
  border-radius: 6px;
  background: #140a2b;
  border: 1px solid var(--line);
}
.console-tile-missing { border-style: dashed; }
.console-tile-label {
  font-size: var(--fs-caption);
  color: var(--accent);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-top: 2px;
}

.console-panel {
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(180, 41, 249, 0.2);
}
.console-label { color: var(--accent); letter-spacing: 0.04em; }

/* Nav in the 2.x idiom: a vertical gradient off the brand purple into the page black,
   caps with tracking, and cyan for the title. The gradient runs dark enough by the foot
   that the version row still reads. */
.q-drawer--left {
  /* 2.x's --header-gradient stops, but the bright band is compressed into the header
     row rather than spread down the rail. The title is near-white with a glow and
     carries purple fine; the items are #5898d4 and do not, so the ground under them
     has to be dark. 90px is just past the 59px header. */
  background: linear-gradient(180deg, var(--flair) 0px, #4a1e7c 60px, var(--surface-2) 90px,
                              #0f0722 100%) !important;
}
.console-nav-item {
  /* Sampled from 2.x: 14px at weight 500 with normal tracking. Mine were 12px with
     0.06em, which read noticeably smaller and tighter than the nav beside it. */
  text-transform: uppercase;
  font-family: sans-serif;
  font-size: var(--fs-body);
  font-weight: 500;
  line-height: 24px;
  /* Sampled off the running 2.x nav, not read from manager.css: .nav-btn declares
     --ink-muted but never wins, and the items render at nicegui's default primary. The
     label above them is the only cyan in the panel. */
  color: var(--ink-2);
}
.q-drawer--left .cursor-pointer:hover .console-nav-item { color: var(--ink); }
.q-drawer--left .cursor-pointer:hover .q-icon { color: var(--ink); opacity: 1; }
.q-drawer--left .q-icon { color: var(--ink-2); }

/* The row itself, also sampled: 48px tall on a 12px/16px pad with a 12px radius, so a
   highlighted row reads as a rounded block inset from the panel edge. */
/* Geometry only. The surface and border here came from matching the "Navigation"
   label's row, which was the wrong element - the title it now matches sits in 2.x's
   header bar with nothing drawn behind it. */
.console-nav-header {
  min-height: 59px;
  padding: 12px !important;
  /* Quasar's .row wraps, and the title's width is whatever `sans-serif` resolves to on
     the machine. Where that lands on a wider face the label dropped under the icon and
     took the header to 90px. Nothing in here may shrink below its own width either, or
     the brand ellipses instead. */
  flex-wrap: nowrap;
}

/* At the rail the row is the icon's whole world, so the wide state's side padding
   pushes it off center. Set here because that padding is !important and a utility
   class cannot outrank it. */
.q-drawer--mini .console-nav-row,
.q-drawer--mini .console-nav-header {
  padding-left: 0 !important;
  padding-right: 0 !important;
  margin-left: 0;
  margin-right: 0;
  max-width: 100%;
  justify-content: center;
}

.console-nav-row {
  min-height: 48px;
  padding: 12px 16px !important;
  border-radius: 12px;
  margin: 2px 8px;
  /* w-full plus a horizontal margin overhangs on the right, which put the highlight
     off-center. 2.x's .nav-btn solves it the same way. */
  max-width: calc(100% - 16px);
}
/* Nested under a parent entry, indented by the icon column so the children line up
   under the parent's label rather than under its icon. Collapsed to the mini rail the
   indent goes with the labels - there is nothing left to line up with. */
.console-nav-row--nested {
  padding-left: 32px !important;
  /* Subordinate, not just shifted: a child that matches its parent in height, icon and
     type is a sibling wearing an indent. 38px against 48, 19px against 24, caption
     against body - each one step down, none of them a different treatment. */
  min-height: 38px;
  padding-top: 6px !important;
  padding-bottom: 6px !important;
  margin-top: 0;
  margin-bottom: 0;
}
.console-nav-row--nested .q-icon { font-size: 19px !important; }
.console-nav-row--nested .console-nav-item {
  font-size: var(--fs-caption);
  line-height: 20px;
}
/* Collapsed to icons there is no parent to line up under, so the indent goes - but the
   step down stays. A child keeps its smaller icon in the rail, which is the only thing
   left that can say it is one. Row height does not follow it: the rail's rhythm is one
   height, and the icons centre in it either way. */
.q-drawer--mini .console-nav-row--nested {
  padding-left: 0 !important;
  min-height: 48px;
}

/* The parent row holds a spacer to push its caret right. Collapsed, the label and the
   caret are hidden but the spacer is not - and a zero-width flex item still earns the
   row's gap, so the icon sat 6px left of every other one in the rail. */
.q-drawer--mini .console-nav-row .q-space { display: none; }

/* The page you are on stays lit while you are on it - --surface-2 behind it and
   --glow-purple around it, which is what 2.x does. */
.console-nav-active {
  background: var(--surface-current);
  box-shadow: 0 0 4px rgba(180, 41, 249, 0.5), 0 0 8px rgba(180, 41, 249, 0.3);
}

/* One accent, not three. Purple is surface - gradients, borders, the grid header - and
   cyan is the only thing that accents. Pink was a third hue close enough to the header
   magenta to muddle rather than contrast; the panels are told apart by tone instead,
   the nav title at full neon and this one near-white with a softer halo. */
.console-workbench {
  /* The nav's treatment, one step down in intensity: a band compressed into the header
     row so the subject sits on its own ground rather than on the same flat field as the
     list of what you can ask about it. It starts at the nav's *second* stop rather than
     its neon, because the magenta is what marks the product and there is only one.
     This panel had nothing to carry when the band was withheld from it; it carries the
     selected game now, which is what changed.

     And then it stops dead. Past the rows' top edge this paints nothing, so browse and
     edit are open to the page - which is the depth model the grid already states: the
     page is nearly black, panels step up. A panel-wide gradient made the whole surface
     a lit thing; as a frame with windows cut in it, only the parts that are the panel
     are lit.

     Resolved to the panel's own ground by 72px and held flat to 80px, then cut. Fading
     to transparent instead put the page - grid and all - behind the bottom of the band
     and behind the rail beside it, which is not a window, and the edge where that met
     the solid rail read as a mistake. The panel is opaque everywhere it is the panel.
     80px is where the rows start; 16px of the workbench's own top padding sits above
     the header, so this starts at 0 or the band would not reach the panel's edge. */
  background: linear-gradient(180deg, #4a1e7c 0px, #2a1a52 44px,
                              var(--panel-ground) 72px, var(--panel-ground) 80px,
                              rgba(0, 0, 0, 0) 80px) !important;
}
/* Collapsed to the rail there is no window at all - the whole strip is panel, so it is
   opaque like every other part that is. The band above is untouched; only the cut to
   transparent goes, which is what let the page grid through a 57px strip. */
.console-rail .console-workbench {
  background: linear-gradient(180deg, #4a1e7c 0px, #2a1a52 44px,
                              var(--panel-ground) 72px) !important;
}
/* truncate only ellipsizes against a definite width. The column may shrink under
   min-w-0, but its labels have to be told to take that width or they overflow and get
   cropped by the parent instead of ellipsized. */
.console-panel-header .console-workbench-title,
.console-panel-header .console-workbench-label { max-width: 100%; }

.console-workbench-title {
  color: var(--ink);
  text-shadow: 0 0 6px rgba(0, 217, 255, 0.45);
}
.console-workbench-label {
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: var(--fs-caption);
}
/* The same name, drawn above the content instead of in a header beside it. The rule is
   what makes it read as a heading rather than as the first line of the page; the gutter
   matches .console-facts so the name sits on the labels' left edge. */
.console-panel-heading {
  display: block;
  /* Or the rule is the width of the word and reads as an underline on it. */
  width: 100%;
  padding: 0 12px 10px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--line-soft);
}
/* Tight: this panel carries a lot and the default expansion chrome is mostly air. */
.console-workbench .q-expansion-item {
  border: 1px solid var(--line);
  border-radius: 8px;
  /* Vertical margin only. A horizontal margin on a w-full child overhangs by exactly
     its own width, which is where the workbench's 6px of horizontal scroll came from; the
     inset belongs on the container. */
  margin: 4px 0;
  background: rgba(26, 15, 53, 0.55);
}
.console-workbench { overflow-x: hidden !important; }
/* No side gutter of its own: what it holds carries the shared one, and two would
   stack. Top and bottom are the exception - the section row sits directly above and
   the section's own edge directly below, and without this the content is flush to
   both and reads as cut off at each end. */
.console-workbench-body { padding: 8px 0; }
.console-workbench .q-expansion-item .q-item {
  min-height: 32px;
  padding: 2px 10px;
}
.console-workbench .q-expansion-item .q-item__label {
  color: var(--accent); font-size: var(--fs-caption);
}
.console-workbench .q-expansion-item__content { padding: 2px 0 6px; }
/* nicegui puts a 16px flex gap on .nicegui-expansion-content, which double-spaced every
   line inside a section: 22px rows on a 38px pitch. Same default as the drawer's, in a
   different container - the rows carry their own spacing. */
.console-workbench .nicegui-expansion-content {
  /* Both of nicegui's defaults on this container: the 16px gap double-spaced the lines
     and the 16px padding is the dead space above the first field and below the last. */
  gap: 0 !important;
  padding: 0 !important;
}
/* The panel toggles match: nav and workbench are the same control, same color. */
.console-panel-header .q-icon { color: var(--ink-2); }
.console-workbench .q-expansion-item__content .row { min-height: 22px; }
.console-nav-title {
  /* .manager-title, sampled: --ink with --glow-cyan behind it at 20px/900. The white
     comes from the near-white glyph and the color from the halo, which is why a cyan
     glyph and a flat one both read wrong. */
  font-family: sans-serif;
  font-size: var(--fs-title);
  font-weight: 900;
  color: var(--ink);
  text-shadow: 0 0 4px rgba(0, 217, 255, 0.5), 0 0 8px rgba(0, 217, 255, 0.3);
}

.nicegui-aggrid {
  border: 1px solid var(--line-strong);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(180, 41, 249, 0.2);
}
.ag-header {
  /* 2.x's --header-gradient in full - I had been running it to #4a1e7c and stopping,
     which lost the fade to near-black at the far end. */
  background: linear-gradient(135deg, var(--flair) 0%, #4a1e7c 50%,
              var(--surface-0) 100%) !important;
  border-bottom: 1px solid var(--line-strong) !important;
}
/* Sampled from 2.x's th: --ink at 12px/600, uppercase, no added tracking. */
.ag-header-cell-text {
  /* pre, not pre-line: the header breaks only where a newline was put deliberately.
     pre-line also lets it wrap on its own, which split words a letter from the end. */
  white-space: pre;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: center;
  line-height: 1.25;
  font-family: sans-serif;
  font-size: var(--fs-caption);
  font-weight: 600;
  letter-spacing: normal;
  text-transform: uppercase;
  color: var(--ink) !important;
}
.ag-header-cell-menu-button, .ag-header-icon { color: rgba(255,255,255,0.85) !important; }
/* The filter button is the first child of the label container, so the container's
   direction decides which side it lands on - and AG Grid reverses it for a numeric
   column. That put the icon at the left edge on numbers and the right edge on
   everything else, so the eye had to hunt for it per column. The icon sits right on
   every column now; the header text stays right-aligned over its digits. */
.ag-right-aligned-header .ag-cell-label-container { flex-direction: row-reverse; }
/* And a gap, so the label never runs into the icon. On a left-aligned header the label
   takes the slack and there is space anyway; on a right-aligned one the text ends flush
   against it, which is where "Table Count" and "Rating" read as tight. */
.ag-cell-label-container { gap: 8px; }
"""


def apply_flair() -> None:
    # Tokens first: everything after this refers to them.
    ui.add_css(_TOKENS)
    ui.add_css(_FLAIR)
    ui.add_css(_COMPONENTS)


def apply_colors(dark: bool) -> None:
    """Swap the palette. The page owns the single ui.dark_mode element and passes its
    value in - creating one per call leaves several fighting over the same body class."""
    ui.colors(**(DARK if dark else LIGHT))


# Components added with the section build-out. Kept apart from _FLAIR so the palette
# work and the component work stay legible as two things.
_COMPONENTS = """
/* --- media map ------------------------------------------------------------------ */
.console-mediatile {
  flex: 1 1 0;
  min-width: 0;
  /* A column, so the caption sits at the foot of whatever height the row settles on
     rather than at the foot of its own art. */
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  border-radius: 6px;
  /* A step *up* from the ground, not down into it. This used to be the page color at
     55%, which darkened the panel's gradient into a recessed plate - but with browse
     open to the page that same value composites to exactly the page and the tile has
     no surface at all, leaving an empty slot as a bare 1px outline. A tile is a small
     panel, and panels step up. */
  background: rgba(26, 15, 53, 0.6);
  padding: 3px;
}
/* Present is stated with a color, missing with the absence of one. A library is mostly
   gaps, so making the gap loud would make the workbench unreadable. */
/* Status and selection cannot share a channel. Cyan answers "which one"; a filled
   slot is shown by the art itself. Amber stays - "borrowed" looks filled and is a gap,
   which is the one state the art cannot tell you. */
.console-mediatile--present { border-color: var(--line); }
.console-mediatile--borrowed { border-color: rgba(255, 176, 32, 0.65); }
.console-mediatile--missing { border-style: dashed; opacity: 0.55; }
.console-mediatile--on {
  box-shadow: 0 0 0 2px var(--accent); border-color: var(--accent);
}

/* Flat buttons are text, and Quasar gives them `primary` - the flair color, at 4.4:1.
   Element-qualified because that is what outranks Quasar's own .text-primary, which
   matches ours and loads after it. */
.q-btn--flat, .q-btn--flat .q-icon,
button.q-btn--flat.text-primary, button.q-btn--flat.text-primary .q-btn__content {
  color: var(--ink-2) !important;
}
.q-btn--flat:hover, .q-btn--flat:hover .q-icon,
button.q-btn--flat.text-primary:hover,
button.q-btn--flat.text-primary:hover .q-btn__content {
  color: var(--ink) !important;
}
.q-btn--flat.text-negative, .q-btn--flat.text-negative .q-icon { color: var(--danger); }

/* An action has to look like one, and color alone never says so - it is silent to
   anyone who cannot see the hue. The border is the affordance; hover fills it. */
.console-action.q-btn {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 3px 10px !important;
  background: rgba(255, 255, 255, 0.02);
}
.console-action.q-btn:hover {
  border-color: var(--accent);
  background: rgba(0, 217, 255, 0.10);
}
/* The same control at the chip's scale, for an action that sits beside a state rather
   than after a field. The edge stays - without one it reads as a second value, and this
   panel is worked in rather than read - but the type comes down: measured beside a chip
   at 11px/400 the panel button sat at 12px/500 and was the louder half of the pair. */
.console-action--inline.q-btn {
  font-weight: 400;
  padding: 3px 8px !important;
  /* Hugs the chip it sits beside rather than taking the pointer floor every other
     control clears. The exception is deliberate and it is the only one: this verb is a
     second control on a row that already has a value, and a box half again the height
     of the state it changes reads as the row's subject. A finger gets the floor back,
     below. */
  min-height: var(--target-inline);
  line-height: 1;
}
.console-action--inline .q-btn__content {
  font-size: var(--fs-caption) !important;
  /* A verb never wraps. The value column is 177px, and "Choose this one" broke across
     three lines and took the row to 49px in a 26px rhythm. */
  flex-wrap: nowrap;
  white-space: nowrap;
}

/* A destructive action is still an action - it takes the same shape and says what it
   is with color on top, not instead. */
.console-action.console-action--danger.q-btn { border-color: rgba(255, 107, 157, 0.45); }
.console-action.console-action--danger.q-btn:hover {
  border-color: var(--danger); background: rgba(255, 107, 157, 0.12);
}

/* `size=sm` writes an inline font-size, which no selector outranks. */
.q-btn--dense .q-btn__content { font-size: var(--fs-caption) !important; }
.q-btn--dense { font-size: var(--fs-caption) !important; }

/* Every control clears the pointer floor - what is fine for a mouse is mean on a
   trackpad. Dense rather than flat, because the toolbar tabs are `unelevated`. */
.q-btn--dense, .console-section-row {
  min-height: var(--target-min);
}
.console-mediatile-art {
  width: 100%;
  /* A backstop, not the layout. The ratio decides the shape; this stops a portrait
     tile in a wide map from growing taller than the rows around it are worth. */
  max-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 4px;
  background: #06030f;
}
/* NiceGUI wraps raw HTML in a plain div, and a percentage height resolves against
   that - which has none. `display: contents` takes it out of layout so the media is
   the flex child and 100% means the box it is actually in. */
.console-mediatile-art > div { display: contents; }
.console-mediatile-art img, .console-mediatile-art video {
  width: 100%; height: 100%; object-fit: contain;
}
/* On hover and over the art: the tile has no room for a control wanted occasionally.
   Touch has no hover, and reaches this through the slot's own Enlarge. */
.console-mediatile-art { position: relative; }
/* An empty slot the catalog can fill. Quiet: it is information, not a warning - a
   library is allowed to be missing a topper, and amber here would shout on every
   second tile. */
.console-mediatile-offered { color: var(--ink-3); opacity: 0.7; }
.console-mediatile:hover .console-mediatile-offered { opacity: 1; color: var(--accent); }
.console-mediatile-zoom {
  position: absolute; top: 2px; right: 2px; opacity: 0;
  background: rgba(10, 5, 24, 0.7) !important; transition: opacity 120ms ease;
}
.console-mediatile:hover .console-mediatile-zoom { opacity: 1; }

/* A panel over the page, sized by its content, so the media decides how big it is. */
.console-viewer-card {
  background: #0b0520 !important;
  max-width: 92vw; max-height: 88vh;
  display: flex; flex-direction: column;
  padding: 0 !important; overflow: hidden;
  border: 1px solid var(--line); border-radius: 10px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}
.console-viewer-bar {
  flex: 0 0 auto; padding: 8px 12px;
  background: rgba(11, 5, 32, 0.9); border-bottom: 1px solid var(--line);
}
/* Darker than Quasar's default: the art being judged is often bright. */
.q-dialog__backdrop { background: rgba(4, 2, 12, 0.78) !important; }
/* The video's transport, in the bar so it stays upright while the picture turns. */
.console-viewer-transport { display: flex; align-items: center; gap: 10px; width: 100%; }
.console-viewer-btn {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 50%; cursor: pointer;
  background: transparent; border: none; color: var(--ink-2);
}
.console-viewer-btn:hover { background: rgba(180, 41, 249, 0.18); color: var(--ink); }
.console-viewer-btn .material-icons { font-size: var(--fs-title); }
.console-viewer-seek { flex: 1 1 auto; min-width: 0; accent-color: var(--accent); cursor: pointer; }
.console-viewer-clock {
  font-size: var(--fs-caption); color: var(--ink-2); white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

/* The stage owns the wheel and the drag, so a pinch magnifies the art rather than
   asking the browser to zoom a page that has nothing to scroll. */
.console-viewer-stage {
  overscroll-behavior: contain; touch-action: none;
  user-select: none; -webkit-user-select: none;
}
.console-viewer-stage img, .console-viewer-stage video {
  -webkit-user-drag: none; user-select: none;
}

.console-viewer-stage {
  /* Sized by the media. A rotated element reports its untransformed box, and the turn
     is about its own center, so that box is the right thing to center on. */
  flex: 1 1 auto; min-height: 0;
  display: flex; align-items: center; justify-content: center; overflow: hidden;
}
.console-mediatile-cap {
  /* Takes up the slack, so captions share a line whatever sits above them. */
  margin-top: auto;
  display: block;
  font-size: var(--fs-caption);
  line-height: 1.3;
  text-align: center;
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.console-mediatile-rule {
  height: 1px; width: 100%; margin: 8px 0 5px; background: var(--line-soft);
}
.console-mediatile-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  width: 100%;
}

/* --- section chrome -------------------------------------------------------------- */
/* The page's own name. It replaced a slash-delimited pair whose first half was a
   constant and whose second was the only real segment - a breadcrumb shape over
   something with no path in it, and nothing was clickable.

   The first text in the Console above body size: every other heading here is 12px
   uppercase, so this is the top of the scale rather than another rung on it. No glow -
   that belongs to the workbench title, which names the thing you selected. */
.console-page-title {
  font-size: var(--fs-title);
  font-weight: 600;
  color: var(--ink);
  /* 32px, which is the height of the small buttons beside it. Centring in the band
     aligns boxes, and boxes of different heights put their text on different
     baselines - matching the height is what actually puts them on one line. */
  line-height: 32px;
}
.console-card {
  border: 1px solid var(--line);
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(26,15,53,0.75) 0%, rgba(15,7,34,0.75) 100%);
  padding: 14px 16px;
}
.console-card-title {
  font-size: var(--fs-caption);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
}
.console-kpi {
  font-size: var(--fs-display); font-weight: 700; color: var(--ink);
  line-height: 1.1;
}
/* The explanation under a control, not a tooltip on it. This is the whole legibility
   argument for the settings pages, so it gets a class rather than ad-hoc utilities. */
.console-help {
  font-size: var(--fs-caption); color: var(--ink-3); line-height: 1.4;
  max-width: 62ch;
}
.console-setting { font-size: var(--fs-body); color: var(--ink); font-weight: 600; }
.console-group {
  font-size: var(--fs-caption);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  padding: 10px 8px 4px;
}
/* A heading that can carry a corner mark. The gutter is reserved on every one of them
   for the same reason the rows reserve theirs. The mark sits on the caption's own line
   and in the rows' column: the heading has no row margin, so matching the rows below
   costs it that 8px, and a mark floating in the gap above the words reads as belonging
   to the row before it. */
.console-rail-group { position: relative; padding-right: 34px; }
/* A heading's padding is 10px over 4px, so its box centre sits 3px above its text.
   Nudged back down onto the caption, and 8px further left because a heading has none of
   the row margin below it - which is what puts the two marks in one column. */
.console-rail-group .console-trouble-mark { margin-top: 3px; right: 14px; }
/* The outline: a table of contents down the side of the workbench. Quiet, because
   what it points at is the content - an open section is lit and the rest recede. */
/* The lens: which build the sections under it answer for. Pills rather than a
   dropdown so the choice and the alternatives are both visible, truncated because a
   .vpx name runs long and the whole one is a hover away. */
/* In the panel header now, so it wraps to the width it is given rather than to the
   section it used to sit in. */
/* The file, under the game it belongs to. Cut from the front for the same reason the
   picker was: what tells two tables of one game apart is at the end. */
.console-workbench-table {
  font-size: var(--fs-caption); color: var(--tier-table);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;
}
/* Body and dock, and one rule for where the dock goes. Under the body it is a
   vertical split - the map scrolls, the controls do not, and picking a tile can never
   put them somewhere you have to go looking. Past the work width they sit side by
   side instead, which is what the room is for. */
.console-section-work { display: grid; grid-template-columns: minmax(0, 1fr); min-height: 0; }
.console-has-dock {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  /* The cap goes on the row, not on the dock: a percentage max-height on a grid item
     resolves against its own auto-sized area, which is circular, and Chrome settles it
     at a fraction of what was asked for. On the row it resolves against the grid, which
     is a real height - and fit-content, because a percentage in minmax() makes the track
     that size outright, so the dock would hold 45% whether it needed it or not. */
  /* A stored height, not fit-content, or the divider moves with whatever is in it.
     The grip row is what you drag. */
  grid-template-rows: minmax(0, 1fr) auto var(--dock-h, 300px);
  min-height: 0;
}
@container (min-width: 900px) {
  .console-has-dock {
    /* `auto` so the track follows the dock's own width. */
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-rows: minmax(0, 1fr);
    grid-template-areas: none;
  }
  /* Half the workbench, so a wide window has no dead middle. The floor keeps it
     usable where half is not much. */
  .console-dock { width: max(320px, 50cqw); }
}
/* The handle between browse and work. Only where they are stacked - side by side the
   split is the panel's own width, which the outer splitter already owns. */
/* A short centered handle, not a full-width rule. It used to draw a hairline right
   across the panel, which is the same picture the section separators draw - so the
   panel had three horizontal lines of the same weight meaning two different things,
   and the band below the open section read as belonging to whatever was above it.
   A stub you could put two fingers on says "drag me" and says nothing else. */
.console-dock-grip {
  height: 19px; cursor: row-resize; flex: 0 0 auto;
  display: flex; align-items: center; justify-content: center;
}
.console-dock-grip::before {
  content: ""; width: 44px; height: 4px; border-radius: 2px;
  background: var(--resize-line);
}
.console-dock-grip:hover::before { background: var(--accent); }
/* The work region keeps its room whether or not anything is in it: collapsing it
   reflows browse under the cursor that just picked something. */
/* Centered in the reserved room: text in the top corner reads as a mistake. */
.console-dock-empty {
  margin: auto; text-align: center; padding: 16px; max-width: 34ch;
}
.console-dock-empty-title { font-size: var(--fs-body); color: var(--ink-2); }
.console-dock {
  /* Room on every side, or the panel's own border sits flush to the edge and loses
     its right side under the scrollbar. No border-top: the grip is the divider. */
  padding: 4px var(--panel-gutter) var(--panel-gutter);
  overflow: auto;
  /* Named: the workbench is a container too, and what fits here depends on this
     region's width rather than the panel's. */
  container: dock / inline-size;
  /* Reserved either way, so the inset does not shift when a scrollbar appears. */
  scrollbar-gutter: stable;
}
@container (min-width: 900px) {
  .console-dock { border-top: none; border-left: 1px solid var(--line); }
  /* Below the grip's own rules on purpose: same specificity, so source order decides.
     Above them this loses to the `display` they set, and the handle shows up floating
     at the top of a layout where the dock is beside the map and there is nothing to
     drag. */
  .console-dock-grip { display: none; }
}

/* Takes the panel. A 420px cap used to stop four fields stretching across a window,
   but these are facts before they are fields, and it cropped a hash at 420px with the
   rest of a 1100px panel left blank - which reads as broken, not as restraint. The
   width still bounds it, so a long filename ellipsizes inside the panel rather than
   running off it; there is simply more panel to use first. A cap belongs on an input,
   where a 900px text box is genuinely useless, not on the text. */
.console-form { width: 100%; }

/* The facts a section is *for*, so they read at body size like everything else. They
   used to be captions - 12px label and 12px value, smaller than the section heading
   above them, which ranked the content below its own title. */
.console-facts {
  display: grid;
  /* Capped, and low enough that the cap is the common case rather than the exception.
     One long label should cost its own row two lines, not move every control on the
     page away from the label naming it - and the eye crossing a gutter to reach a
     control is the thing that made a settings page hard to read. The pane's labels sit
     under this and never wrap. */
  grid-template-columns: fit-content(var(--label-max)) 1fr;
  /* One box per row, whatever the value is, so nothing grows when a field or a chip
     lands in a row that had text. `auto` above the floor is for content that wraps -
     a line of chips takes two rows' worth and keeps its label centred on them. */
  grid-auto-rows: minmax(var(--fact-row), auto);
  align-items: center;
  column-gap: 8px;
  width: 100%;
  padding: 0 12px;
}
/* Dimmed, not also shrunk - which this file has said for a while and only half did. The
   value moved to body size and the label stayed a caption, so a label was a size below
   the value it names and only one step of grey from the help under it. Contrast is the
   lever: --ink-2 is the documented secondary at 11.1:1, and the help is --ink-3 at the
   caption size, so the three read as three. */
.console-fact-label { font-size: var(--fs-body); color: var(--ink-2); line-height: 1.3; }
.console-fact-value { font-size: var(--fs-body); color: var(--ink); }
/* One line of chips sits on the same pitch as every other row, and a wrapped one grows
   symmetrically around its label. The row carries the height rather than the label
   carrying a nudge: two hand-tuned paddings here put this row 28px into a 26px rhythm
   and moved the label whenever the chips wrapped. */
.console-chips {
  display: flex; flex-wrap: wrap; gap: 4px; min-width: 0;
  min-height: var(--fact-row);
  align-content: center;
  /* Room above and below, or a wrapped block runs into the rows either side of it -
     the 26px pitch is a text row's, and this one is several. */
  padding: 5px 0;
}

/* A value the user may set. The read state and the edit state are one element, so the
   alignment cannot drift and nothing moves on the first click. */
.console-fact-edit { display: flex; align-items: center; gap: 8px; min-width: 0; }
/* An action follows the value it acts on. It used to be pushed to the panel's right
   edge for a column of verbs, which assumed the value fills the row: a stretching field
   ends near that edge, but a chip is 60px wide and the verb landed a panel-width away
   from the state it changes - further the wider the pane was dragged. Fields still line
   up under this, because they stretch to the same width. */
.console-edit-field { flex: 1 1 auto; min-width: 0; }
/* The same edge as an action, because it is the same kind of thing: something you can
   act on. A single bottom rule was meant to be the quiet version of this and read as a
   section divider instead - full width, between two rows, which is what a divider is. */
.console-edit-field .q-field__control {
  /* Quasar's 40px was tolerable as an underline and is a lump as a box: the row rhythm
     is 26px, and a field that stands 14px above it makes its own row taller than every
     fact around it. Below the pointer floor, and raised back on touch with the inline
     action - the two exceptions are the same exception. */
  min-height: var(--field-h);
  height: var(--field-h);
  border: 1px solid var(--line);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
  padding: 0 8px;
  transition: border-color 120ms, background 120ms;
}
.console-edit-field .q-field__control::before,
.console-edit-field .q-field__control::after { border: none; }
/* No cap. 56ch was tried and cropped "/Users/.../VPinballX/10.8/VPinballX.ini" with room
   to spare beside it, which is the failure this file already describes: a cropped value
   reads as broken, not as restraint. A settings page is mostly long paths, so the width
   is what it is for. */
/* A whole number, sized for one. In a full-width box the value reads as something that
   might be long, and a page of them is a column of mostly empty boxes. */
.console-edit-narrow { width: 96px; flex: 0 0 auto; }
/* A closed list of named things, sized to the names rather than to the panel. Text
   stretches because what you type has no length; a set of options does, and "daily" in
   a 1100px box says the answer might be a sentence. The floor is for the caret and the
   longest name the set happens to hold, not a target. */
.console-edit-select { flex: 0 1 auto; min-width: var(--select-min); }
/* Except where the list holds addresses. The rule above is for a closed set of named
   things, where a wide box says the answer might be a sentence; a URL is exactly the
   answer that needs the room, and it can also be typed. */
.console-edit-combo { flex: 1 1 auto; }
.console-edit-field:hover .q-field__control {
  border-color: var(--accent);
  background: rgba(0, 217, 255, 0.06);
}
.console-edit-field .q-field--focused .q-field__control {
  border-color: var(--accent);
  background: rgba(0, 217, 255, 0.10);
}
/* What you typed is data, like a grid cell, so it rests at --ink-2 rather than the
   pure white Quasar leaves it at. A settings page is mostly long file paths in wide
   boxes, and at 18.8:1 - brighter than the top of our own scale - that is the loudest
   thing on the page while being the part you are not currently reading.

   The field you are actually in comes up to --ink. That is the one you are working on,
   and it is the only one that needs to be. */
.q-field__native,
.q-field__input { color: var(--ink-2); }
.q-field--focused .q-field__native,
.q-field--focused .q-field__input { color: var(--ink); }
/* Not a value - a prompt for one. It reads as the quiet step everything explanatory
   takes, rather than as dimmed white. */
.q-field__native::placeholder,
.q-field__input::placeholder { color: var(--ink-3) !important; opacity: 1; }

.console-edit-field .q-field__native {
  font-size: var(--fs-body); color: var(--ink); padding: 0;
}
/* A select's value is a span, not an input, and Quasar gives that span a min-height and
   a top padding sized for its own 40px control. At our 26px row the value sits below
   the box and reads as cropped - which is why the lists looked wrong and the text
   fields beside them did not. Centred in the control instead, at the height we set. */
.console-edit-select .q-field__control-container { padding-top: 0; }
.console-edit-select .q-field__native {
  min-height: 0;
  padding: 0;
  align-items: center;
  line-height: normal;
}
/* The caret sits with the value rather than on the control's own baseline. */
.console-edit-select .q-field__append {
  height: var(--field-h);
  padding-left: 4px;
  align-items: center;
}
/* The way back, and the only mark an overridden row carries. Amber because that is
   already this app's word for the exception worth spotting, so one mark says both what
   the state is and what to do about it. */
.console-revert {
  color: var(--tier-table); font-size: 16px; cursor: pointer; flex: 0 0 auto;
  opacity: 0.8;
}
.console-revert:hover { opacity: 1; }
/* The one control for a yes or no. Its own height, which the row takes - a switch is
   a control, and text rows are what the 26px pitch is for. */
.console-fact-switch .q-toggle__inner { font-size: 28px; }
.console-fact-switch.disabled { opacity: 0.65 !important; }

/* A group's name, spanning the grid so every group keeps the one shared label column.

   The rule and the space carry the break. The weight is what puts a group title above
   the labels it governs, and uppercase with tracking is what tells it from one. */
.console-fact-heading {
  grid-column: 1 / -1;
  /* .console-card-title's treatment: a heading inside a panel is cyan and uppercase
     wherever one appears here, so a group's name is one too. */
  font-size: var(--fs-caption);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  border-top: 1px solid var(--line-soft);
  margin-top: 14px;
  padding: 12px 0 4px;
}
/* The first group opens the section - there is nothing above it to be separated from,
   and a rule there would read as the section's own top edge. */
.console-facts > .console-fact-heading:first-child {
  border-top: none; margin-top: 0; padding-top: 0;
}
/* Actions and the attention block: the width of the panel, not of a value. */
.console-fact-full { grid-column: 1 / -1; padding: 4px 0; min-width: 0; }
/* A line about the control above it, so it sits under the control and not under the
   label - across both columns it starts at the label's edge and reads as a caption for
   the label instead. Tight to what it explains and loose to the next row, which is what
   groups the two without a rule between them. */
.console-fact-aside { grid-column: 2; padding: 0 0 8px; min-width: 0; }

/* What is wrong with this thing, before anything merely true about it. Amber, which is
   already the exception color here - not red: none of these is an error, they are
   things to go and fix. */
.console-attention {
  display: flex; align-items: flex-start; gap: 8px; min-width: 0;
  border: 1px solid rgba(255, 192, 97, 0.35);
  background: rgba(255, 192, 97, 0.07);
  border-radius: 6px; padding: 6px 10px;
}
.console-attention-icon { color: var(--tier-table); font-size: 18px; flex: 0 0 auto; }
.console-attention-line { font-size: var(--fs-body); color: var(--ink); }
/* One detail against its replacement. The old value is struck rather than merely dim:
   it is not a lesser version of the new one, it is the wrong machine's. */
.console-diff-field {
  font-size: var(--fs-caption); color: var(--ink-3);
  flex: 0 0 auto; min-width: 72px;
}
.console-diff-was {
  font-size: var(--fs-caption); color: var(--ink-3);
  text-decoration: line-through; flex: 0 1 auto;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.console-diff-arrow { font-size: 14px; color: var(--ink-3); flex: 0 0 auto; }
/* The picked slot. The art is the subject and takes the room; the facts under it are
   a line each, which is what lets them be sentences rather than a table of fields. */
.console-slot {
  border: 1px solid var(--line); border-radius: 8px;
  background: linear-gradient(180deg, rgba(26,15,53,0.75) 0%, rgba(15,7,34,0.75) 100%);
  display: flex; flex-direction: column; min-height: 0;
  /* Without this the column is sized by its contents and overhangs the panel, which
     is what put a horizontal scrollbar under a narrow dock. */
  min-width: 0;
}

/* Takes what is left after the text, down to nothing - so in a short dock the art
   shrinks and the sentences stay on screen, rather than the actions going below
   the fold. */
.console-slot-art {
  /* min-height:0 is what lets this shrink at all: a flex item's floor is its content
     by default, so the picture would push the facts under it off the panel instead of
     giving up room. The floor that keeps it looking like a picture is on the blank
     state, which has no content to be sized by. */
  flex: 1 1 auto; min-height: 0; overflow: hidden; display: flex;
  align-items: center; justify-content: center;
  padding: 4px 0 8px; position: relative;
}
/* On the art, the way the map's tiles do it - so the same gesture works in both
   places and the title row is a title again. */
.console-slot-zoom {
  position: absolute; top: 6px; right: 2px; opacity: 0;
  background: rgba(10, 5, 24, 0.7) !important; transition: opacity 120ms ease;
}
.console-slot-art:hover .console-slot-zoom { opacity: 1; }
/* The preview wraps its element in a div of its own, and that wrapper is what broke
   fitting the art. Flex shrinks this box when the panel is short, but shrinking a box
   does not shrink what is inside it - and the picture's `max-height: 100%` resolved
   against the wrapper, which has no height of its own, so it meant nothing and the art
   came out cropped top and bottom.

   `display: contents` takes the wrapper out of layout without taking the picture out
   of the document, so the picture is the flex item and flex-shrink applies to it
   directly. Nothing else tried worked: clamping the wrapper moved the overflow down a
   level, positioning it collapsed this box - which is sized by its content - and a
   size container cannot be one without a definite height, which is the thing missing.
   Excludes the blank state, which is a column that lays itself out. */
.console-slot-art > div:not(.console-slot-zoom):not(.console-slot-blank) { display: contents; }
.console-slot-art img, .console-slot-art video {
  max-width: 100%; max-height: 100%; object-fit: contain;
  min-height: 0; flex: 0 1 auto;
  border-radius: 4px; border: 1px solid var(--line);
}
/* Audio has no frame, so it is the control itself and takes the width it is given
   rather than being sized like a picture. */
.console-slot-art audio { width: 100%; }

/* An empty slot is still the shape of the thing that goes in it: the outline holds
   the same room the art would, so picking an empty slot does not resize the panel. */
.console-slot-blank {
  width: 100%; height: 100%; min-height: 90px;
  border: 1px dashed var(--line); border-radius: 6px;
  justify-content: center; color: var(--ink-3);
}
.console-slot-blank-icon { font-size: 34px; opacity: 0.55; }

.console-slot-facts { min-width: 0; }
/* The filename is the one identifier a user recognizes, so it reads first and whole -
   these names are long and the interesting half is usually the tail. */
.console-slot-file {
  font-size: var(--fs-body); color: var(--ink-2); word-break: break-all;
  line-height: 1.35;
}

/* The losers. Set apart by a rule rather than a heading weight, because the point is
   that they are the same slot - not a new section. */
.console-slot-others {
  border-top: 1px solid var(--line-soft); margin-top: 6px; padding-top: 5px;
  min-width: 0;
}
.console-slot-others-title {
  font-size: var(--fs-caption); text-transform: uppercase; letter-spacing: 0.07em;
  color: var(--ink-3); padding-bottom: 2px;
}
/* Shrinks but does not grow: given the width of a full-window panel, a growing
   label would put the filename and the phrase that explains it at opposite ends. */
.console-slot-other-file {
  font-size: var(--fs-caption); color: var(--ink-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
  flex: 0 1 auto;
}

/* Who is not using the file above. Set off the same way the outranked files are,
   because it is the same kind of fact: this slot is not the whole story. */
.console-slot-differs {
  border-top: 1px solid var(--line-soft); margin-top: 6px; padding-top: 5px;
  min-width: 0;
}

.console-slot-actions { padding-top: 8px; }

/* Room to judge the art when there is width to spare: at 240px a backglass in a
   half-window panel is a thumbnail beside a lot of nothing, and judging art is what
   this view is for. */
@container (min-width: 900px) {
  .console-slot-art { min-height: 200px; }
  .console-slot-art img, .console-slot-art video { max-height: min(52vh, 520px); }
}

/* --- who owns a file, wherever a file is shown -------------------------- */

.console-tier {
  font-size: 11px; letter-spacing: 0.04em; line-height: 1.5;
  padding: 0 6px; border-radius: 999px; border: 1px solid transparent;
  white-space: nowrap; flex: 0 0 auto; align-self: center;
}
/* Filled, because this is the exception in a folder and the one worth spotting. */
.console-tier--table {
  color: var(--tier-table); border-color: rgba(255, 192, 97, 0.45);
  background: rgba(255, 192, 97, 0.12);
}
/* Outlined and quiet: the common case should be readable, not loud. */
.console-tier--game { color: var(--tier-quiet); border-color: var(--line); }
/* Dashed, because nothing is actually here - something else is filling in. */
.console-tier--standin {
  color: var(--tier-quiet); border-style: dashed; border-color: var(--line);
}
/* Nothing to own. Shown only where a row has to line up with others that carry one. */
.console-tier--missing { color: var(--ink-3); border-color: transparent; opacity: 0.5; }

/* Below .console-tier, not above it. That base sets `border` as a shorthand, so a
   border-color declared earlier is reset to transparent by it - equal
   specificity, and source order decides. */
/* Present, absent, and not yet known. A state chip is not a media tier: those answer
   whose file this is, and their amber is the exception worth spotting. Green is
   present here; amber is reserved for something to go and fix. */
.console-tier--on {
  color: var(--positive); border-color: rgba(0, 255, 159, 0.45);
  background: rgba(0, 255, 159, 0.12);
}
.console-tier--off {
  color: var(--ink-2); border-color: rgba(155, 139, 189, 0.55);
  background: rgba(155, 139, 189, 0.10);
}
.console-tier--unknown {
  color: var(--ink-2); border-style: dashed;
  border-color: rgba(155, 139, 189, 0.55);
  background: rgba(155, 139, 189, 0.06);
}
/* Broken, not merely absent: what this names stops the table working at all. The one
   red on the panel, so it means exactly that and nothing softer. */
.console-tier--bad {
  color: var(--danger); border-color: rgba(255, 107, 157, 0.45);
  background: rgba(255, 107, 157, 0.12);
}
/* Dashed, because the thing it names is not there. */
.console-tier--warn {
  color: var(--tier-table); border-style: dashed;
  border-color: rgba(255, 192, 97, 0.45);
}

/* On a map tile the badge sits over the art, top left, opposite the enlarge. */
.console-mediatile-tier {
  position: absolute; top: 3px; left: 3px;
  background: rgba(10, 5, 24, 0.72);
}
.console-mediatile-tier.console-tier--table { background: rgba(40, 24, 8, 0.85); }

/* The view has drifted from what it says it is, said on the control that names it.
   Quiet - a modified view is an ordinary thing to be in, not a warning - but it has to
   be visible or the picker is lying. */
.console-view-picker .q-field__suffix {
  font-size: var(--fs-caption); color: var(--tier-table); opacity: 1;
  padding-left: 6px;
}

/* A tick column is scanned, not read: center it so the eye runs down one line. */
/* Green, not accent. `docs/conventions.md`: green is present, and accent is the current
   value and nothing else - spending it on every true cell in a matrix is how it stops
   meaning anything. `.console-unknown` is the answer that is neither yes nor no, so it is
   quiet: an unread table is not a fault and must not read as one. */
.console-tick { text-align: center; color: var(--positive); }
.console-unknown { text-align: center; color: var(--ink-3); font-weight: 600; }

/* One or more tables here use something else. A bar rather than a badge: the tile is
   about a hundred pixels wide and already carries a tier badge and an enlarge, and a
   third piece of text on it is not read by anybody. The count is in the tooltip and
   the names are in the panel. */
.console-mediatile-differs {
  position: absolute; left: 0; right: 0; bottom: 0; height: 3px;
  background: var(--tier-table); font-size: 0; overflow: hidden;
}

/* --- where a slot's file can come from ---------------------------------- */

.console-sources-card {
  width: min(840px, 94vw); max-height: 84vh; gap: 6px;
  background: var(--surface-1); border: 1px solid var(--line);
}
/* A row that navigates rather than acting: the whole thing is the target, so it says
   so on hover instead of hiding a click behind a label. Separate from --folder, which
   is one of these and also a row with no picture in it. */
.console-source-row--pick { cursor: pointer; }
/* One line: these names carry the maker and year and run long, and four wrapped lines
   of one row makes a list of them unreadable. */
.console-source-row--pick .console-source-name {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  word-break: normal; min-width: 0;
}
.console-source-trail { word-break: break-word; padding-bottom: 2px; }
.console-source-row--pick:hover {
  border-color: var(--accent); background: rgba(0, 217, 255, 0.06);
}
/* The one decision every way in feeds, so it sits above them rather than inside one.
   Set off by a rule, because it is a different kind of thing from a tab. */
.console-destination {
  padding: 8px 4px 10px; border-bottom: 1px solid var(--line-soft);
}
.console-destination-name {
  padding-top: 4px; word-break: break-all; font-family: inherit;
}
/* Stated before the write, not only in the confirm afterwards - but kept quiet,
   because replacing a file is the ordinary case and not a warning. */
.console-destination-conflict {
  font-size: var(--fs-caption); color: var(--ink-2); padding-top: 2px;
}
/* One name the file could take. The whole row is the target: the mark is small and
   the name is the part being read, so asking for the mark would be a worse target
   than the thing it belongs to. */
.console-placement { padding: 4px 2px; cursor: pointer; border-radius: 4px; }
.console-placement:hover { background: rgba(255, 255, 255, 0.04); }
.console-placement-mark { font-size: 18px; color: var(--ink-3); margin-top: 1px; }
/* Accent, because this is the one chosen - which is what accent is for. */
.console-placement-mark--on { color: var(--accent); }
/* These are filenames and they run long. Wrapped rather than trimmed: what tells two
   of them apart sits in the middle, so an ellipsis at either end can eat it. */
.console-placement-name {
  font-size: var(--fs-body); color: var(--ink-2);
  word-break: break-word; line-height: 1.3;
}
/* A second heading in a panel that opened with one needs the air, or the list above
   reads as belonging to it. */
.console-source-under { padding-top: 10px; }

.console-sources-panels { min-height: 260px; }
/* Quasar paints its own ground on panels and on the tab bar. Left alone it is a pale
   slab in the middle of a dark dialog. */
.console-sources-panels, .console-sources-panels .q-tab-panel,
.console-sources-card .q-tabs { background: transparent; }
.console-sources-panels .q-tab-panel { padding: 12px 4px; }
/* Five sources have to fit without a scroll arrow: an arrow on a tab bar means the
   ways of doing this are hidden behind a control nobody looks for. */
.console-sources-card .q-tab { color: var(--ink-3); padding: 4px 10px; min-width: 0; }
.console-sources-card .q-tab--active { color: var(--accent); }
.console-sources-card .q-tab__indicator { background: var(--accent); }
/* Every tab is a list of candidates, and the dialog is capped - so the list scrolls
   inside it rather than the dialog growing past the window. */
.console-source-list { max-height: 52vh; overflow-y: auto; }
/* The online tab stacks two of these, and they are not equals: the games are how you
   get to the files, and the files are what you came for. Uncapped, a long search
   pushed the files off the bottom of the dialog with nothing to scroll. */
.console-source-found { max-height: 26vh; overflow-y: auto; }
.console-source-offers { max-height: 40vh; overflow-y: auto; }
/* A folder is a line, not a picture: it has no thumbnail, so it should not reserve
   the height of one. */
.console-source-row--folder { padding: 5px 8px; }
.console-source-row {
  border: 1px solid var(--line-soft); border-radius: 6px; padding: 6px 8px;
}
.console-source-name {
  font-size: var(--fs-body); color: var(--ink-2); word-break: break-all;
  line-height: 1.3;
}
.console-source-meta { word-break: break-all; }
/* Big enough to judge the art by, which is the question the row exists to answer.
   A backglass at 64px told you a file was an image and nothing else. */
.console-source-thumb {
  flex: 0 0 auto; width: 132px; height: 99px; border-radius: 4px;
  border: 1px solid var(--line); overflow: hidden; background: var(--surface-0);
  display: flex; align-items: center; justify-content: center;
  position: relative;
}
.console-source-thumb img, .console-source-thumb video {
  max-width: 100%; max-height: 100%; object-fit: contain;
}
/* A kind with no frame to show - audio, a rule sheet - keeps the same footprint, so a
   list of them does not step in and out as it scrolls. */
.console-source-thumb-glyph { font-size: 32px; color: var(--ink-3); }

/* A bigger look at a thumbnail, on hover. These rows live inside a dialog, and opening
   a second dialog over the first to glance at a picture is a lot of ceremony - so this
   is a preview and not the viewer. It rides in a tooltip because the lists around it
   scroll, and anything drawn inside a scrolling box is clipped by it. */
.console-thumb-peek {
  background: #0b0520 !important; padding: 4px !important;
  border: 1px solid var(--line); border-radius: 6px;
  max-width: none !important;
}
/* Slightly larger, not a viewer. Big enough and it covers the rows either side of the
   one being pointed at, which is the list you are reading. */
.console-thumb-peek img, .console-thumb-peek video {
  display: block; max-width: 300px; max-height: 40vh;
}
/* Recognising a machine is a smaller question than judging a piece of art, and this
   list is the long one - a dozen results at the full size is most of a screen. The
   enlarge is what covers the case where the small picture is not enough. */
.console-source-thumb--small { width: 76px; height: 57px; }
.console-source-thumb--small .console-source-thumb-glyph { font-size: 22px; }

/* What a file already does for this game, when it does something. Not a warning:
   using it again is legitimate, and the tag is there so nobody has to wonder. */
.console-source-tag {
  font-size: var(--fs-caption); color: var(--accent); opacity: 0.85;
}

/* Quasar keeps the queued-file list at full height while it is empty. Uploads are
   automatic here, so the list only ever flashes. */
.console-sources-card .q-uploader__list:empty { display: none; }
.console-sources-card .q-uploader { width: 100%; max-height: 220px; }
.console-sources-card .q-uploader__title {
  font-size: var(--fs-body); font-weight: 500; color: var(--ink-2);
}
.console-sources-card .q-uploader__subtitle { display: none; }
/* Quasar fills the header with the primary color. Magenta reads as "selected"
   everywhere else in this UI, and this is a drop target, not a selection. */
/* Element-qualified and forced, because Quasar sets the header's fill from the
   primary color with the same specificity a class selector has. */
.console-sources-card div.q-uploader__header {
  background: rgba(43,26,77,0.6) !important; border-bottom: 1px solid var(--line);
}
.console-sources-card .q-uploader { background: var(--surface-2); border: 1px solid var(--line); }
/* The dashed target is the affordance; without a border the strip reads as a heading. */
.console-sources-card .q-uploader__list {
  background: transparent; border: 1px dashed var(--line); border-top: none;
}

/* One markup, two readings. Wide, the rows are a rail down the left and the open
   section fills the column beside them. Narrow, they stack and the work falls under
   the row that opened it. Same control, same meaning, no threshold to guess: a rail
   with everything closed already looks like an accordion, so this is the same thing
   drawn in the room available.

   Two regions rather than a track per row, so the rows scroll on their own and the
   section beside them holds still. Narrow needs them loose again to interleave, which
   is what `display: contents` on the wrapper does down there. */
.console-sections {
  /* Off the header. The name of what you are looking at and the list of what you can
     ask about it are two things, and butted together they read as one block. */
  margin-top: 12px;
  /* The rail column is panel and everything right of it is open to the page. A hard
     stop at the column's own width does that without a wrapper element to hang a
     background on - the rows are grid children, so there is nothing else to paint. */
  /* One lever for the rail's width, because the same control serves a narrow pane and
     a full-width page and the number appears three times here. */
  --rail-w: 152px;
  background: linear-gradient(90deg, var(--panel-ground) 0 var(--rail-w),
                              transparent var(--rail-w));
  display: grid;
  grid-template-columns: var(--rail-w) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  min-height: 0;
}
/* The rows, as a region of their own. It scrolls when it is taller than the panel -
   thirteen entries in a short window - and the work beside it does not move, which is
   the whole reason the rows are wrapped rather than loose in the frame. */
.console-section-rail {
  grid-column: 1; grid-row: 1;
  display: flex; flex-direction: column;
  overflow-y: auto;
}
.console-section-row { grid-column: 1; }
/* A rail long enough to need grouping says what a run of rows is about. `.console-group`
   carries the treatment - this only puts it in the rail's column. */
.console-rail-group { grid-column: 1; }
.console-section-work {
  grid-column: 2; grid-row: 1;
  min-width: 0; min-height: 0;
  /* Still open to the page, just quieter. The grid is a fixed lattice the page owns
     and this content scrolls over it, so text lands on lines that move under it. A
     wash of the page's own color knocks the lattice back without closing the window -
     the alternative, a ground only under the text, is a card with an edge, and in Full
     that edge is a 400px stripe down a very wide region.
     Any alpha is a claim about what is behind it: this one is the page, and the tile
     fills inside here are measured against this. */
  background-color: rgba(10, 5, 24, 0.55);
  /* The window's two edges against the frame - left of it the rail, above it the
     header. Without the top one the panel just stops in mid-air where the paint ends. */
  border-left: 1px solid var(--line-soft);
  border-top: 1px solid var(--line-soft);
}
/* The workbench measures itself, so the layout changes the moment the drag crosses
   the width rather than when the mouse comes up. */
/* Above the page grid, which is a fixed z-index:0 layer and therefore paints over
   every unpositioned background beneath it - the band and the rail strip included, so
   "opaque" was not opaque. .nicegui-aggrid lifts itself the same way for the same
   reason. Being above it is also what lets the open region *dim* the grid rather than
   sit behind it: what shows through there is now the work region's own alpha. */
.console-workbench { container-type: inline-size; position: relative; z-index: 1; }

/* The splitter measures in pixels, so shrinking the window used to come entirely out
   of the list: the workbench held its width and the list was left with a Name column
   too narrow to read and a toolbar wrapped one word per line. A floor here makes the
   workbench give way instead - it shrinks gracefully because everything in it is
   already sized by its own width, and the list has nowhere to go. */
/* Said here rather than left to Quasar's default, so both dividers move together if
   the value ever changes. */
.q-splitter__separator { background-color: var(--resize-line) !important; }
.q-splitter__separator:hover { background-color: var(--accent) !important; }

.q-splitter__before { min-width: 380px; }

/* Full: the workbench takes the window and the list steps back to a rail. Quasar puts
   an inline width on the pane it sizes, so this swaps which of the two flexes rather
   than fighting that number - and being CSS, it lands the moment it is asked for. */
/* Hidden, not squeezed. A grid at 57px is not a rail - it is a grid with its toolbar
   wrapped into a column of single words. Nothing is stranded by this: the control that
   brings it back sits in the workbench header, which is always on screen. */
/* No subject on this page, so no pane - not even the rail. A rail is a pane you can
   bring back; there is nothing here to bring, and a strip whose only control reopens
   an empty panel is a control charged for nothing. The user's own open/closed and
   width are untouched, so returning to a page that has a subject restores them. */
.console-no-pane .q-splitter__after { display: none !important; }
.console-no-pane .q-splitter__separator { display: none !important; }
.console-no-pane .q-splitter__before {
  width: auto !important;
  flex: 10000 1 0% !important;
  min-width: 0 !important;
}

.console-full .q-splitter__before { display: none !important; min-width: 0 !important; }
.console-full .q-splitter__after { width: auto !important; flex: 10000 1 0% !important; }
.console-full .q-splitter__separator { display: none; }

/* The row is the section's only name - there is no heading under it repeating the
   same words. */
/* Sized as navigation, because that is what it is. Title case and smaller than the
   app nav: these are headings, so they take heading case - but not the nav's uppercase,
   which would rank a game's sections with the app itself. */
/* The app nav's gutter rhythm, so the two rails read as the same kind of control. */
.console-section-row {
  display: flex;
  cursor: pointer;
  font-size: var(--fs-body);
  font-weight: 500;
  color: var(--ink-2);
  padding: 0;
  margin: 2px 8px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* The state tints go on background-image, never background. As `background` they are
   the same property as the ground the bands paint on themselves, and a state selector
   outranks the plain one - so hovering replaced an opaque band with a 14% wash and the
   page showed through it, grid and all. As an image they layer over the ground instead
   of standing in for it, and they still work where the band paints nothing and the
   rail's strip is what shows through. */
.console-section-row:hover {
  background-image: linear-gradient(rgba(180, 41, 249, 0.14), rgba(180, 41, 249, 0.14));
}
/* Carries the row's padding, so every pixel of the band picks the section. The right
   gutter is wider than the left to hold a mark in the corner. Reserved on every row
   whether or not one is there: a badge that appears is not allowed to move the words
   under it, and a rail that reflows when a setting changes is worse than no badge.
   `relative` is what the mark is positioned against; `overflow: hidden` here and a
   scrolling rail outside both clip, so it sits inside the box rather than overhanging
   the way the nav's badge does. */
.console-section-hit { padding: 7px 26px 7px 16px; overflow: hidden; position: relative; }
/* Beside its content, not above it - so there is nothing for a chevron to point at
   and the rail carries no picture at all. */
.console-section-caret {
  display: none; color: var(--ink-2);
  padding: 0 12px;
  transition: transform 120ms;
}
.console-section-on .console-section-caret { color: var(--ink); }
.console-section-on {
  background-image: linear-gradient(rgba(0, 217, 255, 0.22), rgba(0, 217, 255, 0.22));
  color: var(--ink);
}

/* Below the base rules on purpose: same specificity, so source order decides. */
@container (max-width: 519px) {
  /* Column. The open section keeps a working height and the column scrolls past the
     rows it does not fit - a rail long enough to fill the panel leaves nothing to
     work in otherwise. */
  .console-sections {
    display: flex; flex-direction: column; background: none;
    /* The column scrolls now that the open section holds its height. The rows above it
       stay where they are and the ones below are a scroll away, which is the cost of
       giving the section room and the cheaper half of the trade. */
    overflow-y: auto;
  }
  /* The wrapper stops being a box, so the rows become items of the column above and
     the work can take its place among them. It exists for the wide rail's own
     scrollbar, and down here that scrollbar is the whole column's instead. */
  .console-section-rail { display: contents; }
  /* background-color, so a state tint layered on background-image sits over it. */
  .console-section-row { background-color: var(--panel-ground); }
  /* Takes what it needs and no more, so a short section does not leave a void with
     the rows stranded at the bottom edge.

     It no longer shrinks to keep every row on screen. That worked while a rail was
     three or four rows; a device carries sixteen, and they left the open section two
     lines to work in. With a rail that long the two cannot both fit, and the section
     is the one being used - so it keeps a working height and the column scrolls. */
  .console-section-work {
    flex: 0 0 auto;
    min-height: min(420px, 60%);
    border-left: none; border-top: none;
    /* Open to the page rather than tinted darker. The recess used to be a black wash
       over the panel's gradient, which was an invented shade meaning nothing; the step
       down to the page is a real one the rest of the app already uses. Still ruled off,
       or the content runs on into the header of the section below. */
    border-bottom: 1px solid var(--line-band);
  }
  /* Bands, not words. Stacked rows have to look like something that opens: full
     width, a rule under each, and the chevron on the right saying which way. Four
     labels floating in a column said nothing about being controls at all. */
  .console-section-row {
    flex: 0 0 auto;
    margin: 0; border-radius: 0;
    border-bottom: 1px solid var(--line-band);
  }
  .console-section-hit { padding-left: var(--panel-gutter); }
  .console-section-caret { display: flex; }
  /* Turned to point at what it opened, and the rule under the open row goes: the row
     and its content are one block, so a line between them would cut it in half. */
  .console-section-on .console-section-caret { transform: rotate(180deg); }
  .console-section-on { border-bottom-color: transparent; }
}

.console-index-item {
  border-radius: 6px; padding: 4px 10px; cursor: pointer;
  font-size: var(--fs-body);
                  color: var(--ink-2); }
.console-index-item:hover { background: rgba(180, 41, 249, 0.14); }
.console-bar { height: 6px; border-radius: 3px; background: rgba(255,255,255,0.08); }
.console-bar > div { height: 100%; border-radius: 3px; background: var(--accent); }
"""
