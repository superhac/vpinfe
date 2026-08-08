"""The action set is declared once, and the copies that cannot import it are checked.

Ten actions, each with one binding list. The names say what the player meant rather than
which way a stick moved, and a binding names its own device - so the twelve-action,
two-key-per-action shape is gone and with it the table that translated `key*` to `joy*`.

What cannot import Python is pinned here: core.js's fallback bindings, the contract 1
name map that keeps twelve published themes working, and the gamepad binding page.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from common import config_schema, input_registry
from frontend import input_api

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORE_JS = (REPO_ROOT / "web" / "common" / "vpinfe-core.js").read_text(encoding="utf-8")


class RegistryTests(unittest.TestCase):
    def test_there_are_ten_actions(self) -> None:
        """Twelve became ten: up/down and pageup/pagedown were one intent twice."""
        self.assertEqual([a.name for a in input_registry.actions()],
                         ["previous", "next", "page_up", "page_down", "select",
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
                            ("joyup", "page_up"), ("keypagedown", "page_down"),
                            ("joycollectionmenu", "collection_menu")):
            self.assertEqual(input_registry.action_for_legacy_key(old), expect)


class BindingProjectionTests(unittest.TestCase):
    """The Manager UI shows a keyboard field and a controller field over one list."""

    BINDINGS = ["key:ArrowLeft", "key:ShiftLeft", "pad:0/button:4",
                "chord(pad:0/button:4+pad:0/button:5)@hold:1000"]

    def test_each_field_shows_its_own_device(self) -> None:
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
