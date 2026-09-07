"""Visual Pinball's settings at the scope somebody is editing them.

Two layers, not three, and the table layer is one file whose name is decided by which
of two spellings exists. They do not stack, and the shadowing that follows is what the
`in_effect` flag exists to report.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from apps.vpx.config import VPXConfig
from common.apps.contract import SCOPE_ENTRY, SCOPE_FOLDER, SCOPE_LAUNCHER

APP_INI = """\
[Backglass]
; Output Mode: Where it goes [Default: 'Disabled', 0='Disabled', 1='Floating']
BackglassOutput = 1

; Grill Height: How tall [Default: 180]
GrillHeight = 180

[DMD]
; Legacy Renderer: Use the legacy renderer [Default: 1]
Profile1Legacy = 1

[Version]
; VPX Version: what wrote this [Default: '10815353']
VPinball = 10815353
"""

KEY = "Backglass.BackglassOutput"


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app_ini = self.root / "VPinballX.ini"
        self.app_ini.write_text(APP_INI)
        self.settings = {"ini_path": str(self.app_ini)}
        # A folder named for the game rather than the table, so the two spellings of the
        # table layer are genuinely different files.
        self.game = self.root / "Medieval Madness"
        self.game.mkdir()
        self.table = self.game / "MM (VPW 1.2).vpx"
        self.table.write_text("")
        self.other = self.game / "MM (VR).vpx"
        self.other.write_text("")
        self.config = VPXConfig()

    def at(self, scope: str, table=None, key: str = KEY):
        return self.config.read(scope, str(table or self.table), self.settings)[key]

    def folder_file(self, text: str) -> None:
        (self.game / "Medieval Madness.ini").write_text(text)

    def table_file(self, text: str) -> None:
        (self.game / "MM (VPW 1.2).ini").write_text(text)


class LayerTests(_Case):
    def test_with_nothing_beside_it_the_launcher_answers(self) -> None:
        found = self.at(SCOPE_ENTRY)

        self.assertEqual((found.value, found.scope), ("1", SCOPE_LAUNCHER))
        self.assertFalse(found.set_here)
        self.assertTrue(found.in_effect)

    def test_a_folder_file_reaches_the_tables_in_it(self) -> None:
        self.folder_file("[Backglass]\nBackglassOutput = 0\n")

        found = self.at(SCOPE_ENTRY)
        self.assertEqual((found.value, found.scope), ("0", SCOPE_FOLDER))
        self.assertFalse(found.set_here, "it is not set at the table")

    def test_at_its_own_scope_a_folder_value_is_set_here(self) -> None:
        self.folder_file("[Backglass]\nBackglassOutput = 0\n")

        found = self.at(SCOPE_FOLDER)
        self.assertTrue(found.set_here)
        self.assertTrue(found.in_effect)

    def test_a_table_file_stops_the_folder_reaching_that_table(self) -> None:
        """The trap. The two files do not stack: a table with its own file falls through
        to the application for everything that file does not carry, not to the folder."""
        self.folder_file("[Backglass]\nBackglassOutput = 0\n")
        self.table_file("[Backglass]\nGrillHeight = 200\n")

        found = self.at(SCOPE_ENTRY)
        self.assertEqual((found.value, found.scope), ("1", SCOPE_LAUNCHER))

    def test_the_shadowed_folder_value_reports_itself_as_not_in_effect(self) -> None:
        """Invisible otherwise, and it is the bug report we would get."""
        self.folder_file("[Backglass]\nBackglassOutput = 0\n")
        self.table_file("[Backglass]\nGrillHeight = 200\n")

        found = self.at(SCOPE_FOLDER)
        self.assertTrue(found.set_here)
        self.assertFalse(found.in_effect)

    def test_the_other_table_in_the_folder_is_unaffected(self) -> None:
        self.folder_file("[Backglass]\nBackglassOutput = 0\n")
        self.table_file("[Backglass]\nGrillHeight = 200\n")

        self.assertEqual(self.at(SCOPE_ENTRY, self.other).scope, SCOPE_FOLDER)

    def test_a_folder_named_for_its_table_makes_one_file_of_the_two(self) -> None:
        """The ordinary case, and the two scopes coincide rather than shadowing."""
        solo = self.root / "Attack from Mars"
        solo.mkdir()
        table = solo / "Attack from Mars.vpx"
        table.write_text("")
        (solo / "Attack from Mars.ini").write_text("[Backglass]\nBackglassOutput = 0\n")

        for scope in (SCOPE_FOLDER, SCOPE_ENTRY):
            with self.subTest(scope=scope):
                found = self.config.read(scope, str(table), self.settings)[KEY]
                self.assertTrue(found.in_effect)
                self.assertTrue(found.set_here)


class WriteTests(_Case):
    def test_writing_at_a_scope_creates_its_file(self) -> None:
        self.config.write(SCOPE_ENTRY, str(self.table), {KEY: "0"}, self.settings)

        self.assertTrue((self.game / "MM (VPW 1.2).ini").is_file())
        self.assertEqual(self.at(SCOPE_ENTRY).value, "0")

    def test_writing_the_launcher_scope_keeps_the_comments(self) -> None:
        self.config.write(SCOPE_LAUNCHER, "", {KEY: "0"}, self.settings)
        text = self.app_ini.read_text()

        self.assertIn("BackglassOutput = 0", text)
        self.assertIn("; Output Mode: Where it goes", text)

    def test_a_scope_with_nowhere_to_write_says_so(self) -> None:
        with self.assertRaises(ValueError):
            self.config.write(SCOPE_ENTRY, "", {KEY: "0"}, self.settings)


class SchemaTests(_Case):
    def test_vpx_section_names_are_translated_into_this_project_s_words(self) -> None:
        """The window VPX calls the DMD is the one this project calls the score view,
        and a group is where that translation happens."""
        keys = {g.key for g in self.config.groups(self.settings)}

        self.assertIn("scoreview", keys)
        self.assertNotIn("dmd", keys)

    def test_the_groups_come_from_the_file_rather_than_from_here(self) -> None:
        groups = {g.key: g for g in self.config.groups(self.settings)}

        self.assertIn("backglass", groups)
        keys = {f.key for f in groups["backglass"].settings}
        self.assertEqual(keys, {KEY, "Backglass.GrillHeight"})

    def test_a_setting_carries_what_the_comment_said(self) -> None:
        groups = {g.key: g for g in self.config.groups(self.settings)}
        one = next(f for f in groups["backglass"].settings if f.key == KEY)

        self.assertEqual(one.label, "Output Mode")
        self.assertEqual(one.type, "choice")
        self.assertEqual(one.choices, (("0", "Disabled"), ("1", "Floating")))

    def test_what_vpx_wrote_about_itself_is_not_offered_as_a_setting(self) -> None:
        offered = {f.key for g in self.config.groups(self.settings) for f in g.settings}

        self.assertNotIn("Version.VPinball", offered)
        self.assertNotIn("Version.VPinball", self.config.read(
            SCOPE_LAUNCHER, "", self.settings))


class SeedingTests(_Case):
    def test_what_a_folder_would_stop_supplying_is_reportable(self) -> None:
        """Shown in the confirm before a table file takes it off them, so the effective
        values are unchanged at the moment one is created."""
        self.folder_file("[Backglass]\nBackglassOutput = 0\nGrillHeight = 200\n")

        self.assertEqual(sorted(self.config.inherited_from_folder(
            str(self.table), self.settings)),
            ["Backglass.BackglassOutput", "Backglass.GrillHeight"])

    def test_a_table_that_already_has_its_own_file_inherits_nothing(self) -> None:
        self.folder_file("[Backglass]\nBackglassOutput = 0\n")
        self.table_file("[Backglass]\nGrillHeight = 200\n")

        self.assertEqual(self.config.inherited_from_folder(
            str(self.table), self.settings), {})


if __name__ == "__main__":
    unittest.main()
