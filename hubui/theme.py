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
  --ag-header-foreground-color: #b89dd9;
  --ag-foreground-color: #e8d5ff;
  --ag-font-size: 13px;

  /* Cyan carries selection and focus. Purple was doing every job at once, which is
     what made it read as flat - nothing stood out because everything was the accent. */
  /* Opaque, not a wash: a translucent selection composites over the two alternating
     bands differently, so a run of selected rows never reads as one block. */
  --ag-selected-row-background-color: #14314a;
  --ag-range-selection-border-color: #00d9ff;
  --ag-input-focus-border-color: #00d9ff;
  --ag-checkbox-checked-color: #00d9ff;
}
.ag-header { border-bottom: 1px solid rgba(0, 217, 255, 0.35) !important; }
/* Set on the row, not through --ag-selected-row-background-color: that variable is not
   honoured by AG Grid 34's theming, so selection was only ever the cyan bar and each
   selected row kept whichever alternating band it sat on. */
.ag-row-selected,
.ag-row-selected.ag-row-odd {
  background-color: #14314a !important;
  box-shadow: inset 3px 0 0 #00d9ff;
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
  font-size: 13px;
  color: #e8d5ff;
}
.q-menu .q-item:hover { background: #2a1a4a; }
.q-menu .q-separator { background: #3d2461; margin: 2px 0; }
/* The menu reads like the top of the workbench: heading in the title's voice,
   entries in the subtitle's. */
.hub-menu-header {
  color: #eef9ff;
  font-size: 16px;
  text-shadow: 0 0 6px rgba(0, 217, 255, 0.45);
  min-height: 26px !important;
  padding: 4px 12px !important;
}
.q-menu .hub-menu-item,
.q-menu .hub-menu-item .q-item__label {
  color: #7fc9dd;
  font-size: 11px;
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
.q-menu .hub-menu-item:hover .q-item__label { color: #00d9ff; }

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
  font-size: 10px;
  color: #7fc9dd;
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
.hub-label { color: #00d9ff; letter-spacing: 0.04em; }

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
  font-size: 14px;
  font-weight: 500;
  line-height: 24px;
  /* Sampled off the running 2.x nav, not read from manager.css: .nav-btn declares
     --ink-muted but never wins, and the items render at nicegui's default primary. The
     label above them is the only cyan in the panel. */
  color: #5898d4;
}
.q-drawer--left .cursor-pointer:hover .hub-nav-item { color: #8fc4f0; }
.q-drawer--left .cursor-pointer:hover .q-icon { color: #8fc4f0; opacity: 1; }
.q-drawer--left .q-icon { color: #5898d4; }

/* The row itself, also sampled: 48px tall on a 12px/16px pad with a 12px radius, so a
   highlighted row reads as a rounded block inset from the panel edge. */
/* Geometry only. The surface and border here came from matching the "Navigation"
   label's row, which was the wrong element - the title it now matches sits in 2.x's
   header bar with nothing drawn behind it. */
.hub-nav-header {
  min-height: 59px;
  padding: 12px !important;
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
  color: #eef9ff;
  text-shadow: 0 0 6px rgba(0, 217, 255, 0.45);
}
.hub-workbench-label {
  color: #00d9ff;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 11px;
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
.hub-workbench-body { padding: 0 6px; }
.hub-workbench .q-expansion-item .q-item {
  min-height: 32px;
  padding: 2px 10px;
}
.hub-workbench .q-expansion-item .q-item__label { color: #9fd8e8; font-size: 12px; }
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
.hub-panel-header .q-icon { color: #5898d4; }
.hub-workbench .q-expansion-item__content .row { min-height: 22px; }
.hub-nav-title {
  /* .manager-title, sampled: --ink with --glow-cyan behind it at 20px/900. The white
     comes from the near-white glyph and the colour from the halo, which is why a cyan
     glyph and a flat one both read wrong. */
  font-family: sans-serif;
  font-size: 20px;
  font-weight: 900;
  color: #e8d5ff;
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
  font-size: 12px;
  font-weight: 600;
  letter-spacing: normal;
  text-transform: uppercase;
  color: #e8d5ff !important;
}
.ag-header-cell-menu-button, .ag-header-icon { color: rgba(255,255,255,0.85) !important; }
"""


def apply_flair() -> None:
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
  border: 1px solid #2b1a4d;
  border-radius: 6px;
  background: rgba(10, 5, 24, 0.55);
  padding: 3px;
}
/* Present is stated with a colour, missing with the absence of one. A library is mostly
   gaps, so making the gap loud would make the workbench unreadable. */
.hub-mediatile--present { border-color: rgba(0, 217, 255, 0.55); }
.hub-mediatile--borrowed { border-color: rgba(255, 176, 32, 0.65); }
.hub-mediatile--missing { border-style: dashed; opacity: 0.55; }
.hub-mediatile--on { box-shadow: 0 0 0 2px #b429f9; border-color: #b429f9; }
.hub-mediatile-art {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 4px;
  background: #06030f;
}
.hub-mediatile-art img { max-width: 100%; max-height: 100%; object-fit: contain; }
.hub-mediatile-cap {
  display: block;
  font-size: 10px;
  line-height: 1.3;
  text-align: center;
  color: #cbb8ea;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hub-mediatile-group {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #7d6ba3;
  padding: 6px 0 2px;
}
.hub-mediatile-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  width: 100%;
}

/* --- section chrome -------------------------------------------------------------- */
.hub-crumb { color: #cbb8ea; font-size: 13px; }
.hub-crumb b { color: #eef9ff; font-weight: 600; }
.hub-card {
  border: 1px solid #2b1a4d;
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(26,15,53,0.75) 0%, rgba(15,7,34,0.75) 100%);
  padding: 14px 16px;
}
.hub-card-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #00d9ff;
}
.hub-kpi { font-size: 30px; font-weight: 700; color: #eef9ff; line-height: 1.1; }
/* The explanation under a control, not a tooltip on it. This is the whole legibility
   argument for the settings pages, so it gets a class rather than ad-hoc utilities. */
.hub-help { font-size: 11px; color: #9b8bbd; line-height: 1.4; max-width: 62ch; }
.hub-setting { font-size: 13px; color: #eef9ff; font-weight: 600; }
.hub-group {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #7d6ba3;
  padding: 10px 8px 4px;
}
.hub-index-item { border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 13px;
                  color: #cbb8ea; }
.hub-index-item:hover { background: rgba(180, 41, 249, 0.14); }
.hub-index-item.hub-index-on { background: rgba(180, 41, 249, 0.28); color: #eef9ff; }
.hub-bar { height: 6px; border-radius: 3px; background: rgba(255,255,255,0.08); }
.hub-bar > div { height: 100%; border-radius: 3px; background: #00d9ff; }
"""
