"""One control grammar, and what is allowed to sit outside it.

The Console had two answers to "what control does this type want": `settings.control_for`
for a config option, and a copy of it in the themes page for a theme's own options. Two
answers drift the moment either gains a type, which is what these pin.

The budget below is the other half. A raw `ui.*` control is not wrong - a toolbar search
box has no label column and sets nothing, so it is not a fact row and forcing it through
`panel` would be worse. What is wrong is a *new* one appearing without anybody deciding
that, so each module says how many it has and why.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from console import binding_editor, panel, settings, themes

CONSOLE = Path(__file__).resolve().parent.parent.parent / "console"

CONTROLS = re.compile(r"ui\.(switch|checkbox|input|select|number|textarea)\(")

# What each module draws by hand, and why it is not a fact row. `panel.py` is the home of
# the grammar and is not counted. Raising a number is a decision: say what the control is
# for, or use `panel`.
BUDGET = {
    "workbench.py": (17, "panel rows with bespoke wiring - chips, debounce, a disabled "
                         "select carrying its own reason - plus one find box, and what "
                         "the two add dialogs ask for: a name and a program for "
                         "something with no file, a path for something elsewhere. All "
                         "three are questions, not facts about a thing that exists "
                         "yet"),
    "logs.py": (4, "the control bar above the viewport: two pickers, a level and a find"),
    "games.py": (3, "the view picker in the toolbar, and two dialogs"),
    "mediasource.py": (2, "a start picker and a search, both toolbar"),
    "launchers.py": (2, "checkboxes in the copy-to-device dialog"),
    "about.py": (1, "the textarea a browser that will not copy falls back to"),
    "binding_editor.py": (2, "the hold switch and its duration, in the menu a chip "
                             "opens - not a fact row, and the row it belongs to is "
                             "already a strip of chips"),
    "collections.py": (1, "the name field in the new-collection dialog"),
    "import_dialog.py": (5, "the per-item checkbox, the folder name and the record "
                            "picker in the import confirmation, plus the destination "
                            "picker and its do-not-ask-again - all questions about "
                            "something that does not exist yet, which is what a fact "
                            "row is not for"),
    "app_settings.py": (1, "the scope picker in the dialog's toolbar, which is not a "
                           "fact row - it says where edits go rather than holding a "
                           "value of its own"),
    "locations.py": (1, "the folder field in the add-a-location dialog, which is asked "
                        "up front because a location with no folder set reads as "
                        "unreachable - the same words a dropped share uses"),
    "tageditor.py": (1, "the inline tag field, which is the editor itself"),
    "remote.py": (3, "the target picker in the header, which says which machine every "
                     "action on the screen is about, and the find field and collection "
                     "picker above the game list. None is a fact row: two are questions "
                     "about what to show and the third is about where. A library is "
                     "longer than a screen, and a list longer than a screen is typed "
                     "into rather than scrolled"),
    "vps_match.py": (1, "the query the catalog is searched with, which starts as the "
                        "game's name and is meant to be edited. Not a fact row: it holds "
                        "what is being asked, never what the game is"),
}


class ThemeOptionsUseTheSharedGrammar(unittest.TestCase):
    """A theme's settings are settings, drawn the way every other setting is."""

    def test_every_declared_type_maps_onto_a_control(self) -> None:
        cases = {
            "boolean": "bool",
            "number": "number",
            "select": "choice",
            "textarea": "text",
            "json": "text",
            "": "text",
            "something-new": "text",
        }
        for declared, expected in cases.items():
            with self.subTest(declared=declared):
                found = themes._as_option({"key": "k", "type": declared,
                                           "options": ["a", "b"]})
                self.assertEqual(found["type"], expected)

    def test_a_number_keeps_its_bounds_and_its_fraction(self) -> None:
        """`int` was the nearest existing type and it is the wrong one: a theme declares
        scale factors, and formatting one as a whole number shows a value that is not
        the one stored."""
        found = themes._as_option({"key": "k", "type": "number", "min": 0.5, "max": 2,
                                   "step": 0.1})

        self.assertEqual(found["type"], "number")
        self.assertEqual((found["min"], found["max"], found["step"]), (0.5, 2, 0.1))

    def test_choices_reach_the_control_as_a_mapping(self) -> None:
        """A theme names its choices `{value: label}`. Flattened to a list, the stored
        value goes on screen where the label belongs."""
        found = themes._as_option({
            "key": "k", "type": "select",
            "options": [{"value": "hi", "label": "High"}, {"value": "lo", "label": "Low"}]})

        self.assertEqual(found["choices"], {"hi": "High", "lo": "Low"})


class WhatTheDialogHolds(unittest.TestCase):
    """Nothing is written until Save, so editing a control changes the dialog's own
    pending values.

    Unit-level because it is the wiring rather than the rendering. The round trip through
    a real browser is a separate thing and it does work - a Quasar toggle clicked in
    headless Chromium reaches the server and the value lands on disk.
    """

    def setUp(self) -> None:
        self.captured: dict = {}
        self.real = panel.switch

        def fake(value, on_change, **kw):
            self.captured["value"] = value
            self.captured["on_change"] = on_change
            return lambda: None

        settings.panel.switch = fake

    def tearDown(self) -> None:
        settings.panel.switch = self.real

    def test_changing_a_control_changes_the_pending_value(self) -> None:
        wanted = {"k": False}

        rows = themes._rows([{"key": "k", "name": "Start", "type": "boolean"}], wanted)

        self.assertEqual(rows[0][0], "Start")
        self.assertIs(self.captured["value"], False)
        self.captured["on_change"](SimpleNamespace(value=True))
        self.assertEqual(wanted, {"k": True})

    def test_json_is_parsed_where_it_is_typed(self) -> None:
        """While the dialog is open and beside the field that has it, rather than as a
        string the theme's own code cannot read."""
        wanted: dict = {"k": None}
        save = themes._saver({"key": "k", "type": "json"}, wanted)

        self.assertTrue(save('{"a": 1}'))
        self.assertEqual(wanted["k"], {"a": 1})
        self.assertFalse(save("{not json"))
        self.assertEqual(wanted["k"], {"a": 1}, "a refused value must not be stored")
        self.assertTrue(save("  "))
        self.assertIsNone(wanted["k"])

    def test_a_json_value_reaches_the_field_as_json(self) -> None:
        """A field handed an object renders Python's idea of it - single quotes and
        all - which is not what the theme would read back."""
        shown = themes._shown({"key": "k", "type": "json"}, {"k": {"a": 1}})

        self.assertIn('"a"', shown)


class ADeclaredEditorIsRouted(unittest.TestCase):
    """A setting can ask for a tool where a control cannot do the job, and it is routed
    the way `type` is - so declaring one is a line in the schema rather than a branch in
    the renderer."""

    def test_the_input_actions_ask_for_the_binding_editor(self) -> None:
        from common import config_schema

        asked = {one.editor for one in config_schema.options()
                 if one.section == "input"}

        self.assertEqual(asked, {config_schema.EDITOR_BINDING})

    def test_every_declared_editor_is_one_the_console_serves(self) -> None:
        from common import config_schema

        declared = {one.editor for one in config_schema.options() if one.editor}

        self.assertTrue(declared <= set(settings.EDITORS),
                        "a setting asks for an editor nothing draws")
        self.assertTrue(declared <= set(config_schema.EDITORS),
                        "an editor name outside the closed set is a typo, not a tool")


class BindingsAreNotTypedIn(unittest.TestCase):
    """`pad:0/button:3` is written for a parser. The editor shows what was pressed."""

    def test_a_default_arrives_as_a_string_and_is_not_read_letter_by_letter(self) -> None:
        """A stored value is a list; a schema default is the comma-joined string the
        config file would hold. `list()` of the second is one chip per character."""
        self.assertEqual(
            binding_editor._selectors("key:ArrowLeft,key:ShiftLeft"),
            ["key:ArrowLeft", "key:ShiftLeft"])
        self.assertEqual(
            binding_editor._selectors(["key:Enter"]), ["key:Enter"])
        self.assertEqual(binding_editor._selectors(None), [])

    def test_a_chord_is_found_whichever_order_it_was_written(self) -> None:
        """A chord is a set. Looked up as raw text, one of the two rows holding it is
        marked and the other stays silent."""
        # Keyed the way `holders` keys it - by identity, which settles both the
        # member order and each member's spelling.
        held = {"chord(key:KeyA+key:KeyB)": ["back", "exit"]}

        self.assertEqual(
            binding_editor._owner("chord(key:b+key:a)", held, {"key": "exit"}), "Back")

    def test_it_names_who_already_holds_a_binding(self) -> None:
        held = {"key:Escape": ["back", "exit"]}

        self.assertEqual(
            binding_editor._owner("key:Escape", held, {"key": "back"}), "Exit")
        self.assertEqual(
            binding_editor._owner("key:Escape", held, {"key": "exit"}), "Back")
        self.assertEqual(
            binding_editor._owner("key:m", held, {"key": "back"}), "")


class AHoldCanBeSetRatherThanPerformed(unittest.TestCase):
    """You can hold a button for about a second and a half. You cannot hold it for
    exactly 1,500ms, and you may want one on a binding you already captured without."""

    def test_a_hold_is_added_to_a_binding_that_has_none(self) -> None:
        from common import input_registry

        self.assertEqual(input_registry.with_hold("chord(key:a+key:b)", 1500),
                         "chord(key:a+key:b)@hold:1500")

    def test_a_duration_is_changed_rather_than_stacked(self) -> None:
        from common import input_registry

        once = input_registry.with_hold("key:Escape", 1000)

        self.assertEqual(input_registry.with_hold(once, 2500), "key:Escape@hold:2500")
        self.assertEqual(input_registry.hold_ms(once), 1000)

    def test_zero_takes_the_hold_off_again(self) -> None:
        from common import input_registry

        self.assertEqual(
            input_registry.with_hold("chord(key:a+key:b)@hold:1500", 0),
            "chord(key:a+key:b)")

    def test_a_binding_with_no_hold_says_nothing_rather_than_zero(self) -> None:
        from common import input_registry

        self.assertEqual(input_registry.hold_ms("key:a"), 0)


class RawControlsAreDeclared(unittest.TestCase):
    def test_no_module_grows_one_unnoticed(self) -> None:
        found = {}
        for path in sorted(CONSOLE.glob("*.py")):
            if path.name == "panel.py":
                continue
            count = len(CONTROLS.findall(path.read_text(encoding="utf-8")))
            if count:
                found[path.name] = count

        expected = {name: count for name, (count, _why) in BUDGET.items()}
        self.assertEqual(found, expected,
                         "a control outside panel.py is a decision - either draw it "
                         "with panel, or add it to BUDGET with what it is for")


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
