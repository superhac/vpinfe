"""The library checks, and the roll-up a rom check needs.

`rom_installed` is three-valued and the distinction is the whole point: PinMAME's audit
answers False, the name match alone answers None, and a table declaring no rom answers
None as well. Only False is a fault. Anything looser reports a library as broken on any
machine where the audit cannot run, which is every machine without VPX configured.
"""

from __future__ import annotations

import unittest

from console import data, sections


class FakeLibrary:
    """Just enough of Library for the checks: games, their media, and the flat lens."""

    def __init__(self, games, rows, media=None, hidden=()):
        self.games = games
        self.media = media or {g["id"]: {} for g in games}
        self._rows = rows
        self._hidden = set(hidden)

    def table_rows(self):
        return self._rows

    def hidden_checks(self):
        return self._hidden


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

    def test_a_check_the_library_keeps_quiet_is_not_run(self):
        lib = FakeLibrary([game("g1")], [table("g1", False)], hidden=["rom_missing"])
        self.assertNotIn("rom_missing", sections.findings(lib))

    def test_every_check_gets_the_third_argument(self):
        """The signature changed for one check; the others must still run."""
        lib = FakeLibrary([game("g1", year="")], [table("g1", True)])
        found = sections.findings(lib)
        self.assertEqual([g["id"] for g in found["no_year"]], ["g1"])


class _Client:
    def __init__(self, policy=None):
        self.policy = policy
        self.reads = {"tables": 0, "media": 0, "policy": 0}

    def games(self):
        return [game("g1"), game("g2")]

    def media(self, game_id):
        return {"wheel": {"present": False}}

    def all_tables(self, art="", game=""):
        self.reads["tables"] += 1
        return [table("g1", False)]

    def all_media(self):
        self.reads["media"] += 1
        return [{"game_id": "g1", "kind": "wheel", "present": True}]

    def library_policy(self):
        self.reads["policy"] += 1
        if self.policy is None:
            raise OSError("unreachable")
        return self.policy


class OverviewReadTests(unittest.TestCase):
    """Everything the Overview counts is read before it draws."""

    def _library(self, client):
        library = data.Library(client)
        library.games = [game("g1"), game("g2")]
        return library

    def test_it_reads_the_tables_media_and_quiet_checks(self):
        library = self._library(_Client({"hidden_checks": ["no_year"]}))
        self.assertFalse(library.has_overview())

        library.load_overview()

        self.assertTrue(library.has_overview())
        self.assertEqual({"no_year"}, library.hidden_checks())
        self.assertEqual(["g1"], [g["id"] for g in sections.findings(library)["rom_missing"]])

    def test_the_draw_reads_nothing(self):
        client = _Client({"hidden_checks": []})
        library = self._library(client)
        library.load_overview()
        before = dict(client.reads)

        sections.findings(library)

        self.assertEqual(before, client.reads)

    def test_media_an_import_emptied_is_read_again(self):
        client = _Client({})
        library = self._library(client)
        library.load_overview()
        library.refresh_after_import()

        self.assertFalse(library.has_overview())
        library.load_overview()
        self.assertTrue(library.media["g1"]["wheel"]["present"])

    def test_one_game_the_panel_read_does_not_stand_for_the_library(self):
        client = _Client({})
        library = self._library(client)
        library.load_overview()
        library.refresh_after_import()
        library.media_for("g2", None)

        self.assertFalse(library.has_overview())
        library.load_overview()
        self.assertEqual(["g1", "g2"], sorted(library.media))
        self.assertFalse(library.media["g2"]["wheel"]["present"])

    def test_an_unreadable_policy_reports_every_check(self):
        library = self._library(_Client(None))
        library.load_overview()
        self.assertEqual(set(), library.hidden_checks())


if __name__ == "__main__":
    unittest.main()
