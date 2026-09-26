"""What a Media slot's Remove says it takes, before it takes it.

Remove deletes the files at the lens's own tier: the table's, or the game's from the
game or from a table named as its folder. The confirm names the file at that tier and
who loses it, in the Assets view's words, and asks nothing where Remove takes nothing.
"""

import unittest
from typing import Any

from common.i18n import t
from console import game_tables
from console.workbench import _removal

GAME = {"folder": "/tables/Multi VPX (Original 2024)"}
TABLES = [{"id": "a1", "filename": "Multi VPX (Original 2024).vpx"},
          {"id": "b2", "filename": "Multi VPX (Original 2024) - alt.vpx"}]
OWN = {"tier": "table", "file": "(Backglass) Multi VPX (Original 2024) - alt.png"}
SHARED = {"tier": "game", "file": "(Backglass) Multi VPX (Original 2024).png"}
DEFAULT = {"tier": "default", "file": "bg.png"}

EVERY_TABLE = t("console.workbench.remove_asset.game")
FALLS_BACK = t("console.workbench.remove_asset.table")
GOES_WITHOUT = t("console.workbench.remove_asset.table_only")


def _context(lens: str) -> dict[str, Any]:
    return {"lens": lens, "tables": TABLES, "game": GAME}


class RemovalTests(unittest.TestCase):
    def test_the_game_lens_takes_the_game_file(self) -> None:
        self.assertEqual((SHARED["file"], EVERY_TABLE),
                         _removal(_context(""), [SHARED, DEFAULT], {}))

    def test_a_table_named_as_its_folder_takes_the_game_file(self) -> None:
        self.assertEqual((SHARED["file"], EVERY_TABLE),
                         _removal(_context("a1"), [SHARED], {}))

    def test_a_table_takes_its_own_file_and_falls_back(self) -> None:
        for tiers in ([OWN, SHARED], [OWN, DEFAULT]):
            with self.subTest(then=tiers[1]["tier"]):
                self.assertEqual((OWN["file"], FALLS_BACK),
                                 _removal(_context("b2"), tiers, {}))

    def test_a_table_with_nothing_behind_its_own_file_goes_without(self) -> None:
        self.assertEqual((OWN["file"], GOES_WITHOUT), _removal(_context("b2"), [OWN], {}))

    def test_nothing_at_the_lens_tier_asks_nothing(self) -> None:
        for lens, tiers in (("b2", [SHARED, DEFAULT]), ("", [DEFAULT]), ("a1", [])):
            with self.subTest(lens=lens, tiers=[one["tier"] for one in tiers]):
                self.assertIsNone(_removal(_context(lens), tiers, {}))

    def test_an_unread_detail_names_the_file_on_show(self) -> None:
        on_show = {"present": True, "via": "table", "file": OWN["file"]}

        self.assertEqual((OWN["file"], FALLS_BACK), _removal(_context("b2"), None, on_show))
        self.assertIsNone(_removal(_context("b2"), None, {**on_show, "via": "game"}))


class NamedAsFolderTests(unittest.TestCase):
    def test_the_file_named_as_the_folder_in_any_case_or_separator(self) -> None:
        for folder in ("/tables/Multi VPX (Original 2024)",
                       "C:\\Tables\\multi vpx (original 2024)\\"):
            with self.subTest(folder=folder):
                self.assertTrue(game_tables.named_as_folder(TABLES[0], {"folder": folder}))

    def test_another_file_or_none(self) -> None:
        self.assertFalse(game_tables.named_as_folder(TABLES[1], GAME))
        self.assertFalse(game_tables.named_as_folder(None, GAME))
        self.assertFalse(game_tables.named_as_folder(TABLES[0], {}))


if __name__ == "__main__":
    unittest.main()
