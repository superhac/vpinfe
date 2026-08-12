"""Every setting the config page names by hand still exists under that name.

The page sorts a section's keys into buckets - paths, launch overrides, chrome options -
and each bucket becomes a card. The buckets are built with `key in options` against
hardcoded names, and `options` comes from the parser, so it holds canonical names only.
When the snake_case rename landed the aliases kept every *read* working and these
membership tests silently stopped matching: all three buckets came back empty, every
setting fell into the catch-all, and the section rendered as one column with the derived
panes (the launch command preview, the effective chrome options) missing entirely.

Nothing failed, so this shipped. A membership test is what an alias cannot rescue, which
is why the names are pinned here instead.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from common.config_schema import canonical, spellings

PAGES = Path(__file__).resolve().parents[2] / "managerui" / "pages"

# The sections these pages special-case, and the keys they name inside each.
NAMED_KEYS = {
    "general": (
        "vpx_bin_path", "game_root_dir", "vpx_ini_path",
        "vpx_launch_env", "global_ini_override",
        "global_game_ini_override_enabled", "global_game_ini_override_mask",
        "disable_default_chrome_options", "chrome_options", "chrome_options_exclude",
        "auto_update_media_on_startup", "splashscreen", "mute_audio", "hide_quit_button",
    ),
    "displays": ("cab_mode",),
    "input": ("paging_type",),
    "libdmdutil": (
        "pixelcade_device", "zedmd_device", "zedmd_wifi_address", "pin2dmd_enabled",
    ),
    "media": ("realdmd_media_priority",),
    "mobile": ("rename_mask_to_default_ini", "rename_mask_to_default_ini_mask"),
    # VPinPlay gates its sync button and QR code on these, so a stale name here
    # disables both while the fields on screen are visibly filled in.
    "vpinplay": ("user_id", "initials", "machine_id", "api_endpoint", "sync_on_exit"),
}

SOURCES = ("vpinfe_config.py", "vpinplay.py")


class ConfigPageKeyTests(unittest.TestCase):
    def test_named_keys_are_canonical(self) -> None:
        """A key whose canonical name differs is one a rename left behind."""
        for section, keys in NAMED_KEYS.items():
            for key in keys:
                with self.subTest(section=section, key=key):
                    self.assertEqual(canonical(section, key), key)

    def test_pages_do_not_name_a_stale_spelling(self) -> None:
        """The pages' own string literals, checked against the schema."""
        for source in SOURCES:
            with self.subTest(source=source):
                literals = {
                    node.value
                    for node in ast.walk(ast.parse((PAGES / source).read_text(encoding="utf-8")))
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                stale = [
                    f"{section}.{older} (now {key})"
                    for section, keys in NAMED_KEYS.items()
                    for key in keys
                    for older in _older_spellings(section, key)
                    if older in literals
                ]
                self.assertEqual(stale, [], f"{source} still names renamed settings: {stale}")


def _older_spellings(section: str, key: str) -> set[str]:
    """Names this setting has gone by that are no longer canonical."""
    return {name for name in spellings(section, key) if name != key}
