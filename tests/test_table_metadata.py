import unittest

from common.tables.game_metadata import as_string_list


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


if __name__ == "__main__":
    unittest.main()
