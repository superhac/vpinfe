"""The community script fixes: what is offered, and what is left alone.

Matched on the hash of the script a table actually runs. One table's script appears
under a dozen filenames, so a fix is only ever correct for the bytes it was built
against - which is why none of this looks at a name.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.games import standalone_scripts as scripts
from console import sections

HASHES = [{"sha256": "aaa", "file": "Alpha.vbs",
           "patched": {"url": "https://example.invalid/Alpha.vbs"}}]


class MatchTests(unittest.TestCase):
    def test_a_published_fix_is_found_by_hash(self) -> None:
        self.assertEqual(scripts.match_for("aaa", HASHES), HASHES[0])

    def test_nothing_matches_a_script_nobody_published_for(self) -> None:
        self.assertIsNone(scripts.match_for("bbb", HASHES))

    def test_a_table_nothing_has_read_matches_nothing(self) -> None:
        """No hash is not the same as a hash that matches nothing, and an empty string
        must not be allowed to equal an empty field in the index."""
        self.assertIsNone(scripts.match_for("", HASHES))
        self.assertIsNone(scripts.match_for("", [{"sha256": ""}]))


class StateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vpx = Path(self.tmp.name) / "Alpha.vpx"
        self.vpx.write_bytes(b"table")

    def test_a_fix_with_no_sidecar_is_offered(self) -> None:
        self.assertEqual(scripts.state_of(str(self.vpx), "aaa", HASHES)[0],
                         scripts.OFFERED)

    def test_an_existing_sidecar_is_left_alone(self) -> None:
        """VPX runs that file in place of the script inside the .vpx, so whatever is
        there is what the table runs - and replacing it would overwrite somebody's own
        work."""
        self.vpx.with_suffix(".vbs").write_text("' mine")

        self.assertEqual(scripts.state_of(str(self.vpx), "aaa", HASHES)[0],
                         scripts.ALREADY)

    def test_nothing_published_is_its_own_answer(self) -> None:
        """Not folded in with "already patched": a surface that reported both as fine
        would say the same word for two unrelated reasons."""
        self.assertEqual(scripts.state_of(str(self.vpx), "zzz", HASHES)[0],
                         scripts.NOTHING)


class _Game:
    def __init__(self, folder: Path, vpx: Path) -> None:
        self.fullPathGame = str(folder)
        self.fullPathVPXfile = str(vpx)
        self.gameDirName = folder.name


class OfferedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _game(self, name: str, vbs_hash: str | None, sidecar: bool = False) -> _Game:
        folder = Path(self.tmp.name) / name
        folder.mkdir()
        vpx = folder / "Table.vpx"
        vpx.write_bytes(b"table")
        if sidecar:
            vpx.with_suffix(".vbs").write_text("' mine")
        entry = {"filename": "Table.vpx"}
        if vbs_hash is not None:
            entry["vbs_hash"] = vbs_hash
        (folder / f"{name}.info").write_text(json.dumps(
            {"Info": {"Name": name}, "VPinFE": {}, "User": {},
             "tables": {"Table.vpx": entry}}))
        return _Game(folder, vpx)

    def test_it_names_what_can_take_a_fix(self) -> None:
        found = scripts.offered_for([self._game("Alpha", "aaa")], HASHES)

        self.assertEqual(found["offered"], ["Alpha"])
        self.assertEqual(found["checked"], 1)
        self.assertTrue(found["reachable"])

    def test_a_table_already_running_one_is_counted_not_offered(self) -> None:
        found = scripts.offered_for(
            [self._game("Alpha", "aaa", sidecar=True)], HASHES)

        self.assertEqual(found["offered"], [])
        self.assertEqual(found["already"], 1)

    def test_a_table_nothing_has_read_is_not_counted_as_checked(self) -> None:
        """It has no script to match on, and calling it "nothing published" would be a
        statement about a file nobody has opened."""
        found = scripts.offered_for([self._game("Alpha", None)], HASHES)

        self.assertEqual(found["checked"], 0)
        self.assertEqual(found["offered"], [])

    def test_an_index_that_cannot_be_reached_is_not_an_empty_one(self) -> None:
        """Reporting it as "nothing to do" would call the library fine on the strength
        of a failed request."""
        found = scripts.offered_for([self._game("Alpha", "aaa")], [])

        self.assertFalse(found["reachable"])
        self.assertEqual(found["checked"], 0)


class WordingTests(unittest.TestCase):
    """What the Overview card says, which is the only part of this most people see."""

    def test_an_unreachable_index_says_nothing_was_checked(self) -> None:
        good, said = sections._scripts_said({"reachable": False})

        self.assertFalse(good)
        self.assertIn("could not be reached", said)

    def test_offered_tables_are_named(self) -> None:
        good, said = sections._scripts_said(
            {"reachable": True, "offered": ["Alpha", "Beta"], "checked": 9})

        self.assertFalse(good, "something to do is not a tick")
        self.assertIn("Alpha", said)
        self.assertIn("2 of 9", said)

    def test_a_long_list_is_cut_rather_than_run_on(self) -> None:
        good, said = sections._scripts_said(
            {"reachable": True, "offered": list("abcdef"), "checked": 9})

        self.assertIn("and more", said)

    def test_nothing_to_do_says_how_much_was_looked_at(self) -> None:
        """A bare "nothing to do" is indistinguishable from not having looked."""
        good, said = sections._scripts_said(
            {"reachable": True, "offered": [], "checked": 77, "already": 3})

        self.assertTrue(good)
        self.assertIn("77 checked", said)
        self.assertIn("3 already", said)
