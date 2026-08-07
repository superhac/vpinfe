"""Reading a library folder: what the parser hands back, and what it notices on disk."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from common.games.game_parser import GameParser
from common.games.game_repository import game_to_row
from common.games.standalone_scripts import StandaloneScripts
from tests.support.library import TempTree, write_game


class GameParserTests(unittest.TestCase):
    def test_game_parser_accessors_return_copies(self) -> None:
        parser = GameParser.__new__(GameParser)
        parser.games = [SimpleNamespace(name="one")]
        parser.missing_games = [{"folder": "missing"}]

        games = parser.getAllGames()
        missing = parser.getMissingGames()
        games.clear()
        missing[0]["folder"] = "changed"

        self.assertEqual(len(parser.games), 1)
        self.assertEqual(parser.missing_games[0]["folder"], "missing")

    def test_tableparser_detects_directb2s_case_insensitively(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with_b2s = root / "With B2S (Bally 1990)"
            with_b2s.mkdir()
            (with_b2s / "With B2S (Bally 1990).vpx").write_text("")
            (with_b2s / "With B2S (Bally 1990).DirectB2S").write_text("")

            without_b2s = root / "No B2S (Bally 1991)"
            without_b2s.mkdir()
            (without_b2s / "No B2S (Bally 1991).vpx").write_text("")

            parser = GameParser(root)
            by_name = {t.gameDirName: t for t in parser.getAllGames()}

            self.assertTrue(by_name["With B2S (Bally 1990)"].b2sExists)
            self.assertFalse(by_name["No B2S (Bally 1991)"].b2sExists)

            # game_to_row mirrors the flag for the UI
            self.assertTrue(game_to_row(by_name["With B2S (Bally 1990)"])["b2s_exists"])
            self.assertFalse(game_to_row(by_name["No B2S (Bally 1991)"])["b2s_exists"])

    def test_standalone_scripts_can_be_constructed_without_running_network_work(self) -> None:
        with mock.patch(
                "common.games.standalone_scripts.StandaloneScripts.apply_patches") as apply_patches:
            scripts = StandaloneScripts([], auto_run=False)

        self.assertIsNone(scripts.hashes)
        apply_patches.assert_not_called()


class ParallelScanTests(TempTree):
    """The scan reads folders in parallel, and must not become a race.

    Reading a folder is almost entirely waiting - on the network share a real library
    lives on, directory listings were 6.5s of a 7.4s scan - so threads cover the wait.
    What they must not change is the answer: the library is sorted, and a scan whose
    order depended on which network read returned first would make the wheel's order a
    race, and put a folder's problems in another folder's report.
    """

    def _library(self, count: int):
        for i in range(count):
            write_game(self.root, f"Game {i:03}", info={"Info": {"Name": f"Game {i:03}"}})
        return GameParser(str(self.root))

    def test_the_order_is_the_sorted_order_not_the_finishing_order(self) -> None:
        parser = self._library(40)
        names = [g.gameDirName for g in parser.getAllGames()]
        self.assertEqual(names, sorted(names))

    def test_the_same_library_scans_the_same_way_every_time(self) -> None:
        self._library(40)
        runs = {tuple(g.gameDirName for g in GameParser(str(self.root)).getAllGames())
                for _ in range(5)}
        self.assertEqual(len(runs), 1, "the scan is not deterministic")

    def test_a_small_library_skips_the_pool_and_agrees_with_it(self) -> None:
        """Below the threshold the pool costs more than it saves, so it is not used -
        and the two paths must not disagree about what they found."""
        from common.games import game_parser

        self._library(4)
        serial = [g.gameDirName for g in GameParser(str(self.root)).getAllGames()]
        original = game_parser._PARALLEL_SCAN_THRESHOLD
        game_parser._PARALLEL_SCAN_THRESHOLD = 1
        try:
            parallel = [g.gameDirName for g in GameParser(str(self.root)).getAllGames()]
        finally:
            game_parser._PARALLEL_SCAN_THRESHOLD = original
        self.assertEqual(serial, parallel)

    def test_a_folders_problems_are_reported_against_that_folder(self) -> None:
        """Two threads appending to one list is how this would go wrong quietly."""
        for i in range(20):
            write_game(self.root, f"Fine {i:03}", info={"Info": {"Name": f"Fine {i:03}"}})
        for i in range(6):
            write_game(self.root, f"NoInfo {i:03}")

        parser = GameParser(str(self.root))
        missing = {row["folder"] for row in parser.missing_games}

        self.assertEqual(len(missing), 6, parser.missing_games)
        self.assertTrue(all(name.startswith("NoInfo") for name in missing), missing)
        for row in parser.missing_games:
            self.assertTrue(row["path"].endswith(row["folder"]),
                            f"{row['folder']} reported against {row['path']}")


if __name__ == "__main__":
    unittest.main()
