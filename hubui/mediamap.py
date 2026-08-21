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

# Top of the cabinet down to the floor. Kinds on the same row are the same screen shown
# two ways - a still and its video - and share a row so the pair reads as one slot.
CAB_STACK: tuple[tuple[str, ...], ...] = (
    ("topper", "topper_video"),
    ("backglass", "backglass_video"),
    ("scoreview", "scoreview_video"),
    ("real_dmd", "real_dmd_color"),
    ("playfield", "playfield_video"),
    ("playfield_fss",),
    ("cab",),
)

# Everything that is not a surface on the machine.
EXTRAS = ("wheel", "logo", "flyer", "instruction_card", "rule_sheet",
          "loading", "audio", "audio_launch")

# Tile shape as an aspect ratio, width over height. A ratio rather than a height,
# because the pane is resizable: a fixed height with a fluid width stretches the box as
# the pane grows, which is the opposite of what widening it is for. With a ratio the
# silhouette holds and the art gets bigger.
#
# These are shapes, not measurements. A real playfield is 9:16 and at that ratio the
# tile would be taller than the pane; the values below keep portrait reading as portrait
# and a score display reading as a strip, which is all the map has to say.
TILE_AR = {
    "topper": 5.0, "topper_video": 5.0,
    "backglass": 1.9, "backglass_video": 1.9,
    "scoreview": 4.0, "scoreview_video": 4.0,
    "real_dmd": 4.0, "real_dmd_color": 4.0,
    "playfield": 0.7, "playfield_video": 0.7,
    "playfield_fss": 0.7,
    "cab": 1.5,
    "wheel": 1.0, "logo": 1.0,
    "flyer": 0.75,
    "instruction_card": 1.4, "rule_sheet": 1.4,
    "loading": 1.78,
    "audio": 4.0, "audio_launch": 4.0,
}

LABELS = {
    "backglass": "Backglass", "backglass_video": "Backglass video",
    "scoreview": "Score view", "scoreview_video": "Score view video",
    "playfield": "Playfield", "playfield_video": "Playfield video",
    "playfield_fss": "Playfield FSS", "wheel": "Wheel", "logo": "Logo",
    "cab": "Cabinet", "real_dmd": "Real DMD", "real_dmd_color": "Real DMD colour",
    "flyer": "Flyer", "audio": "Audio", "audio_launch": "Launch audio",
    "instruction_card": "Instruction card", "topper": "Topper",
    "topper_video": "Topper video", "loading": "Loading", "rule_sheet": "Rule sheet",
}

# Kinds an <img> cannot paint. A tile for one of these carries a glyph saying what it
# holds, rather than an image element that resolves to nothing - a present video drawn
# as a broken image reads as missing, which is the one thing this control must not do.
GLYPHS = {
    "audio": "graphic_eq",
    "audio_launch": "graphic_eq",
    "rule_sheet": "description",
    "loading": "movie",
}


def _glyph_for(kind: str) -> str | None:
    return GLYPHS.get(kind, "movie" if kind.endswith("_video") else None)


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
          on_pick: Callable[[str], None] | None, selected: str | None) -> None:
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
                pass
            elif glyph is not None:
                ui.icon(glyph, size="18px").classes("text-primary opacity-80")
            else:
                ui.html(f'<img src="{prefix}/{kind}" loading="lazy">')
        ui.label(LABELS.get(kind, kind)).classes("hub-mediatile-cap")
    tile.tooltip(_tooltip(kind, entry))


def _tooltip(kind: str, entry: dict[str, Any]) -> str:
    """The three facts about a slot, in the order a curator asks them.

    Does it resolve, how specific is the match, and where did the file come from.
    Origin is not derivable from the tier - your own art at the fixed name reads as
    `default` exactly like a download does.
    """
    if not entry.get("present"):
        return f"No {LABELS.get(kind, kind).lower()}"
    parts = [str(entry.get("file") or "")]
    if entry.get("via"):
        parts.append(f"resolved: {entry['via']}")
    if entry.get("origin"):
        parts.append(f"from: {entry['origin']}")
    return "  ·  ".join(part for part in parts if part)


def build(entries: dict[str, dict[str, Any]], prefix: str,
          on_pick: Callable[[str], None] | None = None,
          selected: str | None = None) -> None:
    """Draw the map into the current container.

    `prefix` is where the art is fetched from, and it is what the lens changes: the
    game's shared media, or one build's. The map itself does not care which.
    """
    with ui.column().classes("w-full gap-1 px-2 pb-2").style("max-width:640px"):
        ui.label("Cabinet screens").classes("hub-mediatile-group")
        for row in CAB_STACK:
            kinds = [kind for kind in row if kind in entries]
            if not kinds:
                continue
            with ui.row().classes("w-full gap-1 no-wrap items-end"):
                for kind in kinds:
                    _tile(prefix, kind, entries[kind], on_pick, selected)
        extras = [kind for kind in EXTRAS if kind in entries]
        if extras:
            ui.label("Other assets").classes("hub-mediatile-group")
            with ui.element("div").classes("hub-mediatile-grid"):
                for kind in extras:
                    _tile(prefix, kind, entries[kind], on_pick, selected)


def summary(entries: dict[str, dict[str, Any]]) -> tuple[int, int, int]:
    """present, borrowed, total - the numbers a header wants."""
    states = [_state(entry) for entry in entries.values()]
    return (states.count("present"), states.count("borrowed"), len(states))
