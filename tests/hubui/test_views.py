"""The built-in views, and the vocabulary they share with the workbench."""

import unittest

from common.games import asset_registry
from hubui import (
    data,
    game_tables,
    games,
    media_ownership,
    workbench,
)


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


class LaunchRollupTests(unittest.TestCase):
    """One answer to "will this run", and the trap it has to avoid."""

    def test_an_em_table_declaring_no_rom_is_ready(self) -> None:
        """The trap: reading REQUIRED_KINDS as a checklist every table must satisfy
        calls every EM table broken. Required-ness is the kind's; whether it applies
        is the table's."""
        self.assertIs(asset_registry.launchable(True, False, None), True)

    def test_a_declared_rom_that_is_not_installed_blocks(self) -> None:
        self.assertIs(asset_registry.launchable(True, True, False), False)

    def test_an_unparsed_table_is_unknown_rather_than_broken(self) -> None:
        self.assertIsNone(asset_registry.launchable(True, True, None))

    def test_a_file_that_is_gone_blocks_whatever_the_rom_says(self) -> None:
        self.assertIs(asset_registry.launchable(False, True, True), False)

    def test_the_ordinary_state_is_the_quiet_one(self) -> None:
        """Notable first, like every other pair: a word on every row saying the table
        works tells a reader nothing."""
        self.assertEqual(game_tables.word_for(game_tables.LAUNCH_WORDS, True), "Blocked")
        self.assertEqual(game_tables.word_for(game_tables.LAUNCH_WORDS, False), "Ready")


class TableRowShapeTests(unittest.TestCase):
    """A grid row has to answer every column that reads it."""

    def test_a_row_carries_every_field_a_column_names(self) -> None:
        """A column whose field the row lacks renders blank and says nothing - there
        is no error to see. It happened: patching a row-menu write from the game's own
        sub-resource, which describes a table rather than where it sits in a library,
        blanked Game, Manufacturer, Year and ROM on the rows just acted on.
        """
        wire = {
            "id": "t1", "game_id": "g1", "game": "Addams Family, The",
            "manufacturer": "Bally", "year": "1992",
            "filename": "taf.vpx", "version": "2.1", "authors": ["g5k"],
            "rating": 0, "features": {}, "assets": {},
            "rom": "TAF_L7", "rom_installed": True, "launchable": True,
            "default": True, "default_kind": "user", "hidden": False,
            "available": True, "absent_since": None, "app": "vpx",
        }

        row = games.table_rows([wire])[0]

        named = {definition["field"] for definition in games.TABLE_COLUMNS}
        self.assertEqual(sorted(named - set(row)), [])


class PlayGroupTests(unittest.TestCase):
    """The play record, in the units somebody reads it in."""

    def test_play_time_uses_the_largest_unit_that_is_still_true(self) -> None:
        """41,400 seconds is not a length anybody pictures."""
        cases = [(0, "None"), (45, "45 sec"), (1020, "17 min"), (5340, "89 min"),
                 (5400, "1 hr 30 min"), (7200, "2 hr")]
        for seconds, said in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(workbench._played_for(seconds), said)

    def test_never_played_says_so_rather_than_showing_nothing(self) -> None:
        """An empty cell is not a state. Section 8: a value is a name or a state."""
        self.assertEqual(workbench._played_when(None), "Never")
        self.assertEqual(workbench._played_when(""), "Never")
        self.assertEqual(workbench._played_when("not a date"), "Never")

    def test_reset_is_offered_only_where_there_is_something_to_clear(self) -> None:
        """An act offered on a record of nothing is a button that cannot do anything."""
        nothing = {"last_played": None, "play_count": 0, "play_time_seconds": 0}
        played = {"last_played": None, "play_count": 3, "play_time_seconds": 0}
        noop = lambda *a: None  # noqa: E731

        def labels(record):
            return [row[0] for row in workbench._play_rows(
                {}, record, rating=0, on_rate=noop, on_reset=noop)]

        self.assertNotIn(workbench.FULL, labels(nothing))
        self.assertIn(workbench.FULL, labels(played))
