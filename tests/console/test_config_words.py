"""What a settings row says about where its value came from.

The program's file is 98% untouched keys, so most of what this surface shows is a value
nobody chose. Saying that in the wire's word - `unset` - would put a term on screen that
nobody outside this project uses, and putting it on almost every row would say nothing
either way.
"""

from __future__ import annotations

import unittest

from console import workbench


class _Bool:
    type = "bool"
    choices = ()
    default = "1"
    key = "Backglass.ShowGrill"


class _Choice:
    type = "choice"
    choices = (("0", "Disabled"), ("1", "Floating"))
    default = "0"
    key = "Backglass.BackglassOutput"


class ValueWordTests(unittest.TestCase):
    def test_a_switch_reads_on_and_off_rather_than_one_and_zero(self) -> None:
        self.assertEqual(workbench._said_value(_Bool, "1"), "On")
        self.assertEqual(workbench._said_value(_Bool, "0"), "Off")

    def test_a_choice_reads_its_own_label(self) -> None:
        self.assertEqual(workbench._said_value(_Choice, "1"), "Floating")

    def test_a_value_with_no_label_is_shown_as_it_is(self) -> None:
        self.assertEqual(workbench._said_value(_Choice, "7"), "7")


class ClearHintTests(unittest.TestCase):
    def test_clearing_names_what_it_will_follow(self) -> None:
        """So nobody has to change a value to find out what it was following."""
        said = workbench._clear_hint(
            {"fallback_scope": "launcher", "fallback": "0"}, _Bool)

        self.assertEqual(said, "Will follow the launcher (Off)")

    def test_and_names_the_layer_by_what_it_is(self) -> None:
        said = workbench._clear_hint(
            {"fallback_scope": "folder", "fallback": "1"}, _Choice)

        self.assertEqual(said, "Will follow the folder (Floating)")

    def test_with_nothing_under_it_the_program_answers(self) -> None:
        self.assertEqual(workbench._clear_hint({}, _Bool), "Will go back to On")


class MarkTests(unittest.TestCase):
    def test_a_value_nobody_has_touched_is_not_marked(self) -> None:
        """Unmarked is the untouched one, so a mark always means somebody did
        something. On 98% of rows a mark would say nothing."""
        self.assertIsNone(workbench._config_mark(
            {"set_here": False, "in_effect": True, "scope": ""}, "launcher"))

    def test_a_value_set_at_this_scope_says_so(self) -> None:
        self.assertIsNotNone(workbench._config_mark(
            {"set_here": True, "in_effect": True, "scope": "launcher"}, "launcher"))

    def test_a_value_from_another_layer_names_that_layer(self) -> None:
        self.assertIn("folder", workbench.CAME_FROM["folder"].lower())
        self.assertIsNotNone(workbench._config_mark(
            {"set_here": False, "in_effect": True, "scope": "folder"}, "entry"))

    def test_a_shadowed_value_is_the_loud_one(self) -> None:
        """Somebody wrote it and another layer answers over it. Invisible on the row
        otherwise, and the bug report we would get."""
        mark = workbench._config_mark(
            {"set_here": True, "in_effect": False, "scope": "launcher"}, "folder")

        self.assertIsNotNone(mark)

    def test_no_word_on_screen_is_the_wire_s(self) -> None:
        said = " ".join(workbench.CAME_FROM.values()).lower()

        self.assertNotIn("unset", said)
        self.assertNotIn("scope", said)


if __name__ == "__main__":
    unittest.main()
