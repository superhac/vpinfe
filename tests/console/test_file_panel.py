"""The panel a Media or Assets row opens, and the grid behind it."""

from __future__ import annotations

import unittest
from typing import Any

from console import grid, media_ownership, workbench


def _row(kind: str = "backglass", table: str = "", present: bool = True, **more: Any) -> dict:
    return {"id": f"g:{kind}:{table}:{present}", "game_id": "g", "kind": kind,
            "table": table, "present": present, **more}


class FindingTheRowAgain(unittest.TestCase):
    def test_by_id_first(self) -> None:
        wanted = _row(table="t1")

        self.assertIs(wanted, workbench._same_file([_row(), wanted], wanted))

    def test_an_address_finds_it_by_table_and_kind(self) -> None:
        held = _row(table="t1")

        self.assertIs(held, workbench._same_file([_row(), held],
                                                 {"kind": "backglass", "table": "t1"}))

    def test_a_removed_table_file_leaves_its_shared_row(self) -> None:
        shared = _row(present=False)

        self.assertIs(shared, workbench._same_file([shared], _row(table="t1")))

    def test_a_kind_the_game_no_longer_has_is_not_found(self) -> None:
        self.assertIsNone(workbench._same_file([_row(kind="wheel")], _row()))


class WhoUsesIt(unittest.TestCase):
    def test_media_says_it_by_its_tier(self) -> None:
        self.assertEqual([media_ownership.TABLE, media_ownership.GAME,
                          media_ownership.ORPHAN],
                         [workbench._file_tier({"via": via})
                          for via in ("table", "default", "orphan")])

    def test_an_asset_named_for_the_folder_that_nothing_loads_is_unused(self) -> None:
        self.assertEqual(media_ownership.UNUSED, workbench._file_tier(
            {"binding": "game", "present": True, "serves": 0}))

    def test_an_asset_says_it_by_its_binding(self) -> None:
        self.assertEqual([media_ownership.TABLE, media_ownership.GAME,
                          media_ownership.ORPHAN, media_ownership.MISSING],
                         [workbench._file_tier(one) for one in (
                             {"binding": "table", "present": True},
                             {"binding": "game", "present": True, "serves": 2},
                             {"binding": "orphaned", "present": True},
                             {"binding": "none", "present": False})])


class TheLineUnderIt(unittest.TestCase):
    def test_a_folder_counts_its_files(self) -> None:
        said = workbench._asset_spec({"folder": True, "files": 12, "size_bytes": 2048})

        self.assertTrue(said.startswith("12 files"), said)

    def test_a_file_says_its_format(self) -> None:
        self.assertTrue(workbench._asset_spec({"format": "VBS", "size_bytes": 41})
                        .startswith("VBS"))


class ItsOwnRail(unittest.TestCase):
    def test_a_file_is_answered_by_file_alone(self) -> None:
        for subject in ("media_file", "asset_file"):
            with self.subTest(subject=subject):
                self.assertEqual([subject], [item.key
                                             for item in workbench.sections_for(subject)])


class _Grid:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    def run_grid_method(self, *args: Any) -> None:
        self.sent.append(args)


class OneGamesRowsPutRight(unittest.TestCase):
    def test_what_stayed_updates_what_is_new_adds_and_what_went_goes(self) -> None:
        held = [{"id": "a:1", "game_id": "a"}, {"id": "a:2", "game_id": "a"},
                {"id": "b:1", "game_id": "b"}]
        by_id = {row["id"]: row for row in held}
        table = _Grid()

        grid.replace_rows(table, held, by_id, [{"id": "a:1", "game_id": "a", "x": 1},
                                               {"id": "a:3", "game_id": "a"}],
                          lambda row: row["game_id"] == "a")

        (method, change), = table.sent
        self.assertEqual(("applyTransaction", [{"id": "a:2"}], ["a:1"], ["a:3"]),
                         (method, change["remove"], [r["id"] for r in change["update"]],
                          [r["id"] for r in change["add"]]))
        self.assertEqual({"a:1", "a:3", "b:1"}, set(by_id))
        self.assertEqual(3, len(held))


if __name__ == "__main__":
    unittest.main()
