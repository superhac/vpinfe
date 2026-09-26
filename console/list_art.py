"""The picture ahead of a name in a list: which one, where it is served, and its frame.

Every list draws the same frame at the same size, holding the row's glyph where there is
no picture. The address comes from `console/art.py`.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from common import config_schema
from common.config_access import cfg_get
from common.paths import get_ini_config
from console import art

# The row field holding the address, "" where the row has none. A row without the field
# is drawn with no frame at all.
FIELD = "art"
# The two sizes: 80 x 40 in the list rows, 128 x 72 in the Themes grid.
LIST = "list"
PREVIEW = "preview"
# The list frame and the gap after it, which a name column grows by.
ROOM_PX = 92

_PICTURED = "console-cell-pictured"
_BOX = "console-cell-art-box"
_SIZED = {LIST: f"{_BOX} {_BOX}--list", PREVIEW: _BOX}
_GLYPH_BOX = f"{_BOX}--glyph"
_NO_ART = "console-cell-noart"
_LINES = "console-cell-lines"
_PATH_DATA = re.compile(r"^[Mm]\s?[-+]?\.?\d")


def chosen(kept: set[str]) -> str:
    """The kind the lists draw, or "" for none: None, or a kind Media Kinds does not
    keep. A value the setting does not offer reads as its default."""
    option = config_schema.option("console", "list_art")
    assert option is not None
    value = cfg_get(get_ini_config(), "console", "list_art")
    if value not in option.choices:
        value = str(option.default)
    return value if value != "none" and value in kept else ""


def address(row: dict[str, Any]) -> str:
    """Where a tables-listing row's art is served at list size, or "" where it has none.

    A keyed table has no file to name art after, so its art is the game's."""
    kind, version = row.get("art_kind"), row.get("art_version")
    if not kind or not version:
        return ""
    table = "" if row.get("key") else str(row.get("id") or "")
    return art.media(str(row.get("game_id") or ""), str(kind), table,
                     version=str(version), size=art.CELL)


def by_game(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Each game's art from the tables listing: its default table's, else its first's."""
    shown: dict[str, str] = {}
    for row in rows:
        game_id = str(row.get("game_id") or "")
        if game_id not in shown or row.get("default"):
            shown[game_id] = address(row)
    return shown


def glyph_html(glyph: str) -> str:
    """A glyph as the frame holds it: SVG path data, or a Material icon's name."""
    if _PATH_DATA.match(glyph):
        return (f'<svg class="{_NO_ART}" viewBox="0 0 24 24" aria-hidden="true">'
                f'<path d="{html.escape(glyph)}"/></svg>')
    return f'<i class="material-icons {_NO_ART}" aria-hidden="true">{html.escape(glyph)}</i>'


def frame_js(glyph: str, size: str = LIST) -> str:
    """A grid cell renderer's expression for the frame and the name's lines beside it.

    Reads `art`, `lines` and `esc` from the renderer: `art` is the address, or "" for
    the glyph. A picture that fails to load gives way to the glyph.
    """
    swap = f"this.parentNode.classList.add('{_GLYPH_BOX}');this.remove()"
    opened = f'<span class="{_PICTURED}"><span class="{_SIZED[size]}'
    with_picture = json.dumps(
        f'{opened}"><img loading="lazy" alt="" draggable="false" onerror="{swap}" src="')
    without = json.dumps(f'{opened} {_GLYPH_BOX}">')
    beside = json.dumps(f'{glyph_html(glyph)}</span><span class="{_LINES}">')
    return (f"(art ? {with_picture} + esc(art) + '\">' : {without})"
            f" + {beside} + lines + '</span></span>'")
