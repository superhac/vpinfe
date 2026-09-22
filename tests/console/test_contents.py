"""Every collection's contents in one grid, and what a row does when it is taken out or
put back."""

from __future__ import annotations

import unittest

from console import contents, page, workbench
from console.workbench import member_act


def _member(origin: str, game: str = "afm", ref: str = "", table: dict | None = None,
            name: str = "Attack from Mars") -> dict:
    return {"game": game, "name": name, "origin": origin, "ref_table": ref,
            "tables": [table] if table else []}


_AFM = {"id": "a1", "version": "1.2", "authors": ["VPW"], "origin": "default"}


class TheGrid(unittest.TestCase):
    def _rows(self, *members: dict) -> list[dict]:
        return contents.rows([({"name": "Friday Night"}, {"members": list(members)})])

    def test_each_row_says_how_the_game_is_there(self) -> None:
        found = self._rows(_member("named", table=_AFM), _member("filter", game="mm",
                                                                table=_AFM),
                           _member("excluded", game="taf", table=_AFM))

        self.assertEqual([contents.ADDED, contents.MATCHED, contents.EXCLUDED],
                         [row["status"] for row in found])

    def test_a_table_shows_only_where_the_collection_names_one(self) -> None:
        named = dict(_AFM, origin="named")
        found = self._rows(_member("named", table=_AFM),
                           _member("named", ref="a1", table=named))

        self.assertEqual(["", "1.2 · VPW"], [row["table"] for row in found])

    def test_a_game_this_library_lost_is_missing_and_named_by_its_id(self) -> None:
        (row,) = self._rows(_member("missing", game="gone", name=""))

        self.assertEqual((contents.MISSING, "gone"), (row["status"], row["game"]))

    def test_a_named_table_that_is_gone_is_missing(self) -> None:
        (row,) = self._rows(_member("named", ref="old",
                                    table={"id": "old", "origin": "missing"}))

        self.assertEqual((contents.MISSING, ""), (row["status"], row["table"]))

    def test_one_game_in_one_collection_twice_is_two_rows(self) -> None:
        found = self._rows(_member("named", table=_AFM),
                           _member("named", ref="a2", table=dict(_AFM, id="a2")),
                           _member("excluded", table=_AFM))

        self.assertEqual(3, len({row["id"] for row in found}))


class ThePanelFollowsTheRow(unittest.TestCase):
    def test_it_finds_the_row_it_was_opened_on(self) -> None:
        member = _member("filter", table=_AFM)
        wanted = contents.row_id("Friday Night", member)

        self.assertIs(member, contents.find("Friday Night", {"members": [member]}, wanted))

    def test_after_an_act_it_finds_the_same_game_in_its_new_state(self) -> None:
        wanted = contents.row_id("Friday Night", _member("filter", table=_AFM))
        now = _member("excluded", table=_AFM)

        self.assertIs(now, contents.find("Friday Night", {"members": [now]}, wanted))

    def test_a_row_that_has_gone_is_not_found(self) -> None:
        wanted = contents.row_id("Friday Night", _member("named", table=_AFM))

        self.assertIsNone(contents.find("Friday Night", {"members": []}, wanted))


class WhereItLives(unittest.TestCase):
    def test_it_sits_under_collections_in_the_nav(self) -> None:
        library = next(items for parent, items in page.NAV_GROUPS if parent is not None)
        keys = [item[0] for item in library]

        self.assertEqual(keys.index("collections") + 1, keys.index("contents"))
        self.assertIn("contents", page.NAV_UNDER)

    def test_its_panel_is_details_alone(self) -> None:
        self.assertEqual(["contents_details"],
                         [item.key for item in workbench.sections_for("contents")])


class _Library:
    def remove_from_collection(self, *_args: object) -> None: ...

    def exclude_from_collection(self, *_args: object) -> None: ...

    def unexclude_from_collection(self, *_args: object) -> None: ...


class TakingARowOut(unittest.TestCase):
    def setUp(self) -> None:
        self.library = _Library()

    def test_a_matched_row_keeps_the_whole_game_out(self) -> None:
        what, table = member_act(self.library, {"origin": "filter", "ref_table": "",
                                                "tables": [{"id": "t1"}]})

        self.assertEqual((self.library.exclude_from_collection, ""), (what, table))

    def test_an_added_row_removes_the_ref_it_is(self) -> None:
        what, table = member_act(self.library, {"origin": "named", "ref_table": "t2",
                                                "tables": [{"id": "t2"}]})

        self.assertEqual((self.library.remove_from_collection, "t2"), (what, table))

    def test_a_row_following_the_default_is_the_ref_naming_no_table(self) -> None:
        _, table = member_act(self.library, {"origin": "named", "ref_table": "",
                                             "tables": [{"id": "t1"}]})

        self.assertEqual("", table)

    def test_an_excluded_row_is_put_back(self) -> None:
        what, table = member_act(self.library, {"origin": "excluded", "ref_table": "",
                                                "tables": [{"id": "t1"}]})

        self.assertEqual((self.library.unexclude_from_collection, ""), (what, table))


if __name__ == "__main__":
    unittest.main()
