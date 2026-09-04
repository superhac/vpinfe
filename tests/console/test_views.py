"""The built-in views, and the vocabulary they share with the workbench."""

import unittest

from common.games import asset_registry
from common.labels import field_label
from console import (
    data,
    game_tables,
    games,
    media_ownership,
    stars,
    table_features,
    tageditor,
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


class LabelCasingTests(unittest.TestCase):
    """One casing rule for every label the Console shows."""

    def test_acronyms_stay_acronyms(self) -> None:
        for text, said in (("vps_id", "VPS ID"), ("rom", "ROM"),
                           ("dof_event", "DOF Event"),
                           ("Clear NVRAM on exit", "Clear NVRAM on Exit")):
            with self.subTest(text=text):
                self.assertEqual(field_label(text), said)

    def test_a_small_word_stays_down_unless_it_leads_or_closes(self) -> None:
        """`AssetSpec` writes "Point of View" by hand, so a rule producing "Point Of
        View" would disagree with the registry it is the fallback for."""
        self.assertEqual(field_label("point_of_view"), "Point of View")
        self.assertEqual(field_label("Made by"), "Made By")
        self.assertEqual(field_label("of the year"), "Of the Year")

    def test_it_takes_a_key_or_a_phrase(self) -> None:
        self.assertEqual(field_label("last_played"), "Last Played")
        self.assertEqual(field_label("Last played"), "Last Played")

    def test_an_apostrophe_does_not_start_a_word(self) -> None:
        """`str.title` would give "Author'S"."""
        self.assertEqual(field_label("author's notes"), "Author's Notes")


class FeatureLegendTests(unittest.TestCase):
    """A legend names what a reader can actually see."""

    def test_a_settled_library_does_not_explain_a_mark_it_never_shows(self) -> None:
        """Measured on 166 real tables: every one of the seven displayed features is
        true or false, and every null belongs to pinmame - which this vocabulary
        leaves out on purpose. So the third line explained nothing, on every visit."""
        rows = [{"feature_ssf": True, "feature_lut": False}]

        self.assertEqual(table_features.states_in(rows), [table_features.IN_SCRIPT])

    def test_a_state_that_draws_nothing_is_not_in_the_legend(self) -> None:
        """It read as blank space with a name beside it. `media_ownership` leaves
        Missing out for the same reason - a blank cell is not something anybody looks
        up - and the binary views should not differ from the matrix they sit beside."""
        rows = [{"feature_ssf": True, "feature_lut": False}]

        self.assertNotIn(table_features.UNUSED, table_features.states_in(rows))

    def test_it_comes_back_the_moment_a_table_is_unparsed(self) -> None:
        """Reachable, not impossible: discovery leaves a table with a filename and an
        id, and parsing is a separate job because reading one is a full file read. In
        that window the flags are null, and calling that "Not used" would give an
        unparsed table a clean bill of health it has not earned."""
        rows = [{"feature_ssf": True}, {"feature_ssf": None}]

        self.assertIn(table_features.UNKNOWN, table_features.states_in(rows))

    def test_it_keeps_the_vocabulary_s_own_order(self) -> None:
        """Whatever order the rows arrive in, the legend reads the way the vocabulary
        is declared - so it does not shuffle when a library changes."""
        rows = [{"feature_ssf": None}, {"feature_lut": False}, {"feature_nfozzy": True}]

        self.assertEqual(table_features.states_in(rows),
                         [table_features.IN_SCRIPT, table_features.UNKNOWN])


class FunnelChoiceTests(unittest.TestCase):
    """A funnel offers the marks the grid actually draws."""

    def _by_label(self, choices):
        return {choice["label"]: choice for choice in choices}

    def test_missing_offers_no_mark_because_the_cell_draws_none(self) -> None:
        """The media cell holds "" for Missing and the renderer returns nothing, so a
        glyph in the funnel would promise a mark that is never on screen."""
        choices = self._by_label(games._STATE_CHOICES)

        self.assertEqual(choices["Missing"]["mark"], "")
        self.assertTrue(choices["This table"]["mark"])

    def test_every_state_is_still_offered(self) -> None:
        """Dropping the mark is not dropping the choice - Missing is the one people
        filter to most, and it stays pickable."""
        self.assertEqual({choice["label"] for choice in games._STATE_CHOICES},
                         {media_ownership.tier_for(key).noun
                          for key in media_ownership.STATES})


class StarControlTests(unittest.TestCase):
    """One control, drawn twice - so the two drawings have to agree."""

    def test_both_renderers_draw_the_same_control(self) -> None:
        """A grid cell is rendered by AG Grid in the browser and a panel row from
        elements on the server, so they cannot be one call. Everything they draw comes
        from the module's constants, which is what stops them drifting again - the clear
        had a body in one and not the other, and cleared on a different gesture."""
        js = stars.renderer("game")

        for token in (stars.BOX, stars.STAR, stars.LIT, stars.CLEAR_CLASS, stars.CLEAR):
            with self.subTest(token=token):
                self.assertIn(token, js)
        self.assertIn(f"n <= {stars.MOST}", js)

    def test_the_clear_carries_the_character(self) -> None:
        """In a tooltip it measures zero and cannot be clicked - and a scripted click
        passes on it anyway, so only an eye catches it."""
        self.assertEqual(stars.CLEAR, "×")
        self.assertIn(f">{stars.CLEAR}</span>", stars.renderer("game"))

    def test_only_a_rated_row_offers_the_clear(self) -> None:
        """Guarded in the renderer, or an unrated library is a column of dismissals."""
        self.assertIn("if (held)", stars.renderer("game"))

    def test_the_listener_reads_the_box_class(self) -> None:
        """One delegated listener for every star in the app; if the class it looks for
        drifts from the one drawn, every click stops arriving and nothing errors."""
        self.assertIn(f".{stars.BOX} [data-value]", stars.CLICK_JS)


class TagEditorTests(unittest.TestCase):
    """What the editor leads with: the spellings that are one word."""

    def _rows(self, pairs):
        return [{"tag": tag, "games": count, "same": " ".join(tag.split()).casefold()}
                for tag, count in pairs]

    def test_only_words_spelled_more_than_one_way_are_grouped(self) -> None:
        """A tag nobody has spelled twice is not something to act on, and listing it
        would bury the ones that are."""
        groups = tageditor.rows_by_key(
            self._rows([("Sci-Fi", 2), ("sci-fi", 1), ("Wide Body", 4)]))

        self.assertEqual([[r["tag"] for r in g] for g in groups], [["Sci-Fi", "sci-fi"]])

    def test_the_most_used_spelling_leads_because_it_is_the_survivor(self) -> None:
        groups = tageditor.rows_by_key(self._rows([("sci-fi", 1), ("Sci-Fi", 9)]))

        self.assertEqual(groups[0][0]["tag"], "Sci-Fi")

    def test_whitespace_alone_makes_two_spellings_one_word(self) -> None:
        groups = tageditor.rows_by_key(self._rows([("Wide Body", 1), ("wide  body", 1)]))

        self.assertEqual(len(groups), 1)
