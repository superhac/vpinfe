import unittest
from types import SimpleNamespace
from unittest import mock

from common.games import game_metadata as gm
from common.games.game_metadata import (
    as_string_list,
    game_themes,
    game_title,
    game_type,
)


class AsStringListTests(unittest.TestCase):
    def test_a_list_comes_back_as_a_list_of_strings(self) -> None:
        self.assertEqual(as_string_list(["Fantasy", "Magic"]), ["Fantasy", "Magic"])
        self.assertEqual(as_string_list(("Fantasy",)), ["Fantasy"])

    def test_absent_means_empty(self) -> None:
        for value in ([], "", None):
            with self.subTest(value=value):
                self.assertEqual(as_string_list(value), [])

    def test_a_scalar_becomes_one_item(self) -> None:
        self.assertEqual(as_string_list("Fantasy"), ["Fantasy"])
        self.assertEqual(as_string_list(1990), ["1990"])

    def test_a_stringified_list_stays_one_item(self) -> None:
        """Parsing it back would mean inventing a syntax .info does not have, so the
        odd value stays visible rather than being guessed at."""
        self.assertEqual(as_string_list("['Fantasy', 'Magic']"), ["['Fantasy', 'Magic']"])



class LegacyMetadataFieldTests(unittest.TestCase):
    def test_metadata_display_helpers_handle_legacy_fields(self) -> None:
        game = SimpleNamespace(
            gameDirName="Fallback",
            meta_config={
                "VPSdb": {
                    "name": "Legacy Name",
                    "theme": "['Music', 'Movies']",
                    "type": "SS",
                }
            },
        )

        self.assertEqual(game_title(game), "Legacy Name")
        self.assertEqual(game_themes(game), ["Music", "Movies"])
        self.assertEqual(game_type(game), "SS")

if __name__ == "__main__":
    unittest.main()


class FavoriteTests(unittest.TestCase):
    """A real boolean, and a producer at last."""

    def test_it_is_written_as_a_boolean(self) -> None:
        """The .info is JSON and the vpinfe block beside this one already stores real
        booleans; `Favorite: 0` was an INI-era habit carried into a format that has
        true. Nothing had ever written a non-zero, so no value on disk is at risk."""
        written = {}
        game = SimpleNamespace(meta_config={"User": {"Favorite": 0}})

        with mock.patch.object(gm, "load_game_meta", return_value=game.meta_config), \
             mock.patch.object(gm, "persist_game_meta",
                               side_effect=lambda g, c: written.update(c)):
            stored = gm.set_game_favorite(game, True)

        self.assertIs(stored, True)
        self.assertIs(written["User"]["Favorite"], True)

    def test_an_old_zero_still_reads_false(self) -> None:
        """Every .info in the world holds 0, because the zero-fill was the only writer
        there has ever been. The reader coerces, so they do not need migrating."""
        self.assertIs(gm.play_record({"User": {"Favorite": 0}})["favorite"], False)
        self.assertIs(gm.play_record({"User": {"Favorite": 1}})["favorite"], True)
        self.assertIs(gm.play_record({"User": {"Favorite": True}})["favorite"], True)


class ThemeListTests(unittest.TestCase):
    """However a writer wrote them down, they come back as themes."""

    def test_a_repr_in_our_own_field_stays_visible(self) -> None:
        """`Info.Themes` is ours and is a JSON list, so a repr string there is a bad
        value rather than a format. `as_string_list` decided that deliberately - parsing
        it would mean inventing a syntax the file does not have - so the odd value shows
        as it is, and the .info is what gets fixed."""
        game = SimpleNamespace(
            meta_config={"Info": {"Themes": "['Fantasy', 'Magic']"}})

        self.assertEqual(gm.game_themes(game), ["['Fantasy', 'Magic']"])

    def test_the_legacy_field_reads_the_same_way(self) -> None:
        game = SimpleNamespace(meta_config={"VPSdb": {"theme": "['Space']"}})

        self.assertEqual(gm.game_themes(game), ["Space"])

    def test_a_plain_string_is_one_theme(self) -> None:
        game = SimpleNamespace(meta_config={"Info": {"Themes": "Fantasy"}})

        self.assertEqual(gm.game_themes(game), ["Fantasy"])

    def test_something_that_only_looks_like_a_list_is_left_alone(self) -> None:
        """Inventing a parse for it would be worse than showing what is there."""
        game = SimpleNamespace(meta_config={"Info": {"Themes": "[broken"}})

        self.assertEqual(gm.game_themes(game), ["[broken"])
