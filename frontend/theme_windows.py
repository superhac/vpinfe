"""Which windows a theme wants, and what each one is called.

Declaring nothing gets the three VPinFE has always opened, under the names the theme's
contract uses - which is how index_table.html keeps working with no fallback lookup.
Everything else about a window follows from its name.
"""

from __future__ import annotations

import re
from pathlib import Path

from frontend import theme_api

MANIFEST_KEY = "windows"

# The three VPinFE opens when a theme says nothing. The controller is first here and
# launched last, so it takes focus.
DEFAULT_WINDOWS = {
    1: ("table", "bg", "dmd"),
    2: ("playfield", "backglass", "scoreview"),
}

# Contract 1's window names, and what each is called now. The names come from Visual
# Pinball's plugin contract - Playfield, Backglass, ScoreView - which is where a window
# name should come from, since VPinFE is a front end for it. In VPX a DMD is a render
# style rather than a window; the window that shows a score is ScoreView.
#
# A contract 1 theme keeps its own spellings: it still gets `table`, `bg` and `dmd`
# windows and still loads index_bg.html. Only the canonical side moved.
CANONICAL = {"table": "playfield", "bg": "backglass", "dmd": "scoreview"}


# Windows whose label is not just the capitalized name. The contract 1 spellings keep
# the titles they shipped with, so a cabinet's window rules keep matching them.
TITLES = {"bg": "BG", "dmd": "DMD", "scoreview": "ScoreView"}

# A window name reaches the bootstrap page from the URL and is written into its HTML, so
# it is checked rather than trusted. Theme window names are plain words by construction -
# they have to name a file.
_NAME = re.compile(r"[A-Za-z0-9_-]+")


def window_title(window: str) -> str | None:
    """The label for a window, or None when the name could not be one."""
    name = str(window or "").strip()
    if not _NAME.fullmatch(name):
        return None
    return TITLES.get(name.lower(), name.capitalize())


def canonical(window: str) -> str:
    name = str(window or "").strip()
    return CANONICAL.get(name, name)


def screen_key(window: str) -> str:
    """The name under which this window's monitor is looked up.

    Still `<window>screenid` rather than the `windows.<name>.screen_id` the file now
    uses, because it is a lookup token here and not a location - `window_screen_id`
    resolves it either way, and a window a theme invented has no schema entry to move.
    """
    return f"{canonical(window)}screenid"


def declared_windows(theme_dir, contract: int) -> tuple[str, ...]:
    """The windows this theme wants, controller first."""
    default = DEFAULT_WINDOWS.get(contract, DEFAULT_WINDOWS[1])
    if theme_dir is None:
        return default
    manifest = theme_api.read_manifest(theme_dir) or {}
    declared = manifest.get(MANIFEST_KEY)
    if isinstance(declared, list):
        names = tuple(str(name).strip() for name in declared if str(name).strip())
        if names:
            return names
    return _windows_with_a_page(theme_dir, default)


def _windows_with_a_page(theme_dir, default: tuple[str, ...]) -> tuple[str, ...]:
    """The default, minus any window this theme has no page for.

    Only the default is trimmed - a declared window opens whether its page exists or not.
    """
    present = tuple(name for name in default
                    if (Path(theme_dir) / f"index_{name}.html").is_file())
    return present or default


def controller(windows) -> str:
    """The window that owns input, audio and the selection."""
    return windows[0] if windows else ""


def launch_order(windows):
    """Controller last, so it ends up with focus."""
    return list(reversed(list(windows)))
