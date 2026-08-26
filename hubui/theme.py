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
# table's own row colours. AG Grid reads its palette from --ag-* custom properties, so
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
  --flair: #b429f9;      /* fills and borders only   4.4:1 */

  --surface-0: #0a0518;
  --surface-1: #150a2e;
  --surface-2: #1a0f35;
  --line: #2b1a4d;
  --line-soft: #1f1338;

  --fs-caption: 12px;
  --fs-body: 14px;
  --fs-subject: 16px;
  --fs-title: 20px;
  /* A stat, not prose - the one place a number is the content. */
  --fs-display: 30px;

  /* 44px where a finger is in scope; the hub is desk-first, so this is the floor. */
  --target-min: 32px;

  /* What a draggable divider looks like, wherever one appears - a border colour here
     reads as an edge rather than a handle. */
  /* Who owns a media file. Amber is the only warm colour in this palette, which is
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
/* The base colour goes on body alone. Painting it on .q-page-container too put an
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
     narrow - #1a0f35 against #251447 read as two different colours rather than as
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
/* Two states, one colour: both answer "which one", and a second hue would read as a
   third meaning. Selected is a fill, focused is a band, and a row can be both.
   Set on the row, not --ag-selected-row-background-color, which AG Grid 34 ignores. */
.ag-row-selected,
.ag-row-selected.ag-row-odd {
  background-color: #14314a !important;
  box-shadow: inset 3px 0 0 var(--accent);
}

/* Focus follows the row, not the cell: nothing in a cell can be acted on. Drawn as
   top and bottom lines because a row is three elements - pinned left, centre, pinned
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
/* The menu reads like the top of the workbench: heading in the title's voice,
   entries in the subtitle's. */
.hub-menu-header {
  color: var(--ink);
  font-size: var(--fs-subject);
  text-shadow: 0 0 6px rgba(0, 217, 255, 0.45);
  min-height: 26px !important;
  padding: 4px 12px !important;
}
.q-menu .hub-menu-item,
.q-menu .hub-menu-item .q-item__label {
  color: var(--accent);
  font-size: var(--fs-caption);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
/* Each row on its own line, tight, label reading left to right after the box. */
.q-menu .q-checkbox.hub-menu-item {
  display: flex;
  padding: 2px 12px;
  min-height: 26px;
}
.q-menu .q-checkbox.hub-menu-item:hover { background: #2a1a4a; }

.q-menu .hub-menu-item:hover,
.q-menu .hub-menu-item:hover .q-item__label { color: var(--accent); }

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
}

/* At the rail the row is the icon's whole world, so the wide state's side padding
   pushes it off centre. Set here because that padding is !important and a utility
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
     off-centre. 2.x's .nav-btn solves it the same way. */
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
  /* The nav's gradient with its accent band removed - same stops from #1a0f35 down, so
     the two panels read as one surface treatment. The band stays exclusive to the nav
     because it marks the product, and this panel has no identity to carry. */
  background: linear-gradient(180deg, #1a0f35 0%, #150a2e 30%, #0f0722 100%) !important;
}
/* truncate only ellipsizes against a definite width. The column may shrink under
   min-w-0, but its labels have to be told to take that width or they overflow and get
   cropped by the parent instead of ellipsised. */
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
/* No gutter of its own: what it holds carries the shared one, and two would stack. */
.hub-workbench-body { padding: 0; }
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
/* The panel toggles match: nav and workbench are the same control, same colour. */
.hub-panel-header .q-icon { color: var(--ink-2); }
.hub-workbench .q-expansion-item__content .row { min-height: 22px; }
.hub-nav-title {
  /* .manager-title, sampled: --ink with --glow-cyan behind it at 20px/900. The white
     comes from the near-white glyph and the colour from the halo, which is why a cyan
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
  background: rgba(10, 5, 24, 0.55);
  padding: 3px;
}
/* Present is stated with a colour, missing with the absence of one. A library is mostly
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

/* Flat buttons are text, and Quasar gives them `primary` - the flair colour, at 4.4:1.
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

/* An action has to look like one, and colour alone never says so - it is silent to
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
/* A destructive action is still an action - it takes the same shape and says what it
   is with colour on top, not instead. */
.hub-action.hub-action--danger.q-btn { border-color: rgba(255, 107, 157, 0.45); }
.hub-action.hub-action--danger.q-btn:hover {
  border-color: #ff6b9d; background: rgba(255, 107, 157, 0.12);
}

/* `size=sm` writes an inline font-size, which no selector outranks. */
.q-btn--dense .q-btn__content { font-size: var(--fs-caption) !important; }
.q-btn--dense { font-size: var(--fs-caption) !important; }

/* Every control clears the pointer floor - what is fine for a mouse is mean on a
   trackpad. Dense rather than flat, because the toolbar tabs are `unelevated`. */
.q-btn--dense, .hub-outline-item {
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
     is about its own centre, so that box is the right thing to centre on. */
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
.hub-mediatile-group {
  font-size: var(--fs-caption);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-3);
  padding: 6px 0 2px;
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
.hub-lens-select { max-width: 340px; margin-top: 2px; }
.hub-lens-select .q-field__native {
  font-size: var(--fs-caption); color: var(--ink-2);
}
/* The floating label is the word "Showing"; at rest it sits inside the control, so
   it needs to read as a label and not as the value. */
.hub-lens-select .q-field__label {
  font-size: var(--fs-caption); color: var(--ink-3);
}

.hub-lens-label {
  font-size: var(--fs-caption); text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--ink-3);
}

/* Body and dock, and one rule for where the dock goes. Under the body it is a
   vertical split - the map scrolls, the controls do not, and picking a tile can never
   put them somewhere you have to go looking. Past the work width they sit side by
   side instead, which is what the room is for. */
.hub-workbench-main {
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
  .hub-workbench-main {
    /* `auto` so the track follows the dock's own width. */
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-rows: minmax(0, 1fr);
    grid-template-areas: none;
  }
  /* Half the workbench, so a wide window has no dead middle. The floor keeps it
     usable where half is not much. */
  .hub-dock { width: max(320px, 50cqw); }
  .hub-dock-grip { display: none; }
}
/* The handle between browse and work. Only where they are stacked - side by side the
   split is the panel's own width, which the outer splitter already owns. */
.hub-dock-grip {
  /* The line is 1px; the rest is the room either side of it. */
  height: 19px; cursor: row-resize; flex: 0 0 auto;
  background: linear-gradient(180deg, transparent 0, transparent 9px,
                              var(--resize-line) 9px, var(--resize-line) 10px,
                              transparent 10px, transparent 19px);
}
.hub-dock-grip:hover {
  background: linear-gradient(180deg, transparent 0, transparent 9px,
                              var(--accent) 9px, var(--accent) 10px,
                              transparent 10px, transparent 19px);
}
/* The work region keeps its room whether or not anything is in it: collapsing it
   reflows browse under the cursor that just picked something. */
/* Centred in the reserved room: text in the top corner reads as a mistake. */
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
}

/* The chosen section's heading when it has the window to itself - there is no
   expansion to click, so the name has to come from somewhere. */
.hub-work-title {
  font-size: var(--fs-caption); text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--accent); padding: 8px 10px 4px;
}

/* A form has nothing to choose, so it stays one column and leaves the rest alone
   rather than stretching four fields across the window. */
.hub-form { max-width: 420px; }

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
/* The filename is the one identifier a user recognises, so it reads first and whole -
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

/* A tick column is scanned, not read: centre it so the eye runs down one line. */
.hub-tick { text-align: center; color: var(--accent); }

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
   so on hover instead of hiding a click behind a label. */
.hub-source-row--folder { cursor: pointer; }
/* One line for a folder: these names carry the maker and year and run long, and four
   wrapped lines of one row makes a list of them unreadable. */
.hub-source-row--folder .hub-source-name {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  word-break: normal; min-width: 0;
}
.hub-source-trail { word-break: break-word; padding-bottom: 2px; }
.hub-source-row--folder:hover {
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
}
.hub-source-thumb img, .hub-source-thumb video {
  max-width: 100%; max-height: 100%; object-fit: contain;
}
/* A kind with no frame to show - audio, a rule sheet - keeps the same footprint, so a
   list of them does not step in and out as it scrolls. */
.hub-source-thumb-glyph { font-size: 32px; color: var(--ink-3); }

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
/* Quasar fills the header with the primary colour. Magenta reads as "selected"
   everywhere else in this UI, and this is a drop target, not a selection. */
/* Element-qualified and forced, because Quasar sets the header's fill from the
   primary colour with the same specificity a class selector has. */
.hub-sources-card div.q-uploader__header {
  background: rgba(43,26,77,0.6) !important; border-bottom: 1px solid var(--line);
}
.hub-sources-card .q-uploader { background: var(--surface-2); border: 1px solid var(--line); }
/* The dashed target is the affordance; without a border the strip reads as a heading. */
.hub-sources-card .q-uploader__list {
  background: transparent; border: 1px dashed var(--line); border-top: none;
}

/* Down, never across: in a column of modes a sideways bar means the items do not
   fit, never that there is more to reach. */
.hub-outline {
  /* Widened with the gutter below, so the labels keep their room rather than paying
     for it. */
  border-right: 1px solid var(--line-soft); width: 152px;
  overflow-x: hidden;
}
/* Narrow: still a column, now icons - the app nav does the same, so the control never
   changes kind. A column also grows down the axis a narrow panel has spare. The word
   lives on the tooltip. */
/* The workbench measures itself, so the outline appears the moment the drag crosses
   the width rather than when the mouse comes up. */
.hub-workbench { container-type: inline-size; }

/* The splitter measures in pixels, so shrinking the window used to come entirely out
   of the list: the workbench held its width and the list was left with a Name column
   too narrow to read and a toolbar wrapped one word per line. A floor here makes the
   workbench give way instead - it shrinks gracefully because everything in it is
   already sized by its own width, and the list has nowhere to go. */
/* Said here rather than left to Quasar's default, so both dividers move together if
   the value ever changes. */
.q-splitter__separator { background-color: var(--resize-line) !important; }
.q-splitter__separator:hover { background-color: var(--accent) !important; }

.q-splitter__before { min-width: 380px; container-type: inline-size; }

/* And when even that is tight, the parts that are commentary go before the parts that
   are the work. */
@container (max-width: 560px) { .hub-crumb-note { display: none; } }

/* Full: the workbench takes the window and the list steps back to a rail. Quasar puts
   an inline width on the pane it sizes, so this swaps which of the two flexes rather
   than fighting that number - and being CSS, it lands the moment it is asked for. */
/* Hidden, not squeezed. A grid at 57px is not a rail - it is a grid with its toolbar
   wrapped into a column of single words. Nothing is stranded by this: the control that
   brings it back sits in the workbench header, which is always on screen. */
.hub-full .q-splitter__before { display: none !important; min-width: 0 !important; }
.hub-full .q-splitter__after { width: auto !important; flex: 10000 1 0% !important; }
.hub-full .q-splitter__separator { display: none; }

/* The outline carries the grouping once it is there; the body only needs it when it
   is the only structure on screen. */
/* Sized as navigation, because that is what it is. Still smaller and sentence-case
   than the app nav: two uppercase columns would rank a game's sections with the app. */
/* The app nav's gutter rhythm, so the two rails read as the same kind of control. */
.hub-outline-item {
  display: flex;
  font-size: var(--fs-body);
  font-weight: 500;
  color: var(--ink);
  padding: 7px 16px;
  margin: 2px 8px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hub-outline-item:hover { background: rgba(180, 41, 249, 0.14); }
.hub-outline-on { background: rgba(0, 217, 255, 0.22); color: var(--ink); }

/* Below the base rules on purpose: same specificity, so source order decides. Above
   them the wide padding wins and the items overflow the rail. */
@container (max-width: 519px) {
  .hub-outline { width: 48px; padding-right: 0; }
  .hub-outline-text { display: none; }
  .hub-outline-item {
    /* Stretched to the rail, or the item is only as wide as its icon and centring
       happens inside a 20px box that is itself sitting at the left edge. */
    align-self: stretch;
    justify-content: center;
    padding: 6px 0; margin: 2px 4px;
  }
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
