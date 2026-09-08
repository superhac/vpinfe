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
# Not contextual, where `KEY` is: the program keeps a contextual table value even when
# it matches the application's, so a rule about matching values needs an ordinary one.
PLAIN = "DMD.Profile1Legacy"


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

    def test_a_launcher_value_with_no_table_in_play_is_in_force(self) -> None:
        """Nothing sits above the application layer, so a value set there is the one
        that wins - and a row saying otherwise marks every setting as shadowed."""
        found = self.config.read(SCOPE_LAUNCHER, "", self.settings)[KEY]

        self.assertTrue(found.set_here)
        self.assertTrue(found.in_effect)

    def test_a_launcher_value_a_table_overrides_is_still_in_force_at_its_own_scope(self) -> None:
        """The launcher is not shadowed by a table: it still answers for every other
        table. Only the layer that lost to another at the *same* scope is."""
        self.table_file("[Backglass]\nBackglassOutput = 0\n")

        found = self.config.read(SCOPE_LAUNCHER, str(self.table), self.settings)[KEY]
        self.assertTrue(found.set_here)

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


class TypeTests(_Case):
    def test_the_program_says_what_a_setting_is_and_the_file_cannot(self) -> None:
        """`Enable Log` and `ImageMngPosX` both default to a bare 0 or 1. Only the
        program's own declarations separate a switch from a number."""
        from apps.vpx.setting_types import TYPES

        self.assertEqual(TYPES.get("Editor.EnableLog"), "bool")
        self.assertEqual(TYPES.get("Editor.WindowLeft"), "int")

    def test_every_plugin_has_a_switch(self) -> None:
        """The host creates it so a plugin can be turned off, and no plugin declares
        it - so it is the one switch that would have had no type at all."""
        from apps.vpx.setting_types import TYPES

        for plugin in ("Plugin.B2S", "Plugin.PinMAME", "Plugin.FlexDMD"):
            with self.subTest(plugin=plugin):
                self.assertEqual(TYPES.get(f"{plugin}.Enable"), "bool")

    def test_a_setting_the_program_has_not_declared_keeps_what_the_file_implied(self) -> None:
        """A stale map degrades rather than breaks."""
        from apps.vpx import ini as vini
        from apps.vpx.config import _type_of

        one = vini.parse("[Nowhere]\n; A: b [Default: 3]\nNeverDeclared = 3\n")
        self.assertEqual(_type_of(one.settings["Nowhere.NeverDeclared"]), "int")

    def test_what_the_program_keeps_in_the_file_is_not_offered_as_a_setting(self) -> None:
        """Key bindings written per device, and the order plugins render in. State that
        happens to share the file, and 59 rows of it is noise to read past."""
        offered = {f.key for g in self.config.groups(self.settings) for f in g.settings}

        for key in ("Input.Mapping.LeftFlipper", "Input.Device.Key.Type",
                    "Backglass.Priority.PUP"):
            with self.subTest(key=key):
                self.assertNotIn(key, offered)

    def test_a_binding_is_hidden_even_though_its_section_is_not(self) -> None:
        """`[Input]` holds both `Mapping.LeftFlipper` and real settings, so the whole
        name decides rather than the heading above it."""
        from apps.vpx.config import _offered

        self.assertFalse(_offered("Input.Mapping.LeftFlipper"))
        self.assertTrue(_offered("Input.JoyCustom1"))


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


class WritingLikeTheProgramTests(_Case):
    """A table layer is not written the way the application layer is, and the difference
    is the program's, not ours.

    `LayeredINIPropertyStore::Save` writes every key at the application layer, blank
    where it has no value. At a table it writes only real overrides: a key it has no
    value for is removed, and so is one whose value matches the application's - unless
    the property is contextual. Writing our own way leaves a file the program rewrites
    the first time it saves, and the parts it rewrote are the parts somebody set here.
    """

    def test_a_real_override_is_written(self) -> None:
        self.config.write("entry", str(self.table), {KEY: "0"}, self.settings)

        self.assertEqual(self.at("entry")[0] if isinstance(self.at("entry"), tuple)
                         else self.at("entry").value, "0")

    def test_clearing_at_a_table_removes_the_key(self) -> None:
        """Rather than blanking it. Both read the same on the way back in, and the
        program deletes a blank one the next time it saves."""
        self.config.write("entry", str(self.table), {KEY: "0"}, self.settings)
        self.config.write("entry", str(self.table), {KEY: ""}, self.settings)

        written = (self.game / "MM (VPW 1.2).ini").read_text()
        self.assertNotIn("BackglassOutput", written)

    def test_clearing_at_the_application_blanks_it_instead(self) -> None:
        """Which is what the program does where there is no parent to fall through to."""
        self.config.write("launcher", str(self.table), {KEY: ""}, self.settings)

        self.assertIn("BackglassOutput =", self.app_ini.read_text())

    def test_holding_a_table_at_the_inherited_value_is_refused(self) -> None:
        """The program drops exactly this on its next save, so writing it would leave a
        setting that reads as set until something else quietly unset it.

        `Profile1Legacy` rather than the key the rest of this file uses: that one is
        contextual, which is the exception rather than the rule being tested.
        """
        from apps.vpx.config import SettingRefusedError

        with self.assertRaises(SettingRefusedError) as caught:
            self.config.write("entry", str(self.table),
                              {PLAIN: "1"}, self.settings)

        self.assertIn(PLAIN, caught.exception.refusals)

    def test_and_the_refusal_names_the_setting_and_what_to_do(self) -> None:
        """A refusal a surface can only report as "could not save" sends somebody
        looking for a fault that is not there."""
        from apps.vpx.config import SettingRefusedError

        with self.assertRaises(SettingRefusedError) as caught:
            self.config.write("entry", str(self.table),
                              {PLAIN: "1"}, self.settings)

        said = caught.exception.refusals[PLAIN]
        self.assertIn("already", said)
        self.assertIn("every table", said)

    def test_a_different_value_is_written_at_a_table(self) -> None:
        self.config.write("entry", str(self.table), {PLAIN: "0"}, self.settings)

        self.assertIn("Profile1Legacy = 0",
                      (self.game / "MM (VPW 1.2).ini").read_text())

    def test_a_contextual_setting_may_be_held_at_it(self) -> None:
        """The program keeps those even when they match, so we do too."""
        from apps.vpx.config import CONTEXTUAL

        held = next(iter(CONTEXTUAL))
        section, _, key = held.partition(".")
        self.app_ini.write_text(f"{self.app_ini.read_text()}\n[{section}]\n{key} = 7\n")

        self.config.write("entry", str(self.table), {held: "7"}, self.settings)

        self.assertIn(key, (self.game / "MM (VPW 1.2).ini").read_text())

    def test_the_application_layer_may_hold_any_value(self) -> None:
        """There is nothing above it to match, so nothing to be redundant against."""
        self.config.write("launcher", str(self.table), {KEY: "1"}, self.settings)

        self.assertIn("BackglassOutput = 1", self.app_ini.read_text())
