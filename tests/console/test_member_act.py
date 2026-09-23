"""What takes a collection's row out of it, or puts a taken-out one back."""

from __future__ import annotations

import unittest

from console.workbench import member_act


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
