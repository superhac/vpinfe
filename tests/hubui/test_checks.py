"""The library checks, and the roll-up a rom check needs.

`rom_installed` is three-valued and the distinction is the whole point: PinMAME's audit
answers False, the name match alone answers None, and a table declaring no rom answers
None as well. Only False is a fault. Anything looser reports a library as broken on any
machine where the audit cannot run, which is every machine without VPX configured.
"""

from __future__ import annotations

import unittest

from hubui import sections


class FakeLibrary:
    """Just enough of Library for the checks: games, their media, and the flat lens."""

    def __init__(self, games, rows, media=None):
        self.games = games
        self.media = media or {g["id"]: {} for g in games}
        self._rows = rows

    def table_rows(self):
        return self._rows


def game(game_id, **rest):
    return {"id": game_id, "name": game_id, "year": "1992", **rest}


def table(game_id, rom_installed, rom="afm_113b"):
    return {"game_id": game_id, "rom": rom, "rom_installed": rom_installed}


class RollupTests(unittest.TestCase):
    def test_audit_says_missing_is_a_fault(self):
        lib = FakeLibrary([game("g1")], [table("g1", False)])
        self.assertTrue(sections.rollups(lib)["g1"]["rom_missing"])

    def test_installed_is_not_a_fault(self):
        lib = FakeLibrary([game("g1")], [table("g1", True)])
        self.assertFalse(sections.rollups(lib)["g1"]["rom_missing"])

    def test_unknown_is_not_a_fault(self):
        """None is "we could not tell" - the audit needs a VPX binary. Reporting it as
        missing would call every table broken on a machine that has none."""
        lib = FakeLibrary([game("g1")], [table("g1", None)])
        self.assertFalse(sections.rollups(lib)["g1"]["rom_missing"])

    def test_no_rom_declared_is_not_a_fault(self):
        lib = FakeLibrary([game("g1")], [table("g1", None, rom="")])
        self.assertFalse(sections.rollups(lib)["g1"]["rom_missing"])

    def test_one_bad_table_flags_the_game(self):
        """A folder holds several builds and they can declare different roms. The game
        reads as missing when any one of them is."""
        lib = FakeLibrary([game("g1")],
                          [table("g1", True), table("g1", False), table("g1", None)])
        self.assertTrue(sections.rollups(lib)["g1"]["rom_missing"])

    def test_games_do_not_leak_into_each_other(self):
        lib = FakeLibrary([game("g1"), game("g2")],
                          [table("g1", False), table("g2", True)])
        rolled = sections.rollups(lib)
        self.assertTrue(rolled["g1"]["rom_missing"])
        self.assertFalse(rolled["g2"]["rom_missing"])


class FindingsTests(unittest.TestCase):
    def test_the_check_reports_the_game(self):
        lib = FakeLibrary([game("g1")], [table("g1", False)])
        found = sections.findings(lib)
        self.assertEqual([g["id"] for g in found["rom_missing"]], ["g1"])

    def test_a_game_with_no_tables_is_not_flagged(self):
        """`rollups` never saw it, so the check reads an empty dict rather than raising."""
        lib = FakeLibrary([game("g1")], [])
        self.assertEqual(sections.findings(lib)["rom_missing"], [])

    def test_every_check_gets_the_third_argument(self):
        """The signature changed for one check; the others must still run."""
        lib = FakeLibrary([game("g1", year="")], [table("g1", True)])
        found = sections.findings(lib)
        self.assertEqual([g["id"] for g in found["no_year"]], ["g1"])


if __name__ == "__main__":
    unittest.main()
