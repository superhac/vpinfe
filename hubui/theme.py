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
   the details pane's 54px top gap, not anything the rows were doing. Scoped to the
   right drawer on purpose: the nav wants that breathing room, the inspector does not,
   because it has far more to fit. */
.q-drawer--right .q-drawer__content {
  /* Gap goes, top padding stays: the gap was the double-spacing, but the 16px top is
     what puts this header level with the nav's, which keeps it. */
  padding: 16px 0 0 !important;
  gap: 0 !important;
}
/* 18px is what centring a 20px icon in the 57px rail produces, so matching it here
   means the icon does not move horizontally when the panel collapses. */
.q-drawer--right .hub-panel-header { padding-right: 18px !important; }
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
  background: linear-gradient(180deg, #2a1a4a 0%, #150a2e 45%, #0f0722 100%) !important;
}
.hub-nav-item {
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 12px;
  /* Muted at rest, full cyan on hover. Seven items at the title's brightness would
     compete with it and leave nothing to mark the one under the cursor. */
  color: #7fc9dd;
}
.q-drawer--left .cursor-pointer:hover .hub-nav-item { color: #00d9ff; }
.q-drawer--left .cursor-pointer:hover .q-icon { color: #00d9ff; opacity: 1; }
.q-drawer--left .q-icon { color: #7fc9dd; }

/* One accent, not three. Purple is surface - gradients, borders, the grid header - and
   cyan is the only thing that accents. Pink was a third hue close enough to the header
   magenta to muddle rather than contrast; the panels are told apart by tone instead,
   the nav title at full neon and this one near-white with a softer halo. */
.q-drawer--right {
  background: linear-gradient(180deg, #2a1a4a 0%, #150a2e 45%, #0f0722 100%) !important;
}
.hub-detail-title {
  color: #eef9ff;
  text-shadow: 0 0 6px rgba(0, 217, 255, 0.45);
}
.hub-detail-label {
  color: #7fc9dd;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 11px;
}
/* Tight: this panel carries a lot and the default expansion chrome is mostly air. */
.q-drawer--right .q-expansion-item {
  border: 1px solid #2b1a4d;
  border-radius: 8px;
  /* Vertical margin only. A horizontal margin on a w-full child overhangs by exactly
     its own width, which is where the panel's 6px of horizontal scroll came from; the
     inset belongs on the container. */
  margin: 4px 0;
  background: rgba(26, 15, 53, 0.55);
}
.q-drawer--right .q-drawer__content { overflow-x: hidden !important; }
.hub-detail-body { padding: 0 6px; }
.q-drawer--right .q-expansion-item .q-item {
  min-height: 32px;
  padding: 2px 10px;
}
.q-drawer--right .q-expansion-item .q-item__label { color: #9fd8e8; font-size: 12px; }
.q-drawer--right .q-expansion-item__content { padding: 2px 0 6px; }
/* nicegui puts a 16px flex gap on .nicegui-expansion-content, which double-spaced every
   line inside a section: 22px rows on a 38px pitch. Same default as the drawer's, in a
   different container - the rows carry their own spacing. */
.q-drawer--right .nicegui-expansion-content {
  /* Both of nicegui's defaults on this container: the 16px gap double-spaced the lines
     and the 16px padding is the dead space above the first field and below the last. */
  gap: 0 !important;
  padding: 0 !important;
}
/* The panel toggles match: nav and details are the same control, so the same colour. */
.hub-panel-header .q-icon { color: #7fc9dd; }
.q-drawer--right .q-expansion-item__content .row { min-height: 22px; }
.hub-nav-title {
  letter-spacing: 0.04em;
  /* Neon reads as a white-hot core inside a coloured halo, not as flat cyan text. So
     the glyph is a near-white cyan and the glow is manager.css's --glow-cyan. */
  color: #d9f7ff;
  text-shadow: 0 0 4px rgba(0, 217, 255, 0.9), 0 0 10px rgba(0, 217, 255, 0.55),
               0 0 18px rgba(0, 217, 255, 0.3);
}

.nicegui-aggrid {
  border: 1px solid #3d2461;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(180, 41, 249, 0.2);
}
.ag-header {
  background: linear-gradient(135deg, #b429f9 0%, #7d1fb0 55%, #4a1e7c 100%) !important;
  border-bottom: 1px solid #3d2461 !important;
}
.ag-header-cell-text { color: #ffffff !important; letter-spacing: 0.03em; }
.ag-header-cell-menu-button, .ag-header-icon { color: rgba(255,255,255,0.85) !important; }
"""


def apply_flair() -> None:
    ui.add_css(_FLAIR)


def apply_colors(dark: bool) -> None:
    """Swap the palette. The page owns the single ui.dark_mode element and passes its
    value in - creating one per call leaves several fighting over the same body class."""
    ui.colors(**(DARK if dark else LIGHT))
