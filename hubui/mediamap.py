"""The media map: one tile per kind, laid out like the cabinet it describes.

A coverage report, a navigator and a picture of the machine, in one control. The tile's
shape carries the meaning - a playfield is tall, a score display is a strip, a wheel is
square - so the map is readable before any label is.

Kinds that are not a screen (audio, a rule sheet) cannot be placed on the cabinet and are
grouped after it rather than pretended into the stack.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from common.media_specs import media_family, media_label_map
from hubui import media_ownership, mediaview

# Top of the cabinet down to the floor. Kinds on the same row are the same screen shown
# two ways - a still and its video - and share a row so the pair reads as one slot.
CAB_STACK: tuple[tuple[str, ...], ...] = (
    ("topper", "topper_video"),
    ("backglass", "backglass_video"),
    ("scoreview", "scoreview_video"),
    ("real_dmd", "real_dmd_color"),
    ("playfield", "playfield_video"),
    # Paired, because a row splits its width between its tiles and a lone one takes
    # the whole of it.
    ("playfield_fss", "cab"),
)

# Everything that is not a surface on the machine.
EXTRAS = ("wheel", "logo", "flyer", "instruction_card", "rule_sheet",
          "loading", "audio", "audio_launch")

# Tile shape as an aspect ratio, width over height. A ratio rather than a height,
# because the pane is resizable: a fixed height with a fluid width stretches the box as
# the pane grows, which is the opposite of what widening it is for. With a ratio the
# silhouette holds and the art gets bigger.
#
# Measured from the files, not reasoned from the machine: the two disagree, and the file
# is what the tile has to hold. A playfield is portrait in the cabinet and 1920x1080 on
# disk; a cabinet is the reverse, a photo of one standing up.
TILE_AR = {
    "topper": 5.0, "topper_video": 5.0,
    "backglass": 1.9, "backglass_video": 1.9,
    "scoreview": 3.0, "scoreview_video": 3.0,
    "real_dmd": 4.0, "real_dmd_color": 4.0,
    # docs/media_flow.md: an fss.png is "the same subject as a table.png photographed
    # differently", so it takes the playfield's shape rather than one of its own.
    "playfield": 1.78, "playfield_video": 1.78,
    "playfield_fss": 1.78,
    "cab": 0.71,
    "wheel": 1.0, "logo": 1.0,
    "flyer": 0.75,
    "instruction_card": 1.4, "rule_sheet": 1.4,
    "loading": 1.78,
    "audio": 4.0, "audio_launch": 4.0,
}

# Kinds with no frame to show, which take a glyph instead - a present file drawn as a
# broken image reads as missing, the one thing this control must not do.
GLYPHS = {
    "audio": "graphic_eq",
    "audio_launch": "graphic_eq",
    "rule_sheet": "description",
}


def _glyph_for(kind: str) -> str | None:
    """The stand-in for a kind with nothing to show, or None if it has a frame.

    Derived from the kind's extension family rather than its name: `loading` is video
    and does not say so, so a `_video` suffix test gets that one wrong.
    """
    if kind in GLYPHS:
        return GLYPHS[kind]
    return {"audio": "graphic_eq", "doc": "description"}.get(media_family(kind))


# `#t=0.1` is what makes a frame appear: metadata alone can paint nothing, but a media
# fragment makes the browser seek there. Muted, or autoplay is refused.
_TILE_VIDEO = ('<video src="{src}#t=0.1" preload="metadata" muted playsinline loop'
               '></video>')

# Delegated: NiceGUI strips inline handlers off raw HTML, and a server binding would
# make a hover a round trip. The flag guards against a listener per rebuild.
_HOVER = """
if (!window.__hubTilePreview) {
  window.__hubTilePreview = true;
  const tileVideo = (el) => el && el.closest
    ? el.closest('.hub-mediatile')?.querySelector('.hub-mediatile-art video') : null;
  document.addEventListener('mouseover', (e) => {
    const v = tileVideo(e.target);
    if (v && v.paused) v.play().catch(() => {});
  });
  document.addEventListener('mouseout', (e) => {
    const v = tileVideo(e.target);
    if (!v) return;
    // Moving between children of the same tile is not leaving it.
    const tile = e.target.closest('.hub-mediatile');
    if (e.relatedTarget && tile && tile.contains(e.relatedTarget)) return;
    v.pause();
    v.currentTime = 0.1;
  });
}
"""


def _state(entry: dict[str, Any]) -> str:
    """present | borrowed | missing.

    `via` is what the resolver decided, so a file standing in for another kind reports
    itself as borrowed rather than as a plain hit. That distinction is the whole reason
    the map beats a tick: a borrowed wheel looks fine in the frontend and is still a gap.
    """
    if not entry.get("present"):
        return "missing"
    via = entry.get("via") or ""
    return "borrowed" if via.startswith("fallback:") else "present"


def _tile(prefix: str, kind: str, entry: dict[str, Any],
          on_pick: Callable[[str], None] | None, selected: str | None,
          differing: int = 0, offered: int = 0) -> None:
    state = _state(entry)
    ratio = TILE_AR.get(kind, 1.6)
    tile = ui.element("div").classes(
        f"hub-mediatile hub-mediatile--{state}"
        f"{' hub-mediatile--on' if kind == selected else ''}")
    if on_pick is not None:
        tile.classes("cursor-pointer").on("click", lambda k=kind: on_pick(k))
    with tile:
        glyph = _glyph_for(kind)
        with ui.element("div").classes("hub-mediatile-art") \
                .style(f"aspect-ratio:{ratio}"):
            if state == "missing":
                # The catalog has one and this slot does not, which is the only pairing
                # worth a mark: on a filled slot it would say somebody could replace
                # this, which is true of all of them. Counted as files, so a kind the
                # catalog holds only as a folder to browse marks nothing.
                if offered:
                    ui.icon("cloud_download", size="16px") \
                        .classes("hub-mediatile-offered") \
                        .tooltip(f"{offered} in the catalog"
                                 if offered > 1 else "One in the catalog")
            elif glyph is not None:
                ui.icon(glyph, size="18px").classes("text-primary opacity-80")
            elif media_family(kind) == "video":
                ui.html(_TILE_VIDEO.format(src=f"{prefix}/{kind}"))
            else:
                ui.html(f'<img src="{prefix}/{kind}" loading="lazy">')
            # Only where a file is genuinely a table's own. Marking the other twenty
            # tiles "All tables" would put a badge on every one of them and make the
            # map harder to read than it is without any.
            shared = media_ownership.key_of(entry.get("via")) == media_ownership.GAME
            if state != "missing" and not shared:
                media_ownership.badge(entry.get("via"), extra="hub-mediatile-tier")
            # From the game's lens the resolver never looks at a table's own tier, so
            # a slot one table differs on looks settled. This is the only thing that
            # says otherwise.
            if differing:
                plural = "" if differing == 1 else "s"
                ui.element("div").classes("hub-mediatile-differs") \
                    .tooltip(f"{differing} table{plural} use something else here")
            if state != "missing" and media_family(kind) in ("image", "video"):
                # click.stop, or enlarging would also pick the tile and redraw the
                # panel out from under the dialog.
                ui.button(icon="open_in_full") \
                    .props("flat dense round size=sm") \
                    .classes("hub-mediatile-zoom") \
                    .on("click.stop", lambda k=kind: mediaview.open_viewer(
                        f"{prefix}/{k}", k, media_label_map().get(k, k))) \
                    .tooltip("Enlarge")
        ui.label(media_label_map().get(kind, kind)).classes("hub-mediatile-cap")
    tile.tooltip(_tooltip(kind, entry))


def _tooltip(kind: str, entry: dict[str, Any]) -> str:
    """The file, and who uses it."""
    if not entry.get("present"):
        return f"No {media_label_map().get(kind, kind).lower()}"
    parts = [str(entry.get("file") or ""), media_ownership.phrase(entry.get("via"))]
    return "  ·  ".join(part for part in parts if part)


def build(entries: dict[str, dict[str, Any]], prefix: str,
          on_pick: Callable[[str], None] | None = None,
          selected: str | None = None,
          overrides: dict[str, list[dict[str, Any]]] | None = None,
          offered: dict[str, int] | None = None,
          kept: set[str] | None = None) -> None:
    """Draw the map into the current container.

    `prefix` is where the art is fetched from, and it is what the lens changes: the
    game's shared media, or one build's. The map itself does not care which.

    `offered` is how many files the catalog lists per kind. It only ever marks an empty
    slot: on a slot that is filled it would be saying somebody could replace this,
    which is true of every slot and so says nothing.

    `kept` is the kinds this library collects. A kind switched off is not drawn at all -
    not as an empty tile, which is the map saying "you are missing this" about something
    nobody wants.
    """
    if kept is not None:
        entries = {kind: entry for kind, entry in entries.items() if kind in kept}
    # Roughly the width browse gets once work takes its half, so the map fills it and
    # any surplus falls to the right.
    with ui.column().classes("w-full gap-1 pb-2").style(
            "max-width: 760px; padding-left: var(--panel-gutter);"
            " padding-right: var(--panel-gutter)"):
        for row in CAB_STACK:
            kinds = [kind for kind in row if kind in entries]
            if not kinds:
                continue
            # Stretch, so each tile fills the row and puts its caption at the foot of
            # it - captions on one line whatever shapes sit above them.
            with ui.row().classes("w-full gap-1 no-wrap items-stretch"):
                for kind in kinds:
                    _tile(prefix, kind, entries[kind], on_pick, selected,
                          len((overrides or {}).get(kind) or []),
                          (offered or {}).get(kind, 0))
        extras = [kind for kind in EXTRAS if kind in entries]
        if extras:
            # A rule, not a heading: the cabinet stack and everything else are
            # different shapes already, and naming them said nothing the tiles did not.
            ui.element("div").classes("hub-mediatile-rule")
            with ui.element("div").classes("hub-mediatile-grid"):
                for kind in extras:
                    _tile(prefix, kind, entries[kind], on_pick, selected,
                          len((overrides or {}).get(kind) or []),
                          (offered or {}).get(kind, 0))
    ui.run_javascript(_HOVER)


def summary(entries: dict[str, dict[str, Any]]) -> tuple[int, int, int]:
    """present, borrowed, total - the numbers a header wants."""
    states = [_state(entry) for entry in entries.values()]
    return (states.count("present"), states.count("borrowed"), len(states))
