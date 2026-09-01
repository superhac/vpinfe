"""The built-in views, and the vocabulary they share with the workbench."""

import unittest

from hubui import data, game_tables, games


class BuiltinViewTests(unittest.TestCase):
    def test_every_view_names_columns_that_exist(self) -> None:
        """`apply` falls back to every column when a view's fields all miss, so a
        typo in a preset reads as "same as All" rather than as an error."""
        for label, presets, columns in (
            ("games", games.GAME_VIEWS, games.COLUMNS),
            ("tables", games.TABLE_VIEWS, games.TABLE_COLUMNS),
        ):
            known = {definition["field"] for definition in columns}
            for name, fields in presets.items():
                # Media and Assets are filled at render time from what the library
                # reports it holds, so an empty preset here is the declaration.
                if not fields:
                    continue
                with self.subTest(grid=label, view=name):
                    self.assertEqual(sorted(set(fields) - known), [])

    def test_a_view_is_named_for_the_group_it_matches(self) -> None:
        """Section 14.1. The views read the constants rather than repeating them;
        this says which are load-bearing, so renaming one fails here first."""
        self.assertIn(game_tables.MACHINE, games.GAME_VIEWS)
        for group in (game_tables.FILE, game_tables.LAUNCH, game_tables.FEATURES):
            self.assertIn(group, games.TABLE_VIEWS)


class GameRowTests(unittest.TestCase):
    def test_a_game_row_carries_no_table_level_facts(self) -> None:
        """Both were the default table's reported as the game's - a game with two
        builds declaring different roms has no single rom. Section 14.2a."""
        library = data.Library.__new__(data.Library)
        library.games = [{"id": "g1", "name": "A", "rom": "afm_113b",
                          "version": "1.2", "table_count": 1}]
        library.media = {}

        row = library.game_rows()[0]

        self.assertNotIn("rom", row)
        self.assertNotIn("version", row)
