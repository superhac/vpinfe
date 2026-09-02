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
    "negative": "#ff0a78",
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
#
# `--flair` is the trap: magenta measures 4.4:1 here, under the 4.5:1 text needs. It is
# for fills, borders and selection. Text that must look interactive takes `--accent`.
_TOKENS = """
:root {
  --ink: #eef9ff;        /* primary text            18.7:1 */
  --ink-2: #cbb8ea;      /* secondary text          11.1:1 */
  --ink-3: #9b8bbd;      /* help and hints           6.5:1 */
  --accent: #00d9ff;     /* interactive text        11.8:1 */
  --positive: #00ff9f;   /* present, installed, in use */
  --flair: #b429f9;      /* fills and borders only   4.4:1 */

  --surface-0: #0a0518;
  --surface-1: #150a2e;
  --surface-2: #1a0f35;
  --line: #2b1a4d;
  --line-soft: #1f1338;
  /* Structure, not a hairline: the rule between stacked section bands has to be seen
     across a dark panel, and --line-soft sits close enough to the background that it
     read as nothing at all. */
  --line-band: rgba(203, 184, 234, 0.22);
  /* What a panel is, against the page under it. Named because two surfaces need to
     agree on it now that the workbench paints itself in parts. */
  --panel-ground: #150a2e;

  --fs-caption: 12px;
  --fs-body: 14px;
  --fs-subject: 16px;
  --fs-title: 20px;
  /* A stat, not prose - the one place a number is the content. */
  --fs-display: 30px;

  /* 44px where a finger is in scope; the hub is desk-first, so this is the floor. */
  --target-min: 32px;
  /* An action that sits beside a value rather than owning its row - see
     `.hub-action--inline`. Below the floor deliberately, and raised back to it where the
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

  /* What a draggable divider looks like, wherever one appears - a border color here
     reads as an edge rather than a handle. */
  /* Who owns a media file. Amber is the only warm color in this palette, which is
     what makes "one table's own" legible at a glance in a map of twenty tiles; the
     folder-wide case is the norm and stays quiet. Both measured against the surfaces
     they sit on: 11.1:1 and 5.9:1. */
  --tier-table: #ffc061;
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
body { background: #0a0518; }

/* nicegui gives .q-drawer__content 16px of padding and a 16px flex gap - the source of
   the workbench's 54px top gap, not anything the rows were doing. Scoped to the
   right drawer on purpose: the nav wants that breathing room, the workbench does not,
   because it has far more to fit. */
.hub-workbench {
  /* Gap goes, top padding stays: the gap was the double-spacing, but the 16px top is
     what puts this header level with the nav's, which keeps it. */
  padding: 16px 0 0 !important;
  gap: 0 !important;
}
/* 18px is what centring a 20px icon in the 57px rail produces, so matching it here
   means the icon does not move horizontally when the workbench collapses. */
.hub-workbench .hub-panel-header { padding-right: 18px !important; }
.q-page-container, .q-page { background: transparent !important; }
.q-drawer { background: #150a2e !important; }

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
     narrow - #1a0f35 against #251447 read as two different colors rather than as
     banding. */
  --ag-background-color: #140a2b;
  --ag-odd-row-background-color: #190e33;
  --ag-header-background-color: #0f0722;
  --ag-row-hover-color: #21173f;
  --ag-border-color: #2b1a4d;
  --ag-header-foreground-color: var(--ink-2);
  --ag-foreground-color: var(--ink);
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
.ag-row.hub-row-focus { position: absolute; }
.ag-row.hub-row-focus::after {
  content: "";
  position: absolute; inset: 0;
  pointer-events: none;
  z-index: 2;
  box-shadow: inset 0 2px 0 var(--accent), inset 0 -2px 0 var(--accent);
}
/* Only the outer edges, or the verticals show where the fragments meet. The right one
   is off screen when the columns are wider than the window - the row does continue. */
.ag-pinned-left-cols-container .ag-row.hub-row-focus::after {
  box-shadow: inset 0 2px 0 var(--accent), inset 0 -2px 0 var(--accent),
              inset 2px 0 0 var(--accent);
}
.ag-center-cols-container .ag-row.hub-row-focus::after {
  box-shadow: inset 0 2px 0 var(--accent), inset 0 -2px 0 var(--accent),
              inset -2px 0 0 var(--accent);
}
/* If a column is ever pinned right, that fragment owns the right edge instead. */
.ag-pinned-right-cols-container .ag-row.hub-row-focus::after {
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
  background: #1a0f35 !important;
  border: 1px solid #3d2461;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(180, 41, 249, 0.2);
  min-width: 168px;
}
.q-menu .q-item {
  min-height: 30px;
  padding: 4px 12px;
  font-size: var(--fs-body);
  color: var(--ink);
}
.q-menu .q-item:hover { background: #2a1a4a; }
.q-menu .q-separator { background: #3d2461; margin: 2px 0; }
/* A picker over the whole library. Unconstrained, its menu is as wide as the longest
   title in it - which in a library with one 130-character name is the whole window -
   and it resizes and repositions itself as typing filters the list. Bounded here, so
   it opens the same size every time and stays under the field it belongs to. */
.hub-picker-popup {
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
.hub-collection-icon {
  width: 64px; height: 64px;
  object-fit: contain;
  border: 1px solid #2b1a4d;
  border-radius: 8px;
  background: var(--panel-ground);
}
.hub-upload .q-uploader { background: none; border: 1px dashed #3d2461; }

/* The rule, said in words above the controls that set it. Roomier than help text
   because it is the sentence somebody reads to check the rule says what they meant. */
.hub-rule-sentence {
  color: var(--ink-2);
  font-size: var(--fs-body);
  max-width: none;
}

/* Why a row is in the collection. Quiet where the answer is ordinary, amber where it
   is something to go and fix - the same reading the rest of the app gives the colour. */
.hub-member-chip {
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
.hub-chip-quiet { color: var(--ink-3); border: 1px solid #241640; }
.hub-chip-warn { color: #f0b849; border: 1px solid #6b4a12; }

/* The collection's icon in a media slot's art region. Contained, so a wide banner and a
   square logo both sit in the same box. */
.hub-slot-image { max-width: 100%; max-height: 100%; object-fit: contain; }

/* A collection's picture in the list. Small and contained: it identifies a row, it is
   not the row. */
.hub-collection-cell {
  height: 30px; max-width: 44px;
  object-fit: contain;
  display: block;
  margin: 3px auto;
}

/* Dynamic or Manual, the one control that converts between them. */
.hub-kind-toggle { flex: none; }

/* The grip on an arrangeable row. `grab` rather than `move`, because the row is being
   picked up rather than pushed around, and `touch-action: none` or the browser scrolls
   the panel instead of letting the pointer handler have the drag. */
.hub-drag-handle {
  cursor: grab;
  touch-action: none;
  font-size: 18px;
  color: var(--ink-3);
  flex: none;
}
.hub-drag-handle:hover { color: var(--accent); }
/* Lifted, not swapped: the row leaves the flow and follows the pointer while the rest
   of the list holds still. Swapping moved the rows you were aiming at, so the target
   changed as you approached it. */
.hub-member-row.hub-dragging {
  position: fixed;
  z-index: 8000;
  background: #2a1a4a;
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.55);
  cursor: grabbing;
  pointer-events: none;
}
/* Where it would land. A band rather than an empty gap: the gap alone reads as the
   list having lost a row. */
.hub-drop-slot {
  border-radius: 6px;
  border: 1px dashed var(--accent);
  background: rgba(0, 217, 255, 0.06);
}
/* The keyboard's equivalent of being lifted. */
.hub-member-row.hub-grabbed {
  background: #2a1a4a;
  outline: 1px solid var(--accent);
  border-radius: 6px;
}
.hub-drag-handle:focus-visible {
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
.hub-member-row {
  padding: 5px 10px;
  border-radius: 6px;
  line-height: 1.25;
}
/* The row the panel beside this is about. Weight, not colour: accent is the chosen one
   and the default mark already spends it on this list, so a second accent here would
   have two meanings in one row. */
.hub-member-name--here { color: var(--ink); font-weight: 600; }
.hub-member-name { font-size: var(--fs-body); color: var(--ink-2); }
.hub-member-table {
  font-size: var(--fs-caption);
  color: var(--ink-3);
  line-height: 1.2;
  /* Not `.hub-help`, whose 62ch cap and looser leading are for prose. This is a
     label under another label. */
  padding-left: 1px;
}

/* Which of the two this table is, said beside the table it qualifies rather than in the
   chip slot at the row's edge - that slot is for what has happened to the row. Dimmer
   than the identity it follows, so a scan reads the names and not the qualifier. */
.hub-member-qualifier {
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
.hub-mark {
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
.hub-mark--full { background: currentColor; }
/* The base circle, named so a caller can say which end of the ramp it means rather
   than passing an empty string and hoping. */
.hub-mark--outline { background: transparent; }
/* Half filled, and the fill runs to the circle's own centre rather than to the edge of
   its outline. */
.hub-mark--half {
  background: linear-gradient(to right, currentColor 50%, transparent 50%);
}
/* Drawn rather than bordered. `border-style: dashed` picks its own dash length from the
   border width, which on a 34px circumference put three chunky dashes on the circle -
   the same declaration that reads as a proper dashed edge on a tile, because a tile has
   the perimeter for it. The gradient is an exact eight, at any size. */
.hub-mark--dashed {
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
.hub-tier-key .hub-mark { margin-right: 3px; }
/* A state drawn as nothing still needs its place in the legend, or the reader is left
   matching three words against two marks. It holds a mark's width and stays empty. */
.hub-mark-none { display: inline-block; width: 11px; margin-right: 3px; }

/* Five stars that are also the control. Sized to the row rather than to a dialog: this
   is the compact form of the same five, and a star big enough to admire is a column
   wide enough to hurt. */
.hub-stars-cell { padding-left: 10px !important; }
.hub-stars { display: inline-flex; gap: 2px; line-height: 0; }
.hub-star {
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
.hub-star--on { background: var(--accent); opacity: 1; }
.ag-row:hover .hub-star { opacity: 0.6; }
.ag-row:hover .hub-star--on { opacity: 1; }
.hub-star:hover { opacity: 1; background: var(--accent); }
/* The way back to unrated. Beside the stars rather than in them, because it is not a
   sixth degree of the same scale - and only on a row the pointer is over, so a rated
   library does not read as a column of dismissals. */
.hub-star-clear {
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
  .hub-star-clear { opacity: 0; }
  .hub-stars:hover .hub-star-clear { opacity: 0.75; }
}
.hub-stars:focus-within .hub-star-clear { opacity: 1; }
.hub-star-clear:hover { opacity: 1; color: var(--ink-1); }
/* In the filter, the stars are a picture of a value and not a control. */
.hub-filter-row .hub-star { cursor: pointer; margin-right: -1px; }

/* One confirmation, wherever something cannot be undone. Narrow enough to read in one
   line of sight, and the named files are quiet and breakable - a path is looked at, not
   read. */
.hub-confirm { min-width: 320px; max-width: 460px; }
/* A picker is a list to read down, not a question to answer, so it takes the room a
   list needs and caps its height rather than growing past the window. */
.hub-picker-dialog { min-width: 520px; max-width: 640px; }
.hub-picker-dialog .hub-source-list { max-height: 42vh; overflow-y: auto; }
/* The question is a sentence and takes sentence case. It used to wear `.hub-card-title`,
   which is the section-heading treatment - uppercase, tracked, accent - so every dialog
   opened by shouting its question. Weight and size carry it instead. */
.hub-confirm-title {
  font-size: var(--fs-body);
  font-weight: 600;
  color: var(--ink);
  line-height: 1.35;
}
.hub-confirm-line {
  font-size: var(--fs-caption);
  color: var(--ink-3);
  word-break: break-all;
}

/* The state picker inside a column's filter. The same words and marks as the legend,
   because a filter that named the states differently would be a third vocabulary. */
.hub-filter { padding: 6px 4px; min-width: 148px; }
.hub-filter-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 8px;
  border-radius: 4px;
  cursor: pointer;
  color: var(--ink-1);
  font-size: 13px;
  white-space: nowrap;
}
.hub-filter-row:hover { background: rgba(255, 255, 255, 0.06); }
/* The leading slot, wide enough for a mark and present whether or not there is one -
   a choice that draws nothing in the grid indents to here rather than shifting its
   label left of every other. A rating draws five, so it grows rather than clipping. */
.hub-filter-mark {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-width: 11px;
  flex: none;
}
.hub-filter-row input { accent-color: var(--accent); cursor: pointer; margin: 0; }

/* A media cell holds one thing - a mark or a picture - so it centres that thing rather
   than leaving it on the text baseline. A picture on the baseline sat 1px below the top
   of a 60px row and 7px above the bottom. */
.ag-cell.hub-media-cell {
  display: flex;
  align-items: center;
  justify-content: center;
}
/* AG Grid wraps a renderer's HTML in a bare <span> of its own, and that span - not the
   art - is what the cell centres. On a line box sized for the row it stood 76px tall in
   a 59px cell, so centring hung the picture 8px above the cell and the clip took the top
   off the enlarge. Zero line height makes it the height of what it holds. */
.hub-media-cell > * {
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
}
/* The art and the control that enlarges it. Relative on the art rather than the cell,
   so the button sits on the picture's own corner - on the cell's it floats out over
   the whitespace beside a narrow one. */
.hub-cell-art { position: relative; display: inline-flex; line-height: 0; }
.hub-cell-zoom {
  position: absolute;
  top: 2px;
  right: 2px;
  font-size: 14px;
  padding: 2px;
  border-radius: 4px;
  color: var(--ink-1);
  background: rgba(10, 5, 24, 0.72);
  cursor: pointer;
  /* Hidden until the row is under the cursor: twenty of these showing at once is a
     column of buttons, and the pictures are what the row is for. */
  opacity: 0;
  transition: opacity 90ms ease-out;
}
.ag-row:hover .hub-cell-zoom { opacity: 0.75; }
.hub-cell-zoom:hover { opacity: 1; background: rgba(10, 5, 24, 0.9); }

.hub-mark--set {
  border-radius: 0;
  background: currentColor;
  transform: rotate(45deg) scale(0.82);
}

.hub-member-mark {
  /* Big enough that ● and ◐ are told apart. They differ by half a fill, which at 11px
     is two or three pixels - measured on screen, both read as the same dot. */
  font-size: 15px;
  line-height: 1;
  color: var(--ink-2);
  flex: none;
  width: 16px;
  text-align: center;
}
.hub-member-row:hover .hub-member-mark { color: var(--accent); }

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
.hub-member-table-line {
  border-radius: 4px;
  padding-right: 2px;
  margin-top: 1px;
  color: var(--ink-3);
}
.hub-member-row:hover .hub-member-table-line .hub-mark { color: var(--accent); }
.hub-member-table-line:hover { background: rgba(255, 255, 255, 0.06); }
.hub-member-table-caret {
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
  .hub-member-table-caret { opacity: 0; transition: opacity 120ms ease; }
  .hub-member-row:hover .hub-member-table-caret,
  .hub-member-table-line:focus-within .hub-member-table-caret { opacity: 1; }
}
/* Wraps rather than truncates: in the menu the whole point is telling two builds of
   one game apart, and that is exactly what a cut-off tail hides. */
/* Wraps rather than truncates: in this menu the whole point is telling two builds of
   one game apart, and that is exactly what a cut-off tail hides. The uppercase opt-out
   this used to carry is gone - no menu item is uppercase now. */
.q-menu .hub-menu-item .hub-menu-table-name {
  max-width: 30ch;
  white-space: normal;
}
.hub-menu-check { font-size: 16px; color: var(--accent); }
/* What Game Default resolves to today, under the words that name it. A step down in
   size and colour, the same way a member row's table line sits under its game. */
.q-menu .hub-menu-item .hub-menu-sub {
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
.q-menu .hub-menu-item.hub-menu-blocked,
.q-menu .hub-menu-item.hub-menu-blocked .q-item__label,
.q-menu .hub-menu-item.hub-menu-blocked:hover,
.q-menu .hub-menu-item.hub-menu-blocked:hover .q-item__label {
  color: var(--ink-3);
  opacity: 0.55;
  cursor: default;
  background: transparent;
}
.hub-menu-blocked-mark { color: var(--ink-3) !important; font-size: 15px; }
/* Which of a game's tables it offers. A radio rather than a glyph: a game has exactly
   one default, that is what a radio means, and it reads as a control - which this one
   is. Kept clear of the text glyphs in `game_tables.py`, whose question is a different
   one, by being an icon and by living on a surface those never appear on. */
.hub-default-mark {
  font-size: 18px;
  color: var(--ink-3);
  flex: none;
  transition: color 120ms ease;
}
.hub-default-mark--on { color: var(--accent); }
.hub-default-mark.cursor-pointer:hover { color: var(--ink); }

/* A tooltip belonging to the control that opened a menu would sit on top of it. */
body.hub-menu-open .q-tooltip { display: none !important; }

/* The key for those marks, in the header that does not scroll. */
.hub-member-key {
  font-size: var(--fs-caption);
  color: var(--ink-2);
  white-space: nowrap;
  flex: none;
}

/* Alternating ground. Rows are two lines tall here, so where one ends is not obvious
   from spacing alone - which is exactly when striping earns its keep. Kept very low
   contrast: it separates, it does not decorate. */
.hub-member-row:nth-child(even) { background: rgba(255, 255, 255, 0.055); }
.hub-member-row:hover { background: #23143f; }

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
.hub-row-action {
  transition: opacity 120ms ease;
  display: flex; align-items: center; flex: 0 0 auto;
}
@media (hover: hover) and (pointer: fine) {
  .hub-row-action { opacity: 0; }
  .hub-member-row:hover .hub-row-action,
  .hub-member-row:focus-within .hub-row-action { opacity: 1; }
  .hub-member-row[data-origin="missing"] .hub-row-action,
  .hub-member-row[data-origin="excluded"] .hub-row-action { opacity: 1; }
}

.hub-picker-popup .q-item__label {
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

/* The same treatment as `.hub-group`, which is what the rest of the app uses to name a
   group. Quiet, small, tracked - a signpost recedes. */
.hub-menu-header {
  color: var(--ink-3) !important;
  font-size: var(--fs-caption);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  min-height: 24px !important;
  padding: 8px 12px 2px !important;
}
/* Body voice. You read an item and click it; sentence case is how a name stays a name,
   which is what a menu over a library is full of. */
.q-menu .hub-menu-item,
.q-menu .hub-menu-item .q-item__label {
  color: var(--ink-2);
  font-size: var(--fs-caption);
  text-transform: none;
  letter-spacing: normal;
}
/* Every item spans the menu. NiceGUI's column carries `items-start`, so an item in one
   sized to its own text and the hover band stopped where the words did - measured at
   121px inside a 247px menu. The band *is* the affordance; a colour change alone is
   too weak to say "this row is the target". */
.q-menu .hub-menu-item {
  width: 100%;
  min-height: 30px;
  border-radius: 0;
}
.q-menu .hub-menu-item:hover,
.q-menu .hub-menu-item:focus-visible {
  background: #2a1a4a;
}
.q-menu .hub-menu-item:hover,
.q-menu .hub-menu-item:hover .q-item__label,
.q-menu .hub-menu-item:focus-visible,
.q-menu .hub-menu-item:focus-visible .q-item__label { color: var(--ink); }

/* Cyan is the current value and nothing else. Everything being accent-coloured is what
   left it meaning nothing. */
.q-menu .hub-menu-item.hub-menu-on,
.q-menu .hub-menu-item.hub-menu-on .q-item__label { color: var(--accent); }

/* One leading column, 16px, whatever fills it - mark, icon or nothing. Items with no
   mark still indent to it, so the labels line up down the menu. */
.hub-menu-mark, .hub-menu-add {
  flex: none;
  width: 16px;
  font-size: 16px;
  line-height: 1;
  text-align: center;
  color: var(--ink-3);
}
/* A drawn mark keeps its own diameter and is centred in that column rather than
   stretched across it - the column's 16px made an 11px circle into an oval. */
.q-menu .hub-menu-mark.hub-mark { width: 11px; margin: 0 2.5px; }
.q-menu .hub-menu-item:hover .hub-menu-mark,
.q-menu .hub-menu-item:hover .hub-menu-add { color: var(--ink); }
.q-menu .hub-menu-item.hub-menu-on .hub-menu-mark { color: var(--accent); }

/* The act, not the row, is what is destructive: the text carries it and the hover band
   stays the ordinary one. A red row reads as an error that has already happened. */
.q-menu .hub-menu-item.hub-menu-danger,
.q-menu .hub-menu-item.hub-menu-danger .q-item__label { color: var(--warn); }
.q-menu .hub-menu-item.hub-menu-danger:hover,
.q-menu .hub-menu-item.hub-menu-danger:hover .q-item__label { color: #ff9d6b; }

/* A checkbox item is an item: same band, same height, same leading column - the box
   is what fills the mark slot. */
.q-menu .q-checkbox.hub-menu-item {
  display: flex;
  padding: 2px 12px;
  min-height: 30px;
}

/* Between groups, never as decoration. */
.q-menu .q-separator { margin: 4px 0; opacity: 0.5; }

/* Tiles are deliberately plain: the art is the content, so the chrome around it stays
   quiet enough that an outlier stands out rather than the frame. */
.hub-tile { cursor: pointer; padding: 4px; border-radius: 8px; }
.hub-tile:hover { background: #2a1a4a; }
.hub-tile-art {
  width: 100%;
  object-fit: contain;
  border-radius: 6px;
  background: #140a2b;
  border: 1px solid #2b1a4d;
}
.hub-tile-missing { border-style: dashed; }
.hub-tile-label {
  font-size: var(--fs-caption);
  color: var(--accent);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-top: 2px;
}

.hub-panel {
  background: #1a0f35;
  border: 1px solid #3d2461;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(180, 41, 249, 0.2);
}
.hub-label { color: var(--accent); letter-spacing: 0.04em; }

/* Nav in the 2.x idiom: a vertical gradient off the brand purple into the page black,
   caps with tracking, and cyan for the title. The gradient runs dark enough by the foot
   that the version row still reads. */
.q-drawer--left {
  /* 2.x's --header-gradient stops, but the bright band is compressed into the header
     row rather than spread down the rail. The title is near-white with a glow and
     carries purple fine; the items are #5898d4 and do not, so the ground under them
     has to be dark. 90px is just past the 59px header. */
  background: linear-gradient(180deg, #b429f9 0px, #4a1e7c 60px, #1a0f35 90px,
                              #0f0722 100%) !important;
}
.hub-nav-item {
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
.q-drawer--left .cursor-pointer:hover .hub-nav-item { color: var(--ink); }
.q-drawer--left .cursor-pointer:hover .q-icon { color: var(--ink); opacity: 1; }
.q-drawer--left .q-icon { color: var(--ink-2); }

/* The row itself, also sampled: 48px tall on a 12px/16px pad with a 12px radius, so a
   highlighted row reads as a rounded block inset from the panel edge. */
/* Geometry only. The surface and border here came from matching the "Navigation"
   label's row, which was the wrong element - the title it now matches sits in 2.x's
   header bar with nothing drawn behind it. */
.hub-nav-header {
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
.q-drawer--mini .hub-nav-row,
.q-drawer--mini .hub-nav-header {
  padding-left: 0 !important;
  padding-right: 0 !important;
  margin-left: 0;
  margin-right: 0;
  max-width: 100%;
  justify-content: center;
}

.hub-nav-row {
  min-height: 48px;
  padding: 12px 16px !important;
  border-radius: 12px;
  margin: 2px 8px;
  /* w-full plus a horizontal margin overhangs on the right, which put the highlight
     off-center. 2.x's .nav-btn solves it the same way. */
  max-width: calc(100% - 16px);
}
/* The page you are on stays lit while you are on it - --surface-2 behind it and
   --glow-purple around it, which is what 2.x does. */
.hub-nav-active {
  background: #251447;
  box-shadow: 0 0 4px rgba(180, 41, 249, 0.5), 0 0 8px rgba(180, 41, 249, 0.3);
}

/* One accent, not three. Purple is surface - gradients, borders, the grid header - and
   cyan is the only thing that accents. Pink was a third hue close enough to the header
   magenta to muddle rather than contrast; the panels are told apart by tone instead,
   the nav title at full neon and this one near-white with a softer halo. */
.hub-workbench {
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
.hub-rail .hub-workbench {
  background: linear-gradient(180deg, #4a1e7c 0px, #2a1a52 44px,
                              var(--panel-ground) 72px) !important;
}
/* truncate only ellipsizes against a definite width. The column may shrink under
   min-w-0, but its labels have to be told to take that width or they overflow and get
   cropped by the parent instead of ellipsized. */
.hub-panel-header .hub-workbench-title,
.hub-panel-header .hub-workbench-label { max-width: 100%; }

.hub-workbench-title {
  color: var(--ink);
  text-shadow: 0 0 6px rgba(0, 217, 255, 0.45);
}
.hub-workbench-label {
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: var(--fs-caption);
}
/* Tight: this panel carries a lot and the default expansion chrome is mostly air. */
.hub-workbench .q-expansion-item {
  border: 1px solid #2b1a4d;
  border-radius: 8px;
  /* Vertical margin only. A horizontal margin on a w-full child overhangs by exactly
     its own width, which is where the workbench's 6px of horizontal scroll came from; the
     inset belongs on the container. */
  margin: 4px 0;
  background: rgba(26, 15, 53, 0.55);
}
.hub-workbench { overflow-x: hidden !important; }
/* No side gutter of its own: what it holds carries the shared one, and two would
   stack. Top and bottom are the exception - the section row sits directly above and
   the section's own edge directly below, and without this the content is flush to
   both and reads as cut off at each end. */
.hub-workbench-body { padding: 8px 0; }
.hub-workbench .q-expansion-item .q-item {
  min-height: 32px;
  padding: 2px 10px;
}
.hub-workbench .q-expansion-item .q-item__label {
  color: var(--accent); font-size: var(--fs-caption);
}
.hub-workbench .q-expansion-item__content { padding: 2px 0 6px; }
/* nicegui puts a 16px flex gap on .nicegui-expansion-content, which double-spaced every
   line inside a section: 22px rows on a 38px pitch. Same default as the drawer's, in a
   different container - the rows carry their own spacing. */
.hub-workbench .nicegui-expansion-content {
  /* Both of nicegui's defaults on this container: the 16px gap double-spaced the lines
     and the 16px padding is the dead space above the first field and below the last. */
  gap: 0 !important;
  padding: 0 !important;
}
/* The panel toggles match: nav and workbench are the same control, same color. */
.hub-panel-header .q-icon { color: var(--ink-2); }
.hub-workbench .q-expansion-item__content .row { min-height: 22px; }
.hub-nav-title {
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
  border: 1px solid #3d2461;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(180, 41, 249, 0.2);
}
.ag-header {
  /* 2.x's --header-gradient in full - I had been running it to #4a1e7c and stopping,
     which lost the fade to near-black at the far end. */
  background: linear-gradient(135deg, #b429f9 0%, #4a1e7c 50%, #0a0518 100%) !important;
  border-bottom: 1px solid #3d2461 !important;
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
.hub-mediatile {
  flex: 1 1 0;
  min-width: 0;
  /* A column, so the caption sits at the foot of whatever height the row settles on
     rather than at the foot of its own art. */
  display: flex;
  flex-direction: column;
  border: 1px solid #2b1a4d;
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
.hub-mediatile--present { border-color: var(--line); }
.hub-mediatile--borrowed { border-color: rgba(255, 176, 32, 0.65); }
.hub-mediatile--missing { border-style: dashed; opacity: 0.55; }
.hub-mediatile--on {
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
.q-btn--flat.text-negative, .q-btn--flat.text-negative .q-icon { color: #ff6b9d; }

/* An action has to look like one, and color alone never says so - it is silent to
   anyone who cannot see the hue. The border is the affordance; hover fills it. */
.hub-action.q-btn {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 3px 10px !important;
  background: rgba(255, 255, 255, 0.02);
}
.hub-action.q-btn:hover {
  border-color: var(--accent);
  background: rgba(0, 217, 255, 0.10);
}
/* The same control at the chip's scale, for an action that sits beside a state rather
   than after a field. The edge stays - without one it reads as a second value, and this
   panel is worked in rather than read - but the type comes down: measured beside a chip
   at 11px/400 the panel button sat at 12px/500 and was the louder half of the pair. */
.hub-action--inline.q-btn {
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
.hub-action--inline .q-btn__content {
  font-size: var(--fs-caption) !important;
  /* A verb never wraps. The value column is 177px, and "Choose this one" broke across
     three lines and took the row to 49px in a 26px rhythm. */
  flex-wrap: nowrap;
  white-space: nowrap;
}

/* A destructive action is still an action - it takes the same shape and says what it
   is with color on top, not instead. */
.hub-action.hub-action--danger.q-btn { border-color: rgba(255, 107, 157, 0.45); }
.hub-action.hub-action--danger.q-btn:hover {
  border-color: #ff6b9d; background: rgba(255, 107, 157, 0.12);
}

/* `size=sm` writes an inline font-size, which no selector outranks. */
.q-btn--dense .q-btn__content { font-size: var(--fs-caption) !important; }
.q-btn--dense { font-size: var(--fs-caption) !important; }

/* Every control clears the pointer floor - what is fine for a mouse is mean on a
   trackpad. Dense rather than flat, because the toolbar tabs are `unelevated`. */
.q-btn--dense, .hub-section-row {
  min-height: var(--target-min);
}
.hub-mediatile-art {
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
.hub-mediatile-art > div { display: contents; }
.hub-mediatile-art img, .hub-mediatile-art video {
  width: 100%; height: 100%; object-fit: contain;
}
/* On hover and over the art: the tile has no room for a control wanted occasionally.
   Touch has no hover, and reaches this through the slot's own Enlarge. */
.hub-mediatile-art { position: relative; }
/* An empty slot the catalog can fill. Quiet: it is information, not a warning - a
   library is allowed to be missing a topper, and amber here would shout on every
   second tile. */
.hub-mediatile-offered { color: var(--ink-3); opacity: 0.7; }
.hub-mediatile:hover .hub-mediatile-offered { opacity: 1; color: var(--accent); }
.hub-mediatile-zoom {
  position: absolute; top: 2px; right: 2px; opacity: 0;
  background: rgba(10, 5, 24, 0.7) !important; transition: opacity 120ms ease;
}
.hub-mediatile:hover .hub-mediatile-zoom { opacity: 1; }

/* A panel over the page, sized by its content, so the media decides how big it is. */
.hub-viewer-card {
  background: #0b0520 !important;
  max-width: 92vw; max-height: 88vh;
  display: flex; flex-direction: column;
  padding: 0 !important; overflow: hidden;
  border: 1px solid #2b1a4d; border-radius: 10px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}
.hub-viewer-bar {
  flex: 0 0 auto; padding: 8px 12px;
  background: rgba(11, 5, 32, 0.9); border-bottom: 1px solid #2b1a4d;
}
/* Darker than Quasar's default: the art being judged is often bright. */
.q-dialog__backdrop { background: rgba(4, 2, 12, 0.78) !important; }
/* The video's transport, in the bar so it stays upright while the picture turns. */
.hub-viewer-transport { display: flex; align-items: center; gap: 10px; width: 100%; }
.hub-viewer-btn {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 50%; cursor: pointer;
  background: transparent; border: none; color: var(--ink-2);
}
.hub-viewer-btn:hover { background: rgba(180, 41, 249, 0.18); color: var(--ink); }
.hub-viewer-btn .material-icons { font-size: var(--fs-title); }
.hub-viewer-seek { flex: 1 1 auto; min-width: 0; accent-color: var(--accent); cursor: pointer; }
.hub-viewer-clock {
  font-size: var(--fs-caption); color: var(--ink-2); white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

/* The stage owns the wheel and the drag, so a pinch magnifies the art rather than
   asking the browser to zoom a page that has nothing to scroll. */
.hub-viewer-stage {
  overscroll-behavior: contain; touch-action: none;
  user-select: none; -webkit-user-select: none;
}
.hub-viewer-stage img, .hub-viewer-stage video {
  -webkit-user-drag: none; user-select: none;
}

.hub-viewer-stage {
  /* Sized by the media. A rotated element reports its untransformed box, and the turn
     is about its own center, so that box is the right thing to center on. */
  flex: 1 1 auto; min-height: 0;
  display: flex; align-items: center; justify-content: center; overflow: hidden;
}
.hub-mediatile-cap {
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
.hub-mediatile-rule {
  height: 1px; width: 100%; margin: 8px 0 5px; background: #1f1338;
}
.hub-mediatile-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  width: 100%;
}

/* --- section chrome -------------------------------------------------------------- */
.hub-crumb { color: var(--ink-2); font-size: var(--fs-body); }
.hub-crumb b { color: var(--ink); font-weight: 600; }
.hub-card {
  border: 1px solid #2b1a4d;
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(26,15,53,0.75) 0%, rgba(15,7,34,0.75) 100%);
  padding: 14px 16px;
}
.hub-card-title {
  font-size: var(--fs-caption);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
}
.hub-kpi { font-size: var(--fs-display); font-weight: 700; color: var(--ink); line-height: 1.1; }
/* The explanation under a control, not a tooltip on it. This is the whole legibility
   argument for the settings pages, so it gets a class rather than ad-hoc utilities. */
.hub-help { font-size: var(--fs-caption); color: var(--ink-3); line-height: 1.4; max-width: 62ch; }
.hub-setting { font-size: var(--fs-body); color: var(--ink); font-weight: 600; }
.hub-group {
  font-size: var(--fs-caption);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  padding: 10px 8px 4px;
}
/* The outline: a table of contents down the side of the workbench. Quiet, because
   what it points at is the content - an open section is lit and the rest recede. */
/* The lens: which build the sections under it answer for. Pills rather than a
   dropdown so the choice and the alternatives are both visible, truncated because a
   .vpx name runs long and the whole one is a hover away. */
/* In the panel header now, so it wraps to the width it is given rather than to the
   section it used to sit in. */
/* The file, under the game it belongs to. Cut from the front for the same reason the
   picker was: what tells two tables of one game apart is at the end. */
.hub-workbench-table {
  font-size: var(--fs-caption); color: var(--tier-table);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;
}
/* Body and dock, and one rule for where the dock goes. Under the body it is a
   vertical split - the map scrolls, the controls do not, and picking a tile can never
   put them somewhere you have to go looking. Past the work width they sit side by
   side instead, which is what the room is for. */
.hub-section-work { display: grid; grid-template-columns: minmax(0, 1fr); min-height: 0; }
.hub-has-dock {
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
  .hub-has-dock {
    /* `auto` so the track follows the dock's own width. */
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-rows: minmax(0, 1fr);
    grid-template-areas: none;
  }
  /* Half the workbench, so a wide window has no dead middle. The floor keeps it
     usable where half is not much. */
  .hub-dock { width: max(320px, 50cqw); }
}
/* The handle between browse and work. Only where they are stacked - side by side the
   split is the panel's own width, which the outer splitter already owns. */
/* A short centered handle, not a full-width rule. It used to draw a hairline right
   across the panel, which is the same picture the section separators draw - so the
   panel had three horizontal lines of the same weight meaning two different things,
   and the band below the open section read as belonging to whatever was above it.
   A stub you could put two fingers on says "drag me" and says nothing else. */
.hub-dock-grip {
  height: 19px; cursor: row-resize; flex: 0 0 auto;
  display: flex; align-items: center; justify-content: center;
}
.hub-dock-grip::before {
  content: ""; width: 44px; height: 4px; border-radius: 2px;
  background: var(--resize-line);
}
.hub-dock-grip:hover::before { background: var(--accent); }
/* The work region keeps its room whether or not anything is in it: collapsing it
   reflows browse under the cursor that just picked something. */
/* Centered in the reserved room: text in the top corner reads as a mistake. */
.hub-dock-empty {
  margin: auto; text-align: center; padding: 16px; max-width: 34ch;
}
.hub-dock-empty-title { font-size: var(--fs-body); color: var(--ink-2); }
.hub-dock {
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
  .hub-dock { border-top: none; border-left: 1px solid #2b1a4d; }
  /* Below the grip's own rules on purpose: same specificity, so source order decides.
     Above them this loses to the `display` they set, and the handle shows up floating
     at the top of a layout where the dock is beside the map and there is nothing to
     drag. */
  .hub-dock-grip { display: none; }
}

/* Takes the panel. A 420px cap used to stop four fields stretching across a window,
   but these are facts before they are fields, and it cropped a hash at 420px with the
   rest of a 1100px panel left blank - which reads as broken, not as restraint. The
   width still bounds it, so a long filename ellipsizes inside the panel rather than
   running off it; there is simply more panel to use first. A cap belongs on an input,
   where a 900px text box is genuinely useless, not on the text. */
.hub-form { width: 100%; }

/* The facts a section is *for*, so they read at body size like everything else. They
   used to be captions - 12px label and 12px value, smaller than the section heading
   above them, which ranked the content below its own title. */
.hub-facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  /* One box per row, whatever the value is, so nothing grows when a field or a chip
     lands in a row that had text. `auto` above the floor is for content that wraps -
     a line of chips takes two rows' worth and keeps its label centred on them. */
  grid-auto-rows: minmax(var(--fact-row), auto);
  align-items: center;
  column-gap: 8px;
  width: 100%;
  padding: 0 12px;
}
/* Dimmed, not also shrunk. Two levers were doing one job and contrast is the one that
   costs readability; --ink-2 is the documented secondary at 11.1:1. */
.hub-fact-label { font-size: var(--fs-caption); color: var(--ink-2); }
.hub-fact-value { font-size: var(--fs-body); color: var(--ink); }
/* One line of chips sits on the same pitch as every other row, and a wrapped one grows
   symmetrically around its label. The row carries the height rather than the label
   carrying a nudge: two hand-tuned paddings here put this row 28px into a 26px rhythm
   and moved the label whenever the chips wrapped. */
.hub-chips {
  display: flex; flex-wrap: wrap; gap: 4px; min-width: 0;
  min-height: var(--fact-row);
  align-content: center;
  /* Room above and below, or a wrapped block runs into the rows either side of it -
     the 26px pitch is a text row's, and this one is several. */
  padding: 5px 0;
}

/* A value the user may set. The read state and the edit state are one element, so the
   alignment cannot drift and nothing moves on the first click. */
.hub-fact-edit { display: flex; align-items: center; gap: 8px; min-width: 0; }
/* An action follows the value it acts on. It used to be pushed to the panel's right
   edge for a column of verbs, which assumed the value fills the row: a stretching field
   ends near that edge, but a chip is 60px wide and the verb landed a panel-width away
   from the state it changes - further the wider the pane was dragged. Fields still line
   up under this, because they stretch to the same width. */
.hub-edit-field { flex: 1 1 auto; min-width: 0; }
/* The same edge as an action, because it is the same kind of thing: something you can
   act on. A single bottom rule was meant to be the quiet version of this and read as a
   section divider instead - full width, between two rows, which is what a divider is. */
.hub-edit-field .q-field__control {
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
.hub-edit-field .q-field__control::before,
.hub-edit-field .q-field__control::after { border: none; }
.hub-edit-field:hover .q-field__control {
  border-color: var(--accent);
  background: rgba(0, 217, 255, 0.06);
}
.hub-edit-field .q-field--focused .q-field__control {
  border-color: var(--accent);
  background: rgba(0, 217, 255, 0.10);
}
.hub-edit-field .q-field__native {
  font-size: var(--fs-body); color: var(--ink); padding: 0;
}
/* The way back, and the only mark an overridden row carries. Amber because that is
   already this app's word for the exception worth spotting, so one mark says both what
   the state is and what to do about it. */
.hub-revert {
  color: var(--tier-table); font-size: 16px; cursor: pointer; flex: 0 0 auto;
  opacity: 0.8;
}
.hub-revert:hover { opacity: 1; }
/* The one control for a yes or no. Its own height, which the row takes - a switch is
   a control, and text rows are what the 26px pitch is for. */
.hub-fact-switch .q-toggle__inner { font-size: 28px; }
.hub-fact-switch.disabled { opacity: 0.65 !important; }

/* A group's name, spanning the grid so every group keeps the one shared label column.

   The rule and the space carry the break. The weight is what puts a group title above
   the labels it governs, and uppercase with tracking is what tells it from one. */
.hub-fact-heading {
  grid-column: 1 / -1;
  /* .hub-card-title's treatment: a heading inside a panel is cyan and uppercase
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
.hub-facts > .hub-fact-heading:first-child {
  border-top: none; margin-top: 0; padding-top: 0;
}
/* Actions and the attention block: the width of the panel, not of a value. */
.hub-fact-full { grid-column: 1 / -1; padding: 4px 0; min-width: 0; }

/* What is wrong with this thing, before anything merely true about it. Amber, which is
   already the exception color here - not red: none of these is an error, they are
   things to go and fix. */
.hub-attention {
  display: flex; align-items: flex-start; gap: 8px; min-width: 0;
  border: 1px solid rgba(255, 192, 97, 0.35);
  background: rgba(255, 192, 97, 0.07);
  border-radius: 6px; padding: 6px 10px;
}
.hub-attention-icon { color: var(--tier-table); font-size: 18px; flex: 0 0 auto; }
.hub-attention-line { font-size: var(--fs-body); color: var(--ink); }
/* One detail against its replacement. The old value is struck rather than merely dim:
   it is not a lesser version of the new one, it is the wrong machine's. */
.hub-diff-field {
  font-size: var(--fs-caption); color: var(--ink-3);
  flex: 0 0 auto; min-width: 72px;
}
.hub-diff-was {
  font-size: var(--fs-caption); color: var(--ink-3);
  text-decoration: line-through; flex: 0 1 auto;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.hub-diff-arrow { font-size: 14px; color: var(--ink-3); flex: 0 0 auto; }
/* The picked slot. The art is the subject and takes the room; the facts under it are
   a line each, which is what lets them be sentences rather than a table of fields. */
.hub-slot {
  border: 1px solid #2b1a4d; border-radius: 8px;
  background: linear-gradient(180deg, rgba(26,15,53,0.75) 0%, rgba(15,7,34,0.75) 100%);
  display: flex; flex-direction: column; min-height: 0;
  /* Without this the column is sized by its contents and overhangs the panel, which
     is what put a horizontal scrollbar under a narrow dock. */
  min-width: 0;
}

/* Takes what is left after the text, down to nothing - so in a short dock the art
   shrinks and the sentences stay on screen, rather than the actions going below
   the fold. */
.hub-slot-art {
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
.hub-slot-zoom {
  position: absolute; top: 6px; right: 2px; opacity: 0;
  background: rgba(10, 5, 24, 0.7) !important; transition: opacity 120ms ease;
}
.hub-slot-art:hover .hub-slot-zoom { opacity: 1; }
.hub-slot-art img, .hub-slot-art video {
  max-width: 100%; max-height: 100%; object-fit: contain;
  border-radius: 4px; border: 1px solid #2b1a4d;
}
/* Audio has no frame, so it is the control itself and takes the width it is given
   rather than being sized like a picture. */
.hub-slot-art audio { width: 100%; }

/* An empty slot is still the shape of the thing that goes in it: the outline holds
   the same room the art would, so picking an empty slot does not resize the panel. */
.hub-slot-blank {
  width: 100%; height: 100%; min-height: 90px;
  border: 1px dashed #2b1a4d; border-radius: 6px;
  justify-content: center; color: var(--ink-3);
}
.hub-slot-blank-icon { font-size: 34px; opacity: 0.55; }

.hub-slot-facts { min-width: 0; }
/* The filename is the one identifier a user recognizes, so it reads first and whole -
   these names are long and the interesting half is usually the tail. */
.hub-slot-file {
  font-size: var(--fs-body); color: var(--ink-2); word-break: break-all;
  line-height: 1.35;
}

/* The losers. Set apart by a rule rather than a heading weight, because the point is
   that they are the same slot - not a new section. */
.hub-slot-others {
  border-top: 1px solid var(--line-soft); margin-top: 6px; padding-top: 5px;
  min-width: 0;
}
.hub-slot-others-title {
  font-size: var(--fs-caption); text-transform: uppercase; letter-spacing: 0.07em;
  color: var(--ink-3); padding-bottom: 2px;
}
/* Shrinks but does not grow: given the width of a full-window panel, a growing
   label would put the filename and the phrase that explains it at opposite ends. */
.hub-slot-other-file {
  font-size: var(--fs-caption); color: var(--ink-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
  flex: 0 1 auto;
}

/* Who is not using the file above. Set off the same way the outranked files are,
   because it is the same kind of fact: this slot is not the whole story. */
.hub-slot-differs {
  border-top: 1px solid var(--line-soft); margin-top: 6px; padding-top: 5px;
  min-width: 0;
}

.hub-slot-actions { padding-top: 8px; }

/* Room to judge the art when there is width to spare: at 240px a backglass in a
   half-window panel is a thumbnail beside a lot of nothing, and judging art is what
   this view is for. */
@container (min-width: 900px) {
  .hub-slot-art { min-height: 200px; }
  .hub-slot-art img, .hub-slot-art video { max-height: min(52vh, 520px); }
}

/* --- who owns a file, wherever a file is shown -------------------------- */

.hub-tier {
  font-size: 11px; letter-spacing: 0.04em; line-height: 1.5;
  padding: 0 6px; border-radius: 999px; border: 1px solid transparent;
  white-space: nowrap; flex: 0 0 auto; align-self: center;
}
/* Filled, because this is the exception in a folder and the one worth spotting. */
.hub-tier--table {
  color: var(--tier-table); border-color: rgba(255, 192, 97, 0.45);
  background: rgba(255, 192, 97, 0.12);
}
/* Outlined and quiet: the common case should be readable, not loud. */
.hub-tier--game { color: var(--tier-quiet); border-color: var(--line); }
/* Dashed, because nothing is actually here - something else is filling in. */
.hub-tier--standin {
  color: var(--tier-quiet); border-style: dashed; border-color: var(--line);
}
/* Nothing to own. Shown only where a row has to line up with others that carry one. */
.hub-tier--missing { color: var(--ink-3); border-color: transparent; opacity: 0.5; }

/* Below .hub-tier, not above it. That base sets `border` as a shorthand, so a
   border-color declared earlier is reset to transparent by it - equal
   specificity, and source order decides. */
/* Present, absent, and not yet known. A state chip is not a media tier: those answer
   whose file this is, and their amber is the exception worth spotting. Green is
   present here; amber is reserved for something to go and fix. */
.hub-tier--on {
  color: var(--positive); border-color: rgba(0, 255, 159, 0.45);
  background: rgba(0, 255, 159, 0.12);
}
.hub-tier--off {
  color: var(--ink-2); border-color: rgba(155, 139, 189, 0.55);
  background: rgba(155, 139, 189, 0.10);
}
.hub-tier--unknown {
  color: var(--ink-2); border-style: dashed;
  border-color: rgba(155, 139, 189, 0.55);
  background: rgba(155, 139, 189, 0.06);
}
/* Broken, not merely absent: what this names stops the table working at all. The one
   red on the panel, so it means exactly that and nothing softer. */
.hub-tier--bad {
  color: #ff6b9d; border-color: rgba(255, 107, 157, 0.45);
  background: rgba(255, 107, 157, 0.12);
}
/* Dashed, because the thing it names is not there. */
.hub-tier--warn {
  color: var(--tier-table); border-style: dashed;
  border-color: rgba(255, 192, 97, 0.45);
}

/* On a map tile the badge sits over the art, top left, opposite the enlarge. */
.hub-mediatile-tier {
  position: absolute; top: 3px; left: 3px;
  background: rgba(10, 5, 24, 0.72);
}
.hub-mediatile-tier.hub-tier--table { background: rgba(40, 24, 8, 0.85); }

/* The view has drifted from what it says it is, said on the control that names it.
   Quiet - a modified view is an ordinary thing to be in, not a warning - but it has to
   be visible or the picker is lying. */
.hub-view-picker .q-field__suffix {
  font-size: var(--fs-caption); color: var(--tier-table); opacity: 1;
  padding-left: 6px;
}

/* A tick column is scanned, not read: center it so the eye runs down one line. */
/* Green, not accent. `docs/conventions.md`: green is present, and accent is the current
   value and nothing else - spending it on every true cell in a matrix is how it stops
   meaning anything. `.hub-unknown` is the answer that is neither yes nor no, so it is
   quiet: an unread table is not a fault and must not read as one. */
.hub-tick { text-align: center; color: var(--positive); }
.hub-unknown { text-align: center; color: var(--ink-3); font-weight: 600; }

/* One or more tables here use something else. A bar rather than a badge: the tile is
   about a hundred pixels wide and already carries a tier badge and an enlarge, and a
   third piece of text on it is not read by anybody. The count is in the tooltip and
   the names are in the panel. */
.hub-mediatile-differs {
  position: absolute; left: 0; right: 0; bottom: 0; height: 3px;
  background: var(--tier-table); font-size: 0; overflow: hidden;
}

/* --- where a slot's file can come from ---------------------------------- */

.hub-sources-card {
  width: min(840px, 94vw); max-height: 84vh; gap: 6px;
  background: var(--surface-1); border: 1px solid var(--line);
}
/* A row that navigates rather than acting: the whole thing is the target, so it says
   so on hover instead of hiding a click behind a label. Separate from --folder, which
   is one of these and also a row with no picture in it. */
.hub-source-row--pick { cursor: pointer; }
/* One line: these names carry the maker and year and run long, and four wrapped lines
   of one row makes a list of them unreadable. */
.hub-source-row--pick .hub-source-name {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  word-break: normal; min-width: 0;
}
.hub-source-trail { word-break: break-word; padding-bottom: 2px; }
.hub-source-row--pick:hover {
  border-color: var(--accent); background: rgba(0, 217, 255, 0.06);
}
/* The one decision every way in feeds, so it sits above them rather than inside one.
   Set off by a rule, because it is a different kind of thing from a tab. */
.hub-destination {
  padding: 8px 4px 10px; border-bottom: 1px solid var(--line-soft);
}
.hub-destination-name {
  padding-top: 4px; word-break: break-all; font-family: inherit;
}
/* Stated before the write, not only in the confirm afterwards - but kept quiet,
   because replacing a file is the ordinary case and not a warning. */
.hub-destination-conflict {
  font-size: var(--fs-caption); color: var(--ink-2); padding-top: 2px;
}
/* One name the file could take. The whole row is the target: the mark is small and
   the name is the part being read, so asking for the mark would be a worse target
   than the thing it belongs to. */
.hub-placement { padding: 4px 2px; cursor: pointer; border-radius: 4px; }
.hub-placement:hover { background: rgba(255, 255, 255, 0.04); }
.hub-placement-mark { font-size: 18px; color: var(--ink-3); margin-top: 1px; }
/* Accent, because this is the one chosen - which is what accent is for. */
.hub-placement-mark--on { color: var(--accent); }
/* These are filenames and they run long. Wrapped rather than trimmed: what tells two
   of them apart sits in the middle, so an ellipsis at either end can eat it. */
.hub-placement-name {
  font-size: var(--fs-body); color: var(--ink-2);
  word-break: break-word; line-height: 1.3;
}
/* A second heading in a panel that opened with one needs the air, or the list above
   reads as belonging to it. */
.hub-source-under { padding-top: 10px; }

.hub-sources-panels { min-height: 260px; }
/* Quasar paints its own ground on panels and on the tab bar. Left alone it is a pale
   slab in the middle of a dark dialog. */
.hub-sources-panels, .hub-sources-panels .q-tab-panel,
.hub-sources-card .q-tabs { background: transparent; }
.hub-sources-panels .q-tab-panel { padding: 12px 4px; }
/* Five sources have to fit without a scroll arrow: an arrow on a tab bar means the
   ways of doing this are hidden behind a control nobody looks for. */
.hub-sources-card .q-tab { color: var(--ink-3); padding: 4px 10px; min-width: 0; }
.hub-sources-card .q-tab--active { color: var(--accent); }
.hub-sources-card .q-tab__indicator { background: var(--accent); }
/* Every tab is a list of candidates, and the dialog is capped - so the list scrolls
   inside it rather than the dialog growing past the window. */
.hub-source-list { max-height: 52vh; overflow-y: auto; }
/* The online tab stacks two of these, and they are not equals: the games are how you
   get to the files, and the files are what you came for. Uncapped, a long search
   pushed the files off the bottom of the dialog with nothing to scroll. */
.hub-source-found { max-height: 26vh; overflow-y: auto; }
.hub-source-offers { max-height: 40vh; overflow-y: auto; }
/* A folder is a line, not a picture: it has no thumbnail, so it should not reserve
   the height of one. */
.hub-source-row--folder { padding: 5px 8px; }
.hub-source-row {
  border: 1px solid var(--line-soft); border-radius: 6px; padding: 6px 8px;
}
.hub-source-name {
  font-size: var(--fs-body); color: var(--ink-2); word-break: break-all;
  line-height: 1.3;
}
.hub-source-meta { word-break: break-all; }
/* Big enough to judge the art by, which is the question the row exists to answer.
   A backglass at 64px told you a file was an image and nothing else. */
.hub-source-thumb {
  flex: 0 0 auto; width: 132px; height: 99px; border-radius: 4px;
  border: 1px solid var(--line); overflow: hidden; background: var(--surface-0);
  display: flex; align-items: center; justify-content: center;
  position: relative;
}
.hub-source-thumb img, .hub-source-thumb video {
  max-width: 100%; max-height: 100%; object-fit: contain;
}
/* A kind with no frame to show - audio, a rule sheet - keeps the same footprint, so a
   list of them does not step in and out as it scrolls. */
.hub-source-thumb-glyph { font-size: 32px; color: var(--ink-3); }

/* A bigger look at a thumbnail, on hover. These rows live inside a dialog, and opening
   a second dialog over the first to glance at a picture is a lot of ceremony - so this
   is a preview and not the viewer. It rides in a tooltip because the lists around it
   scroll, and anything drawn inside a scrolling box is clipped by it. */
.hub-thumb-peek {
  background: #0b0520 !important; padding: 4px !important;
  border: 1px solid #2b1a4d; border-radius: 6px;
  max-width: none !important;
}
/* Slightly larger, not a viewer. Big enough and it covers the rows either side of the
   one being pointed at, which is the list you are reading. */
.hub-thumb-peek img, .hub-thumb-peek video {
  display: block; max-width: 300px; max-height: 40vh;
}
/* Recognising a machine is a smaller question than judging a piece of art, and this
   list is the long one - a dozen results at the full size is most of a screen. The
   enlarge is what covers the case where the small picture is not enough. */
.hub-source-thumb--small { width: 76px; height: 57px; }
.hub-source-thumb--small .hub-source-thumb-glyph { font-size: 22px; }

/* What a file already does for this game, when it does something. Not a warning:
   using it again is legitimate, and the tag is there so nobody has to wonder. */
.hub-source-tag {
  font-size: var(--fs-caption); color: var(--accent); opacity: 0.85;
}

/* Quasar keeps the queued-file list at full height while it is empty. Uploads are
   automatic here, so the list only ever flashes. */
.hub-sources-card .q-uploader__list:empty { display: none; }
.hub-sources-card .q-uploader { width: 100%; max-height: 220px; }
.hub-sources-card .q-uploader__title {
  font-size: var(--fs-body); font-weight: 500; color: var(--ink-2);
}
.hub-sources-card .q-uploader__subtitle { display: none; }
/* Quasar fills the header with the primary color. Magenta reads as "selected"
   everywhere else in this UI, and this is a drop target, not a selection. */
/* Element-qualified and forced, because Quasar sets the header's fill from the
   primary color with the same specificity a class selector has. */
.hub-sources-card div.q-uploader__header {
  background: rgba(43,26,77,0.6) !important; border-bottom: 1px solid var(--line);
}
.hub-sources-card .q-uploader { background: var(--surface-2); border: 1px solid var(--line); }
/* The dashed target is the affordance; without a border the strip reads as a heading. */
.hub-sources-card .q-uploader__list {
  background: transparent; border: 1px dashed var(--line); border-top: none;
}

/* One markup, two readings. Wide, the rows are a rail down the left and the open
   section fills the column beside them. Narrow, they stack and the work falls under
   the row that opened it. Same control, same meaning, no threshold to guess: a rail
   with everything closed already looks like an accordion, so this is the same thing
   drawn in the room available.

   A track per row and then one that takes what is left, so the work spans the whole
   height rather than stopping under the last row. The count comes in on --rows,
   because CSS cannot count its own children. */
.hub-sections {
  /* Off the header. The name of what you are looking at and the list of what you can
     ask about it are two things, and butted together they read as one block. */
  margin-top: 12px;
  /* The rail column is panel and everything right of it is open to the page. A hard
     stop at the column's own width does that without a wrapper element to hang a
     background on - the rows are grid children, so there is nothing else to paint. */
  background: linear-gradient(90deg, var(--panel-ground) 0 152px, transparent 152px);
  display: grid;
  grid-template-columns: 152px minmax(0, 1fr);
  grid-template-rows: repeat(var(--rows, 4), max-content) minmax(0, 1fr);
  min-height: 0;
}
.hub-section-row { grid-column: 1; }
.hub-section-work {
  grid-column: 2; grid-row: 1 / -1;
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
.hub-workbench { container-type: inline-size; position: relative; z-index: 1; }

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
.hub-full .q-splitter__before { display: none !important; min-width: 0 !important; }
.hub-full .q-splitter__after { width: auto !important; flex: 10000 1 0% !important; }
.hub-full .q-splitter__separator { display: none; }

/* The row is the section's only name - there is no heading under it repeating the
   same words. */
/* Sized as navigation, because that is what it is. Title case and smaller than the
   app nav: these are headings, so they take heading case - but not the nav's uppercase,
   which would rank a game's sections with the app itself. */
/* The app nav's gutter rhythm, so the two rails read as the same kind of control. */
.hub-section-row {
  display: flex;
  cursor: pointer;
  font-size: var(--fs-body);
  font-weight: 500;
  color: var(--ink);
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
.hub-section-row:hover {
  background-image: linear-gradient(rgba(180, 41, 249, 0.14), rgba(180, 41, 249, 0.14));
}
/* Carries the row's padding, so every pixel of the band picks the section. */
.hub-section-hit { padding: 7px 16px; overflow: hidden; }
/* Beside its content, not above it - so there is nothing for a chevron to point at
   and the rail carries no picture at all. */
.hub-section-caret {
  display: none; color: var(--ink-2);
  padding: 0 12px;
  transition: transform 120ms;
}
.hub-section-on .hub-section-caret { color: var(--ink); }
.hub-section-on {
  background-image: linear-gradient(rgba(0, 217, 255, 0.22), rgba(0, 217, 255, 0.22));
  color: var(--ink);
}

/* Below the base rules on purpose: same specificity, so source order decides. */
@container (max-width: 519px) {
  /* Column, and the open section takes what the rows leave - so the names stay put
     and the content scrolls under them rather than the whole panel sliding. */
  .hub-sections { display: flex; flex-direction: column; background: none; }
  /* background-color, so a state tint layered on background-image sits over it. */
  .hub-section-row { background-color: var(--panel-ground); }
  /* Takes what it needs and no more, so a short section does not leave a void with
     the rows stranded at the bottom edge - and shrinks when it needs more than is
     there, which puts the scrolling inside it and keeps every row on screen. */
  .hub-section-work {
    flex: 0 1 auto;
    min-height: 0;
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
  .hub-section-row {
    flex: 0 0 auto;
    margin: 0; border-radius: 0;
    border-bottom: 1px solid var(--line-band);
  }
  .hub-section-hit { padding-left: var(--panel-gutter); }
  .hub-section-caret { display: flex; }
  /* Turned to point at what it opened, and the rule under the open row goes: the row
     and its content are one block, so a line between them would cut it in half. */
  .hub-section-on .hub-section-caret { transform: rotate(180deg); }
  .hub-section-on { border-bottom-color: transparent; }
}

.hub-index-item { border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: var(--fs-body);
                  color: var(--ink-2); }
.hub-index-item:hover { background: rgba(180, 41, 249, 0.14); }
.hub-index-item.hub-index-on {
  background: rgba(0, 217, 255, 0.22); color: var(--ink);
}
.hub-bar { height: 6px; border-radius: 3px; background: rgba(255,255,255,0.08); }
.hub-bar > div { height: 100%; border-radius: 3px; background: #00d9ff; }
"""
