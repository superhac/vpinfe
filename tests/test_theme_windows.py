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
from frontend import theme_api, theme_windows


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


class PagesDecideTheDefaultTests(unittest.TestCase):
    """A theme that declares nothing gets a window per page it ships, not three."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _theme_with(self, pages, manifest=None) -> Path:
        theme = _theme(self.root, manifest if manifest is not None else {"name": "a-theme"})
        for page in pages:
            (theme / f"index_{page}.html").write_text("", encoding="utf-8")
        return theme

    def test_a_one_screen_theme_gets_one_window(self) -> None:
        """carousel2 ships only index_table.html; opening bg and dmd served two 404s."""
        theme = self._theme_with(["table"])

        self.assertEqual(theme_windows.declared_windows(theme, 1), ("table",))

    def test_a_three_screen_theme_is_unchanged(self) -> None:
        theme = self._theme_with(["table", "bg", "dmd"])

        self.assertEqual(theme_windows.declared_windows(theme, 1), ("table", "bg", "dmd"))

    def test_a_theme_with_no_pages_at_all_still_gets_the_default(self) -> None:
        """Nothing to learn from, so behave as before rather than opening no windows."""
        theme = self._theme_with([])

        self.assertEqual(theme_windows.declared_windows(theme, 1), ("table", "bg", "dmd"))

    def test_a_declared_window_is_honored_even_with_no_page(self) -> None:
        """An explicit declaration is intent; silently dropping it would hide the bug."""
        theme = self._theme_with(["playfield"], {"windows": ["playfield", "topper"]})

        self.assertEqual(theme_windows.declared_windows(theme, 2), ("playfield", "topper"))

    def test_the_count_in_the_manifest_is_not_what_decides(self) -> None:
        """`supported_screens` never opened a window; the pages are the real answer."""
        theme = self._theme_with(["table"], {"name": "a-theme", "supported_screens": 3})

        self.assertEqual(theme_windows.declared_windows(theme, 1), ("table",))


class IndexPageTests(unittest.TestCase):
    """The window name picks the file, so the contract decides which file a theme ships."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _pages(self, contract: int) -> list[str]:
        theme = _theme(self.root, {"name": "a-theme", "contract": contract})
        config = ConfigParser()
        config.read_dict({"Settings": {"theme": "a-theme"}})
        return [theme_api.get_theme_index_page(config, window)
                for window in theme_windows.declared_windows(theme, contract)]

    def test_contract_1_asks_for_index_table(self) -> None:
        self.assertIn("index_table.html", self._pages(1)[0])

    def test_contract_2_asks_for_index_playfield(self) -> None:
        """A contract 2 theme shipping index_table.html gets a 404, so docs say playfield."""
        self.assertIn("index_playfield.html", self._pages(2)[0])

    def test_a_window_vpinfe_never_had_names_its_own_file(self) -> None:
        theme = _theme(self.root, {"windows": ["playfield", "topper"]})
        config = ConfigParser()
        config.read_dict({"Settings": {"theme": "a-theme"}})

        windows = theme_windows.declared_windows(theme, 2)

        self.assertIn("index_topper.html", theme_api.get_theme_index_page(config, windows[1]))


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
