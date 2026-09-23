"""A table VPS lists a newer version of, on the Tables page."""

from __future__ import annotations

import unittest

from console import games, views


class TableUpdateTests(unittest.TestCase):
    def _row(self, **wire) -> dict:
        return games.table_rows([{"id": "t1", "game": "A", **wire}])[0]

    def test_a_newer_release_reads_newer_beside_the_version_vps_lists(self) -> None:
        row = self._row(version="1.0", update_available=True,
                        source={"vps_file_id": "release01", "version": "1.2"})

        self.assertEqual(("1.2", games._NEWER), (row["on_vps"], row["update"]))

    def test_nothing_known_reads_blank(self) -> None:
        for known in (False, None):
            with self.subTest(known=known):
                self.assertEqual("", self._row(update_available=known)["update"])

    def test_the_updates_view_holds_only_those_rows(self) -> None:
        view = next(view for view in views.builtins(games.TABLE_VIEWS)
                    if view.name == "Updates")
        column = next(definition for definition in games.TABLE_COLUMNS
                      if definition["field"] == "update")

        self.assertEqual({"update": {"values": [games._NEWER]}}, view.filters)
        self.assertIn(games._NEWER, [choice["value"]
                                     for choice in column["filterParams"]["choices"]])


if __name__ == "__main__":
    unittest.main()
