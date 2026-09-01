"""The built-in views, and the vocabulary they share with the workbench."""

import unittest

from hubui import data, game_tables, games, media_ownership, workbench


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


class AssetSectionTests(unittest.TestCase):
    """The Assets section: what it counts, and the one kind that takes no tier."""

    def _context(self, resolved, folder):
        return {"game": {"assets": folder}, "lens": "t1",
                "tables": [{"id": "t1", "assets": resolved}]}

    def test_the_count_matches_the_rows_drawn(self) -> None:
        """The folder reports a backglass the table resolves too, and the body skips
        what the table already answered - so counting both said four over two rows."""
        label = workbench._assets_label(self._context(
            {"backglass": {"resolution": "dedicated"},
             "ini": {"resolution": "shared"},
             "script": {"resolution": "none"}},
            {"backglass": {"present": True}, "ini": {"present": True},
             "music": {"present": True}, "pup_pack": {"present": False}}))

        self.assertEqual(label, "Assets (3)")

    def test_nothing_here_says_so_without_a_number(self) -> None:
        label = workbench._assets_label(self._context(
            {"backglass": {"resolution": "none"}}, {"music": {"present": False}}))

        self.assertEqual(label, "Assets")

    def test_a_script_inside_the_vpx_is_not_missing(self) -> None:
        """The ordinary table runs the script in its own .vpx. Reading the resolver's
        `none` through the media tiers would render that as Missing and call every one
        of them broken, which is why the script keeps SCRIPT_WORDS."""
        internal = game_tables.word_for(game_tables.SCRIPT_WORDS, False)

        self.assertEqual(internal, "Internal")
        self.assertNotEqual(internal, media_ownership.for_resolution("none").noun)

    def test_a_resolution_maps_onto_the_tier_that_means_it(self) -> None:
        for resolution, noun in (("dedicated", "This table"), ("shared", "All tables"),
                                 ("none", "Missing"), (None, "Missing")):
            with self.subTest(resolution=resolution):
                self.assertEqual(media_ownership.for_resolution(resolution).noun, noun)
