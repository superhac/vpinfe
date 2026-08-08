import unittest
from types import SimpleNamespace

from common.games.game_metadata import as_string_list, game_themes, game_title, game_type


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
