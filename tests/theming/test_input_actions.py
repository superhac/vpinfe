"""The action set is declared once, and the copies that cannot import it are checked.

Ten actions, each with one binding list. The names say what the player meant rather than
which way a stick moved, and a binding names its own input - so the twelve-action,
two-key-per-action shape is gone and with it the table that translated `key*` to `joy*`.

What cannot import Python is pinned here: core.js's fallback bindings, the contract 1
name map that keeps twelve published themes working, and the gamepad binding page.
"""

from __future__ import annotations

import configparser
import re
import unittest
from pathlib import Path

from common import config_schema, input_registry
from frontend import input_api

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CORE_JS_PATH = REPO_ROOT / "frontend" / "static" / "common" / "vpinfe-core.js"
CORE_JS = _CORE_JS_PATH.read_text(encoding="utf-8")


class RegistryTests(unittest.TestCase):
    def test_there_are_ten_actions(self) -> None:
        """Twelve became ten: up/down and pageup/pagedown were one intent twice."""
        self.assertEqual([a.name for a in input_registry.actions()],
                         ["previous", "next", "page_previous", "page_next", "select",
                          "back", "menu", "collection_menu", "tutorial", "exit"])

    def test_every_action_is_a_config_option(self) -> None:
        declared = {(o.section, o.key) for o in config_schema.options()}
        for action in input_registry.actions():
            self.assertIn((input_registry.SECTION, action.name), declared)

    def test_the_shipped_bindings_are_the_config_default(self) -> None:
        for action in input_registry.actions():
            option = config_schema.option(input_registry.SECTION, action.name)
            self.assertEqual(option.default, ",".join(action.bindings))

    def test_an_old_key_still_names_its_action(self) -> None:
        for old, expect in (("keyleft", "previous"), ("joyleft", "previous"),
                            ("joyup", "page_previous"), ("keypagedown", "page_next"),
                            ("joycollectionmenu", "collection_menu")):
            self.assertEqual(input_registry.action_for_legacy_key(old), expect)


class BindingProjectionTests(unittest.TestCase):
    """The Manager UI shows a keyboard field and a controller field over one list."""

    BINDINGS = ["key:ArrowLeft", "key:ShiftLeft", "pad:0/button:4",
                "chord(pad:0/button:4+pad:0/button:5)@hold:1000"]

    def test_each_field_shows_its_own_input(self) -> None:
        self.assertEqual(input_registry.keys_in(self.BINDINGS), ["ArrowLeft", "ShiftLeft"])
        self.assertEqual(input_registry.pad_buttons_in(self.BINDINGS), ["4"])

    def test_what_neither_field_can_show_is_kept(self) -> None:
        """Dropping it would delete a cabinet's hold-both-flippers binding on Save."""
        self.assertEqual(input_registry.unrenderable(self.BINDINGS),
                         ["chord(pad:0/button:4+pad:0/button:5)@hold:1000"])

    def test_an_old_value_becomes_selectors(self) -> None:
        self.assertEqual(input_registry.binding_for_legacy("keyleft", "ArrowLeft,ShiftLeft"),
                         ["key:ArrowLeft", "key:ShiftLeft"])
        self.assertEqual(input_registry.binding_for_legacy("joyleft", "3"),
                         ["pad:0/button:3"])


class CollisionTests(unittest.TestCase):
    """A binding two actions hold only ever fires the first of them, and nothing said so.

    Dispatch resolves a key to the first action listing it, so the loser is not a
    conflict somebody is asked about - it is a binding that does nothing, made on a page
    that showed no sign.
    """

    def test_a_binding_one_action_holds_is_not_a_collision(self) -> None:
        found = input_registry.collisions(
            {"previous": ["key:ArrowLeft"], "next": ["key:ArrowRight"]})

        self.assertEqual(found, {})

    def test_a_binding_two_actions_hold_names_both(self) -> None:
        found = input_registry.collisions(
            {"back": ["key:b", "key:Escape"], "exit": ["key:Escape", "key:q"]})

        self.assertEqual(found, {"key:Escape": ["back", "exit"]})

    def test_an_action_listing_one_twice_does_not_collide_with_itself(self) -> None:
        self.assertEqual(
            input_registry.collisions({"back": ["key:b", "key:b"]}), {})

    def test_holders_answers_who_has_it_before_anything_clashes(self) -> None:
        """Refusing a binding another action already holds needs this, not the clash
        list - which by definition only names what is already broken."""
        found = input_registry.holders({"previous": ["key:F9"], "next": []})

        self.assertEqual(found, {"key:F9": ["previous"]})

    def test_the_shipped_bindings_do_not_collide(self) -> None:
        self.assertEqual(input_registry.collisions(input_registry.defaults()), {})

    def test_an_install_that_holds_one_is_told(self) -> None:
        """The Console refuses new ones; an install that already has one gets a line in
        the log, because the alternative is a player concluding the cabinet is broken."""
        input_api._said_collisions.clear()
        parser = configparser.ConfigParser()
        parser.add_section("input")
        parser.set("input", "back", "key:b,key:Escape")

        with self.assertLogs("vpinfe.frontend.input_api", level="WARNING") as caught:
            input_api.get_bindings(parser)

        self.assertIn("Esc", caught.output[0])
        self.assertIn("back", caught.output[0])
        self.assertIn("exit", caught.output[0])

    def test_it_is_said_once_and_not_on_every_page(self) -> None:
        input_api._said_collisions.clear()
        parser = configparser.ConfigParser()
        parser.add_section("input")
        parser.set("input", "back", "key:b,key:Escape")
        input_api.get_bindings(parser)

        with self.assertNoLogs("vpinfe.frontend.input_api", level="WARNING"):
            input_api.get_bindings(parser)


class ReadableBindingTests(unittest.TestCase):
    """A selector is written for a parser. Ten of them on a settings page is what made
    input read as configuration rather than a choice."""

    def test_a_key_is_named_as_a_keyboard_prints_it(self) -> None:
        for selector, expected in (("key:ArrowLeft", "Left arrow"),
                                   ("key:ShiftLeft", "Left Shift"),
                                   ("key:KeyM", "M"),
                                   ("key:Digit4", "4"),
                                   ("key:Escape", "Esc"),
                                   ("key:b", "B"),
                                   ("key:Comma", ",")):
            with self.subTest(selector=selector):
                self.assertEqual(input_registry.describe(selector), expected)

    def test_pads_are_numbered_from_one_on_screen(self) -> None:
        """Zero on the wire, one in the hand. Somebody with a single controller has
        pad 1."""
        self.assertEqual(input_registry.describe("pad:0/button:3"), "Pad 1 button 3")

    def test_what_it_cannot_name_comes_back_as_it_was(self) -> None:
        """Inventing a name for a chord would be worse than showing the one stored."""
        for selector in ("pad:0/chord(1,2)", "key:ArrowLeft@hold", "nonsense"):
            with self.subTest(selector=selector):
                self.assertEqual(input_registry.describe(selector), selector)


class ChordIdentityTests(unittest.TestCase):
    """A chord is a set of inputs held together, so it is compared as one.

    And it does not fold into its members: both flippers fire their own actions *and*
    the chord, which is the decision rather than an oversight - so a chord and a plain
    binding on one of its members are two bindings that both work.
    """

    def test_a_chord_written_either_way_round_is_one_binding(self) -> None:
        self.assertEqual(
            input_registry.identity("chord(key:b+key:a)"),
            input_registry.identity("chord(key:a+key:b)"))

    def test_two_actions_holding_the_same_chord_collide(self) -> None:
        found = input_registry.collisions(
            {"exit": ["chord(key:a+key:b)"], "back": ["chord(key:b+key:a)"]})

        self.assertEqual(list(found.values()), [["exit", "back"]])

    def test_a_chord_does_not_collide_with_its_own_members(self) -> None:
        """The shipped idiom is exactly this - hold both flippers, and both flippers are
        bound. A rule that called it a collision would refuse the one example the design
        is built around."""
        self.assertEqual(
            input_registry.collisions({
                "exit": ["chord(key:ShiftLeft+key:ShiftRight)@hold:1500"],
                "previous": ["key:ShiftLeft"],
                "next": ["key:ShiftRight"]}),
            {})

    def test_a_hold_is_part_of_what_makes_two_bindings_different(self) -> None:
        self.assertNotEqual(input_registry.identity("chord(key:a+key:b)"),
                            input_registry.identity("chord(key:a+key:b)@hold:1500"))

    def test_a_repeated_member_is_held_once(self) -> None:
        self.assertEqual(input_registry.chord_members("chord(key:a+key:a+key:b)"),
                         ("key:a", "key:b"))

    def test_what_is_not_a_chord_has_no_members(self) -> None:
        for selector in ("key:a", "pad:0/button:1", "chord(", ""):
            with self.subTest(selector=selector):
                self.assertEqual(input_registry.chord_members(selector), ())


class OneSpellingPerKeyTests(unittest.TestCase):
    """A browser reports two things for a key: what it produces (`event.key`, "c") and
    which key it is (`event.code`, "KeyC").

    The defaults were written in the first and capture stores the second. Dispatch matches
    on both of an event's tokens, so both work - and a config could hold one key under two
    spellings with nothing to say so. That is the same silence B6 was about.
    """

    def test_a_single_character_becomes_its_code(self) -> None:
        for selector, expected in (("key:c", "key:KeyC"), ("key:B", "key:KeyB"),
                                   ("key:4", "key:Digit4"), ("key:,", "key:Comma")):
            with self.subTest(selector=selector):
                self.assertEqual(input_registry.normalize(selector), expected)

    def test_a_code_is_already_the_answer(self) -> None:
        for selector in ("key:KeyC", "key:ArrowLeft", "key:Escape", "key:F9"):
            with self.subTest(selector=selector):
                self.assertEqual(input_registry.normalize(selector), selector)

    def test_it_leaves_alone_what_it_does_not_understand(self) -> None:
        """Guessing would invent a key nobody pressed."""
        for selector in ("pad:0/button:1", "chord(key:a+key:b)", "", "nonsense"):
            with self.subTest(selector=selector):
                self.assertEqual(input_registry.normalize(selector), selector)

    def test_two_spellings_of_one_key_are_one_clash(self) -> None:
        found = input_registry.collisions({"back": ["key:c"], "menu": ["key:KeyC"]})

        self.assertEqual(found, {"key:KeyC": ["back", "menu"]})

    def test_a_chord_normalizes_its_members_too(self) -> None:
        self.assertEqual(input_registry.identity("chord(key:b+key:a)"),
                         input_registry.identity("chord(key:KeyA+key:KeyB)"))

    def test_both_spellings_read_the_same_on_screen(self) -> None:
        self.assertEqual(input_registry.describe("key:c"),
                         input_registry.describe("key:KeyC"))

    def test_the_shipped_defaults_are_codes(self) -> None:
        """So a captured binding and a shipped one are spelled the same way, which is
        what stops the two drifting again."""
        for action in input_registry.actions():
            for binding in action.bindings:
                with self.subTest(action=action.name, binding=binding):
                    self.assertEqual(input_registry.normalize(binding), binding)


class HoldEditingTests(unittest.TestCase):
    """A hold is a modifier on a binding rather than a different binding, so adding one
    after the fact is editing a suffix and nothing else."""

    def test_it_round_trips(self) -> None:
        for binding in ("key:Escape", "pad:0/button:3", "chord(key:a+key:b)"):
            with self.subTest(binding=binding):
                held = input_registry.with_hold(binding, 1500)
                self.assertEqual(input_registry.hold_ms(held), 1500)
                self.assertEqual(input_registry.with_hold(held, 0), binding)

    def test_a_negative_duration_is_no_hold_rather_than_a_broken_one(self) -> None:
        self.assertEqual(input_registry.with_hold("key:a", -50), "key:a")


class ComposedNameTests(unittest.TestCase):
    def test_a_chord_reads_as_its_parts(self) -> None:
        self.assertEqual(
            input_registry.describe("chord(key:ShiftLeft+key:ShiftRight)@hold:1500"),
            "Left Shift + Right Shift, held 1.5s")

    def test_a_hold_is_said_in_seconds(self) -> None:
        """A hold is something a person counts, not a number of milliseconds."""
        self.assertEqual(input_registry.describe("key:Escape@hold:800"),
                         "Esc, held 0.8s")
        self.assertEqual(input_registry.describe("key:Escape@hold:2000"),
                         "Esc, held 2s")

    def test_a_selector_it_still_cannot_name_comes_back_whole(self) -> None:
        for selector in ("pad:0/axis:1+@deadzone:0.5", "key:ctrl+KeyQ"):
            with self.subTest(selector=selector):
                self.assertEqual(input_registry.describe(selector), selector)


class WhatCaptureCannotRemakeTests(unittest.TestCase):
    """Asked before offering to delete a binding: removing what nothing can rebuild is a
    door that only opens one way.

    The set shrank when capture learned to watch until release - a chord is pressing two
    things and a hold is keeping one down, so both are gestures now.
    """

    def test_anything_a_gesture_can_make(self) -> None:
        for selector in ("key:ArrowLeft", "pad:0/button:3",
                         "chord(key:a+key:b)", "key:Escape@hold:1500",
                         "chord(key:a+key:b)@hold:1500"):
            with self.subTest(selector=selector):
                self.assertTrue(input_registry.capturable(selector))

    def test_a_modifier_and_an_axis_have_no_gesture(self) -> None:
        """Shift is a flipper on a cabinet and has to stay bindable on its own, so a
        modifier cannot be captured by pressing one; an axis is a tuned value rather
        than a press."""
        for selector in ("key:ctrl+KeyQ", "key:shift+KeyQ",
                         "pad:0/axis:1+@deadzone:0.5"):
            with self.subTest(selector=selector):
                self.assertFalse(input_registry.capturable(selector))


class JavaScriptCopiesTests(unittest.TestCase):
    def test_the_fallback_bindings_match_the_shipped_ones(self) -> None:
        block = re.search(r"this\.keyActionMap = \{(.*?)\n    \};", CORE_JS, re.S)
        self.assertIsNotNone(block, "keyActionMap moved; this test needs updating")
        js = {name: [v.strip().strip("'\"").lower() for v in vals.split(",") if v.strip()]
              for name, vals in re.findall(r"(\w+):\s*\[([^\]]*)\]", block.group(1))}

        expected = {a.name: [k.lower() for k in input_registry.keys_in(a.bindings)]
                    for a in input_registry.actions()}
        self.assertEqual(js, expected)

    def test_contract_1_gets_a_name_for_every_action(self) -> None:
        """A missing entry means a published theme's `case` silently stops matching."""
        block = re.search(r"const LEGACY_ACTION_NAMES = \{(.*?)\n\};", CORE_JS, re.S)
        self.assertIsNotNone(block, "the legacy name map moved")
        js = dict(re.findall(r"(\w+):\s*\"(\w+)\"", block.group(1)))

        self.assertEqual(js, {a.name: a.legacy_joy_key for a in input_registry.actions()})


class BridgeTests(unittest.TestCase):
    def test_the_old_bridge_methods_still_answer(self) -> None:
        """Projected out of the lists, so anything built against them keeps working."""
        from configparser import ConfigParser

        parser = ConfigParser()
        parser.read_dict({"input": {"previous": "key:ArrowLeft,pad:0/button:3"}})

        self.assertEqual(input_api.get_keymapping(parser)["keyleft"], "ArrowLeft")
        self.assertEqual(input_api.get_joymapping(parser)["joyleft"], "3")


if __name__ == "__main__":
    unittest.main()
