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


if __name__ == "__main__":
    unittest.main()
