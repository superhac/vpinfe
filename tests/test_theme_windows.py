"""Which windows a theme gets, and what each one is called.

The window name decides four things at once - the HTML file, the `?window=` value, the
WebSocket identity and the monitor key - so getting the default wrong for a contract
would silently stop twelve published themes from loading.
"""

from __future__ import annotations

import json
import unittest
from configparser import ConfigParser
from pathlib import Path
from tempfile import TemporaryDirectory

from common.config_access import DisplayConfig
from frontend import theme_windows


def _theme(root: Path, manifest: dict | None) -> Path:
    theme = root / "a-theme"
    theme.mkdir(parents=True)
    if manifest is not None:
        (theme / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return theme


class DefaultsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_contract_1_keeps_the_names_published_themes_use(self) -> None:
        """index_table.html and ?window=table have to go on working untouched."""
        theme = _theme(self.root, {"name": "a-theme"})

        self.assertEqual(theme_windows.declared_windows(theme, 1), ("table", "bg", "dmd"))

    def test_contract_2_uses_the_current_vocabulary(self) -> None:
        theme = _theme(self.root, {"name": "a-theme", "contract": 2})

        self.assertEqual(theme_windows.declared_windows(theme, 2),
                         ("playfield", "bg", "dmd"))

    def test_a_theme_with_no_manifest_still_gets_windows(self) -> None:
        theme = _theme(self.root, None)

        self.assertEqual(theme_windows.declared_windows(theme, 1), ("table", "bg", "dmd"))

    def test_a_declaration_that_is_not_a_list_is_ignored(self) -> None:
        theme = _theme(self.root, {"windows": "playfield"})

        self.assertEqual(theme_windows.declared_windows(theme, 2),
                         ("playfield", "bg", "dmd"))


class DeclaredTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_theme_can_ask_for_a_window_vpinfe_never_had(self) -> None:
        theme = _theme(self.root, {"windows": ["playfield", "bg", "dmd", "topper"]})

        windows = theme_windows.declared_windows(theme, 2)

        self.assertIn("topper", windows)
        self.assertEqual(theme_windows.screen_key("topper"), "topperscreenid")

    def test_the_first_window_is_the_controller(self) -> None:
        theme = _theme(self.root, {"windows": ["playfield", "bg"]})

        self.assertEqual(theme_windows.controller(
            theme_windows.declared_windows(theme, 2)), "playfield")

    def test_the_controller_is_launched_last_so_it_takes_focus(self) -> None:
        order = theme_windows.launch_order(("playfield", "bg", "dmd"))

        self.assertEqual(order[-1], "playfield")


class ScreenKeyTests(unittest.TestCase):
    def test_the_playfield_key_is_the_same_under_either_spelling(self) -> None:
        """Contract 1 calls the window `table`; the ini key never moved."""
        self.assertEqual(theme_windows.screen_key("table"), "playfieldscreenid")
        self.assertEqual(theme_windows.screen_key("playfield"), "playfieldscreenid")

    def test_an_unheard_of_window_reads_its_own_key(self) -> None:
        config = ConfigParser()
        config.read_dict({"Displays": {"playfieldscreenid": "0", "topperscreenid": "2"}})

        displays = DisplayConfig.from_config(config)

        self.assertEqual(displays.window_screen_id("topperscreenid"), "2")
        self.assertEqual(displays.window_screen_id("nosuchscreenid"), "",
                         "a window with no monitor set is simply not launched")


if __name__ == "__main__":
    unittest.main()
