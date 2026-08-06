"""Refreshing one game reads one folder.

Setting a rating, importing a file or renaming a table changes one folder. Rescanning
the library to notice costs the whole library, which on a network share is minutes.
"""

from __future__ import annotations

import configparser
import json
import unittest
from pathlib import Path

from common.games.game_parser import GameParser
from tests.support.library import TempTree


def _game_folder(root: Path, name: str, rating: int = 0) -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.vpx").write_bytes(b"vpx")
    (folder / f"{name}.info").write_text(
        json.dumps({"Info": {"Title": name}, "User": {"Rating": rating},
                    "vpinfe": {"schema": 2}}), encoding="utf-8")
    return folder


class SingleGameRefreshTests(TempTree):
    def setUp(self):
        super().setUp()
        for name in ("Alpha", "Bravo", "Charlie"):
            _game_folder(self.root, name)
        config = configparser.ConfigParser()
        config.read_dict({"Settings": {"gamerootdir": str(self.root)}, "Media": {}})
        self.parser = GameParser(str(self.root), config)
        self.parser.loadGames(reload=True)

    def _rating(self, game):
        return game.meta_config.get("User", {}).get("Rating")

    def _by_name(self, name):
        return next(t for t in self.parser.getAllGames() if t.gameDirName == name)

    def test_a_changed_folder_is_picked_up(self):
        _game_folder(self.root, "Bravo", rating=5)

        self.parser.reload_game(str(self.root / "Bravo"))

        self.assertEqual(self._rating(self._by_name("Bravo")), 5)

    def test_the_rest_of_the_library_is_not_re_read(self):
        """The point of the change. Charlie is edited on disk and must stay stale,
        because refreshing Bravo has no business reading Charlie's folder."""
        _game_folder(self.root, "Charlie", rating=4)

        self.parser.reload_game(str(self.root / "Bravo"))

        self.assertEqual(self._rating(self._by_name("Charlie")), 0,
                         "refreshing one table read another one's folder")

    def test_the_game_count_does_not_drift(self):
        for _ in range(3):
            self.parser.reload_game(str(self.root / "Alpha"))

        self.assertEqual(self.parser.getGameCount(), 3)

    def test_a_folder_that_appeared_is_added(self):
        _game_folder(self.root, "Delta")

        added = self.parser.reload_game(str(self.root / "Delta"))

        self.assertIsNotNone(added)
        self.assertEqual(self.parser.getGameCount(), 4)

    def test_a_folder_that_went_away_is_dropped(self):
        for path in (self.root / "Alpha").iterdir():
            path.unlink()
        (self.root / "Alpha").rmdir()

        gone = self.parser.reload_game(str(self.root / "Alpha"))

        self.assertIsNone(gone)
        self.assertEqual(self.parser.getGameCount(), 2)
        self.assertNotIn("Alpha", [t.gameDirName for t in self.parser.getAllGames()])

    def test_a_folder_with_no_table_is_not_a_game(self):
        empty = self.root / "Empty"
        empty.mkdir()
        (empty / "readme.txt").write_text("nothing here", encoding="utf-8")

        self.assertIsNone(self.parser.reload_game(str(empty)))
        self.assertEqual(self.parser.getGameCount(), 3)

    def test_a_game_that_loses_its_info_is_reported_missing(self):
        (self.root / "Bravo" / "Bravo.info").unlink()

        self.parser.reload_game(str(self.root / "Bravo"))

        missing = [row["folder"] for row in self.parser.getMissingGames()]
        self.assertEqual(missing, ["Bravo"])

    def test_a_game_that_regains_its_info_stops_being_missing(self):
        (self.root / "Bravo" / "Bravo.info").unlink()
        self.parser.reload_game(str(self.root / "Bravo"))

        _game_folder(self.root, "Bravo", rating=2)
        self.parser.reload_game(str(self.root / "Bravo"))

        self.assertEqual(self.parser.getMissingGames(), [])


if __name__ == "__main__":
    unittest.main()
