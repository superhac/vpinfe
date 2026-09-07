"""Reading Visual Pinball's settings file, and writing one back without losing it."""

from __future__ import annotations

import unittest

from apps.vpx import ini as vini

SAMPLE = """\
; #########################
; # A header nobody parses
; #########################

[Editor]
; Enable Log: Enable general logging to the vinball.log file [Default: 1]
EnableLog = 1

; WindowLeft: Main window left [Default: -1]
WindowLeft =

[Backglass]
; Output Mode: Disabled, floating, or embedded [Default: 'Disabled', 0='Disabled', \
1='Floating', 2='Embedded in playfield']
BackglassOutput = 1

; Brightness: How bright [Default: 1.0 in 0.0 .. 2.0]
Brightness = 1.5

; Tint: The color [Default: 0X000000 in 0X000000 .. 0XFFFFFF]
Tint = 0XFF0000

; Name: What to call it [Default: '']
Name = something
"""


class ParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ini = vini.parse(SAMPLE)

    def one(self, qualified: str) -> vini.Setting:
        return self.ini.settings[qualified]

    def test_a_key_is_addressed_by_its_section(self) -> None:
        """A key is only unique inside its section - `Width` is in eight of them."""
        self.assertIn("Editor.EnableLog", self.ini.settings)
        self.assertEqual(self.one("Editor.EnableLog").section, "Editor")

    def test_the_comment_gives_the_label_and_the_description(self) -> None:
        one = self.one("Editor.EnableLog")

        self.assertEqual(one.label, "Enable Log")
        self.assertEqual(one.description,
                         "Enable general logging to the vinball.log file")

    def test_a_closed_set_of_answers_comes_back_as_choices(self) -> None:
        one = self.one("Backglass.BackglassOutput")

        self.assertEqual(one.kind, vini.KIND_CHOICE)
        self.assertEqual(one.choices,
                         (("0", "Disabled"), ("1", "Floating"),
                          ("2", "Embedded in playfield")))

    def test_an_enumerated_default_is_stored_as_its_value_not_its_label(self) -> None:
        """The file states the default by label and stores the number."""
        self.assertEqual(self.one("Backglass.BackglassOutput").default, "0")

    def test_a_number_keeps_its_range(self) -> None:
        one = self.one("Backglass.Brightness")

        self.assertEqual(one.kind, vini.KIND_NUMBER)
        self.assertEqual((one.minimum, one.maximum), (0.0, 2.0))

    def test_a_color_is_not_read_as_a_number(self) -> None:
        """Its range is stated in hex, which a number field cannot use, so it is left
        unstated rather than reported wrong."""
        one = self.one("Backglass.Tint")

        self.assertEqual(one.kind, vini.KIND_COLOR)
        self.assertIsNone(one.minimum)

    def test_a_quoted_default_is_a_string(self) -> None:
        self.assertEqual(self.one("Backglass.Name").kind, vini.KIND_STRING)

    def test_an_empty_value_is_not_the_same_as_an_absent_key(self) -> None:
        """VPX's own header says a property with nothing after the `=` means "use the
        default", so it is a deliberate reset rather than a key the file never had."""
        self.assertEqual(self.ini.value("Editor.WindowLeft"), "")
        self.assertIsNone(self.ini.value("Editor.NeverHeardOf"))

    def test_a_label_falls_back_to_the_key(self) -> None:
        self.assertEqual(vini.parse("[A]\nB = 1\n").settings["A.B"].label, "B")


class WriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ini = vini.parse(SAMPLE)

    def test_writing_nothing_gives_the_file_back(self) -> None:
        self.assertEqual(vini.written(self.ini, {}), SAMPLE)

    def test_a_value_is_replaced_where_it_already_sits(self) -> None:
        """The comments are the only documentation these settings have, so the file
        keeps its own shape rather than being rewritten from the parse."""
        out = vini.written(self.ini, {"Backglass.BackglassOutput": "2"})

        self.assertIn("BackglassOutput = 2", out)
        self.assertIn("; Output Mode: Disabled, floating, or embedded", out)
        self.assertEqual(out.count("BackglassOutput"), 1)

    def test_a_key_the_file_lacks_is_added_under_its_section(self) -> None:
        out = vini.written(self.ini, {"Backglass.NewOne": "3"})
        again = vini.parse(out)

        self.assertEqual(again.settings["Backglass.NewOne"].section, "Backglass")
        self.assertEqual(again.value("Backglass.NewOne"), "3")

    def test_a_section_the_file_lacks_is_added(self) -> None:
        out = vini.written(self.ini, {"Plugin.New.Thing": "on"})

        self.assertEqual(vini.parse(out).value("Plugin.New.Thing"), "on")

    def test_nothing_else_moves(self) -> None:
        before = SAMPLE.splitlines()
        after = vini.written(self.ini, {"Editor.EnableLog": "0"}).splitlines()

        differing = [n for n, (a, b) in enumerate(zip(before, after, strict=True))
                     if a != b]
        self.assertEqual(len(differing), 1)


if __name__ == "__main__":
    unittest.main()
