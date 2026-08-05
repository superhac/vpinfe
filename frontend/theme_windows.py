"""Which windows a theme wants, and what each one is called.

Declaring nothing gets the three VPinFE has always opened, under the names the theme's
contract uses - which is how index_table.html keeps working with no fallback lookup.
Everything else about a window follows from its name.
"""

from __future__ import annotations

from pathlib import Path

from frontend import theme_api

MANIFEST_KEY = "windows"

# The three VPinFE opens when a theme says nothing. The controller is first here and
# launched last, so it takes focus.
DEFAULT_WINDOWS = {
    1: ("table", "bg", "dmd"),
    2: ("playfield", "bg", "dmd"),
}

# Contract 1 calls the playfield window `table`. The ini key never moved, so the two
# spellings have to agree on which monitor setting they mean.
CANONICAL = {"table": "playfield"}


def canonical(window: str) -> str:
    name = str(window or "").strip()
    return CANONICAL.get(name, name)


def screen_key(window: str) -> str:
    """The `[Displays]` key naming this window's monitor."""
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
