"""What a Match group says when there is no record to draw."""

from __future__ import annotations

import unittest

from console.workbench import game_match_gap, release_match_gap


class AGame(unittest.TestCase):
    def test_an_id_the_catalog_lacks_is_not_in_vps(self) -> None:
        said, level, _ = game_match_gap("SHAREDID", declared=False, held=True)
        self.assertEqual(("console.workbench.not_in_vps", "warn"), (said, level))

    def test_with_no_catalog_the_match_is_unknown_rather_than_wrong(self) -> None:
        said, level, why = game_match_gap("abc", declared=False, held=False)
        self.assertEqual(("word.unknown", "unknown"), (said, level))
        self.assertEqual("console.workbench.vps_not_downloaded", why)

    def test_no_id_is_not_matched_whether_or_not_there_is_a_catalog(self) -> None:
        for held in (True, False):
            self.assertEqual("console.workbench.not_matched",
                             game_match_gap("", declared=False, held=held)[0])

    def test_a_declared_none_is_quiet(self) -> None:
        self.assertEqual("off", game_match_gap("", declared=True, held=True)[1])


class ATable(unittest.TestCase):
    def test_nothing_recorded_is_quiet(self) -> None:
        self.assertEqual(("console.workbench.not_matched", "off", ""),
                         release_match_gap("entry", "", held=True))

    def test_an_unmatched_game_says_which_comes_first(self) -> None:
        self.assertEqual("console.workbench.match_game_vps_first",
                         release_match_gap("", "", held=True)[2])

    def test_a_release_the_catalog_lacks_is_not_in_vps(self) -> None:
        self.assertEqual("console.workbench.not_in_vps",
                         release_match_gap("entry", "gone", held=True)[0])

    def test_with_no_catalog_the_release_is_unknown(self) -> None:
        self.assertEqual("word.unknown", release_match_gap("entry", "x", held=False)[0])


if __name__ == "__main__":
    unittest.main()
