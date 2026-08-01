"""Refreshing one table reads one folder.

Setting a rating, importing a file or renaming a table changes one folder. Rescanning
the library to notice costs the whole library, which on a network share is minutes.
"""

from __future__ import annotations

import configparser
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.tables.tableparser import TableParser


def _table_folder(root: Path, name: str, rating: int = 0) -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.vpx").write_bytes(b"vpx")
    (folder / f"{name}.info").write_text(
        json.dumps({"Info": {"Title": name}, "User": {"Rating": rating},
                    "vpinfe": {"schema": 2}}), encoding="utf-8")
    return folder


class SingleTableRefreshTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for name in ("Alpha", "Bravo", "Charlie"):
            _table_folder(self.root, name)
        config = configparser.ConfigParser()
        config.read_dict({"Settings": {"tablerootdir": str(self.root)}, "Media": {}})
        self.parser = TableParser(str(self.root), config)
        self.parser.loadTables(reload=True)

    def _rating(self, game):
        return game.metaConfig.get("User", {}).get("Rating")

    def _by_name(self, name):
        return next(t for t in self.parser.getAllTables() if t.tableDirName == name)

    def test_a_changed_folder_is_picked_up(self):
        _table_folder(self.root, "Bravo", rating=5)

        self.parser.reload_table(str(self.root / "Bravo"))

        self.assertEqual(self._rating(self._by_name("Bravo")), 5)

    def test_the_rest_of_the_library_is_not_re_read(self):
        """The point of the change. Charlie is edited on disk and must stay stale,
        because refreshing Bravo has no business reading Charlie's folder."""
        _table_folder(self.root, "Charlie", rating=4)

        self.parser.reload_table(str(self.root / "Bravo"))

        self.assertEqual(self._rating(self._by_name("Charlie")), 0,
                         "refreshing one table read another one's folder")

    def test_the_table_count_does_not_drift(self):
        for _ in range(3):
            self.parser.reload_table(str(self.root / "Alpha"))

        self.assertEqual(self.parser.getTableCount(), 3)

    def test_a_folder_that_appeared_is_added(self):
        _table_folder(self.root, "Delta")

        added = self.parser.reload_table(str(self.root / "Delta"))

        self.assertIsNotNone(added)
        self.assertEqual(self.parser.getTableCount(), 4)

    def test_a_folder_that_went_away_is_dropped(self):
        for path in (self.root / "Alpha").iterdir():
            path.unlink()
        (self.root / "Alpha").rmdir()

        gone = self.parser.reload_table(str(self.root / "Alpha"))

        self.assertIsNone(gone)
        self.assertEqual(self.parser.getTableCount(), 2)
        self.assertNotIn("Alpha", [t.tableDirName for t in self.parser.getAllTables()])

    def test_a_folder_with_no_game_file_is_not_a_table(self):
        empty = self.root / "Empty"
        empty.mkdir()
        (empty / "readme.txt").write_text("nothing here", encoding="utf-8")

        self.assertIsNone(self.parser.reload_table(str(empty)))
        self.assertEqual(self.parser.getTableCount(), 3)

    def test_a_table_that_loses_its_info_is_reported_missing(self):
        (self.root / "Bravo" / "Bravo.info").unlink()

        self.parser.reload_table(str(self.root / "Bravo"))

        missing = [row["folder"] for row in self.parser.getMissingTables()]
        self.assertEqual(missing, ["Bravo"])

    def test_a_table_that_regains_its_info_stops_being_missing(self):
        (self.root / "Bravo" / "Bravo.info").unlink()
        self.parser.reload_table(str(self.root / "Bravo"))

        _table_folder(self.root, "Bravo", rating=2)
        self.parser.reload_table(str(self.root / "Bravo"))

        self.assertEqual(self.parser.getMissingTables(), [])


if __name__ == "__main__":
    unittest.main()
