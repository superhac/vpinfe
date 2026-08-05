"""The action set is declared once, and the copies that cannot import it are checked.

Twelve actions were written out in seven places. Four of those are Python and now read
`common/input_actions.py`; the rest are JavaScript, a diagnostic page and two docs
tables, which cannot import anything. They are pinned here instead, the same way
`tests/test_theme_windows.py` pins the window label map.

The drift these exist to catch is not hypothetical: the JavaScript said `back` was
unbound while Python shipped `b`.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from common import config_schema, input_actions
from frontend.input_api import JOY_MAPPING_KEYS, KEY_MAPPING_DEFAULTS

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_JS = (REPO_ROOT / "web" / "common" / "vpinfe-core.js").read_text(encoding="utf-8")
GAMEPAD_HTML = (REPO_ROOT / "web" / "diag" / "gamepad.html").read_text(encoding="utf-8")


class RegistryTests(unittest.TestCase):
    def test_the_python_views_come_from_the_registry(self) -> None:
        self.assertEqual(JOY_MAPPING_KEYS, input_actions.joy_config_keys())
        self.assertEqual(KEY_MAPPING_DEFAULTS, input_actions.keyboard_defaults())

    def test_every_action_has_both_config_keys_in_the_schema(self) -> None:
        declared = {(o.section, o.key) for o in config_schema.options()}
        for action in input_actions.actions():
            self.assertIn(("Input", action.key_config), declared)
            self.assertIn(("Input", action.joy_config), declared)

    def test_the_shipped_binding_is_the_config_default(self) -> None:
        """The two disagreeing is exactly what happened to `back`."""
        for action in input_actions.actions():
            option = config_schema.option("Input", action.key_config)
            self.assertEqual(option.default, action.keyboard)

    def test_a_config_key_resolves_to_its_action(self) -> None:
        self.assertEqual(input_actions.action_for_config_key("keyleft"), "left")
        self.assertEqual(input_actions.action_for_config_key("joyleft"), "left")
        self.assertEqual(input_actions.action_for_config_key("pagingsize"), "")


class JavaScriptCopiesTests(unittest.TestCase):
    """core.js cannot import Python, so its two tables are checked against the registry."""

    def test_the_default_key_bindings_match(self) -> None:
        block = re.search(r"this\.keyActionMap = \{(.*?)\n    \};", CORE_JS, re.S)
        self.assertIsNotNone(block, "keyActionMap moved; this test needs updating")
        js = dict(re.findall(r"(\w+):\s*\[([^\]]*)\]", block.group(1)))

        expected = {}
        for action in input_actions.actions():
            tokens = [t.strip().lower() for t in action.keyboard.split(",") if t.strip()]
            expected[f"joy{action.name}"] = tokens

        got = {name: [v.strip().strip("'\"").lower() for v in vals.split(",") if v.strip()]
               for name, vals in js.items()}
        self.assertEqual(got, expected,
                         "the JavaScript fallback bindings and the shipped defaults differ")

    def test_the_config_key_to_action_table_matches(self) -> None:
        block = re.search(r"const actionMap = \{(.*?)\n  \};", CORE_JS, re.S)
        self.assertIsNotNone(block, "actionMap moved; this test needs updating")
        js = dict(re.findall(r"(\w+):\s*'(\w+)'", block.group(1)))

        self.assertEqual(js, {a.key_config: a.joy_config for a in input_actions.actions()})


class DiagnosticPageTests(unittest.TestCase):
    def test_the_gamepad_page_offers_every_action(self) -> None:
        """It is where a cabinet's buttons get bound, so a missing action is unbindable."""
        for action in input_actions.actions():
            self.assertIn(action.joy_config, GAMEPAD_HTML,
                          f"{action.joy_config} cannot be bound on the gamepad page")


class DocumentationTests(unittest.TestCase):
    def test_the_docs_list_every_action(self) -> None:
        for name in ("docs/technical_details.md", "docs/theme.md"):
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
            for action in input_actions.actions():
                self.assertIn(action.joy_config, text,
                              f"{name} does not mention {action.joy_config}")


if __name__ == "__main__":
    unittest.main()
