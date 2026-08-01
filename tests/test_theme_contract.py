"""The versioned surface themes are written against.

A theme declares what it was built for; the payload is built in the current shape and
projected back. The point of the levels is that a theme never has to guess.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from frontend.theme_contract import (
    CURRENT_CONTRACT,
    OLDEST_CONTRACT,
    declared_contract,
    project,
)

ROW = {
    "gameDirName": "Example",
    "WheelImagePath": "/t/wheel.png",
    "meta": {
        "Info": {"Title": "Example", "VPSId": "vps-1"},
        "User": {"Rating": 4},
        "vpinfe": {"schema": 2, "id": "tuF3WogthK", "alt_title": "Alt"},
        "tables": {"E.vpx": {"rom": "afm_113b", "authors": ["jpsalas"]}},
        "assets": {"medias/bg.png": {"source": {"host": "user"}}},
    },
    "pupPackExists": True,
    "altSoundExists": False,
    "altColorExists": False,
}


class DeclarationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.theme = Path(self._tmp.name) / "MyTheme"
        self.theme.mkdir()

    def _manifest(self, body):
        (self.theme / "manifest.json").write_text(json.dumps(body), encoding="utf-8")

    def test_a_theme_that_says_nothing_gets_the_oldest_contract(self):
        """Every theme written before this existed, which is all of them."""
        self._manifest({"name": "MyTheme", "version": "1.0"})

        self.assertEqual(declared_contract(self.theme), OLDEST_CONTRACT)

    def test_a_theme_gets_what_it_declares(self):
        self._manifest({"name": "MyTheme", "contract": 2})

        self.assertEqual(declared_contract(self.theme), 2)

    def test_a_theme_from_the_future_is_served_what_we_have(self):
        """Refusing to draw anything would be worse than drawing most of it."""
        self._manifest({"name": "MyTheme", "contract": CURRENT_CONTRACT + 5})

        with self.assertLogs("vpinfe.frontend.theme_contract", level="WARNING"):
            self.assertEqual(declared_contract(self.theme), CURRENT_CONTRACT)

    def test_a_manifest_we_cannot_read_is_not_fatal(self):
        for body in ("{ not json", '{"contract": "two"}', '{"contract": null}'):
            with self.subTest(body=body):
                (self.theme / "manifest.json").write_text(body, encoding="utf-8")
                self.assertEqual(declared_contract(self.theme), OLDEST_CONTRACT)

    def test_a_missing_manifest_is_not_fatal(self):
        self.assertEqual(declared_contract(self.theme), OLDEST_CONTRACT)


class ProjectionTests(unittest.TestCase):
    def test_the_current_contract_is_handed_the_payload_as_built(self):
        self.assertIs(project(ROW, CURRENT_CONTRACT), ROW)

    def test_contract_1_reads_the_shape_it_was_written_against(self):
        """VPXFile is synthesised from the default game file - the payload itself has
        not carried that section since the .info stopped having one."""
        meta = project(ROW, 1)["meta"]

        self.assertEqual(meta["VPXFile"]["filename"], "E.vpx")
        self.assertEqual(meta["VPXFile"]["rom"], "afm_113b")
        self.assertEqual(meta["Info"]["Rom"], "afm_113b")
        self.assertEqual(meta["Info"]["Authors"], ["jpsalas"])
        self.assertEqual(meta["VPinFE"]["alt_title"], "Alt")

    def test_contract_1_keeps_the_old_spelling_of_the_detect_flags(self):
        row = {**ROW, "meta": {**ROW["meta"],
                               "tables": {"E.vpx": {"detect_ssf": True,
                                                        "detect_scorbit": True}}}}

        vpx = project(row, 1)["meta"]["VPXFile"]

        self.assertTrue(vpx["detectssf"])
        self.assertTrue(vpx["detectscorebit"], "the old name kept its typo on the wire")
        self.assertNotIn("detect_ssf", vpx)

    def test_a_detect_flag_written_as_a_string_is_still_a_boolean(self):
        """A JSON "false" is truthy to anything that reads it without care."""
        row = {**ROW, "meta": {**ROW["meta"],
                               "tables": {"E.vpx": {"detect_ssf": "false",
                                                        "detect_lut": "true"}}}}

        vpx = project(row, 1)["meta"]["VPXFile"]

        self.assertIs(vpx["detectssf"], False)
        self.assertIs(vpx["detectlut"], True)

    def test_contract_1_still_gets_the_addon_flags(self):
        vpx = project(ROW, 1)["meta"]["VPXFile"]

        self.assertTrue(vpx["pupPackExists"])
        self.assertFalse(vpx["altSoundExists"])

    def test_the_current_contract_does_not_carry_the_retired_section(self):
        self.assertNotIn("VPXFile", project(ROW, CURRENT_CONTRACT)["meta"])

    def test_contract_1_does_not_see_what_replaced_it(self):
        """Serving both shapes lets a theme work by accident against fields it never
        declared, which is the failure this exists to prevent."""
        meta = project(ROW, 1)["meta"]

        for section in ("tables", "vpinfe", "assets"):
            self.assertNotIn(section, meta, section)

    def test_projecting_does_not_touch_the_payload_it_was_given(self):
        original = json.dumps(ROW, sort_keys=True)

        project(ROW, 1)

        self.assertEqual(json.dumps(ROW, sort_keys=True), original)

    def test_the_renamed_row_keys_come_back_with_their_old_names(self):
        """PAR-22. The four keys the vocabulary rename moved are the only things
        outside meta the projection touches, and a contract 1 theme must not be able
        to tell they moved."""
        projected = project(ROW, 1)

        self.assertEqual(projected["tableDirName"], "Example")
        self.assertNotIn("gameDirName", projected,
                         "serving both spellings would let a theme work by accident")

    def test_everything_else_outside_meta_is_untouched(self):
        projected = project(ROW, 1)

        self.assertEqual(projected["WheelImagePath"], "/t/wheel.png")

    def test_a_game_with_no_table_still_projects(self):
        row = {"meta": {"Info": {"Title": "x"}, "vpinfe": {}, "tables": {}}}

        meta = project(row, 1)["meta"]

        self.assertEqual(meta["Info"]["Rom"], "")
        self.assertNotIn("tables", meta)


if __name__ == "__main__":
    unittest.main()
