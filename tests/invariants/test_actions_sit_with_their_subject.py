"""An action sits with what it acts on, never under a heading that says "Actions".

The placement rule is `docs/conventions.md`, "An action sits with what it acts on". What
this reads is its residue: a section or heading named for the mechanism, a subject whose
panel menu and grid menu are drawn from different lists, and buttons built by hand
instead of through `panel.py`, which is where a verb's treatment is decided.
"""

from __future__ import annotations

import ast
import json
import pathlib
import unittest

from tests.support import trees

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
CONSOLE = REPO / "console"
CATALOG = REPO / "common" / "i18n" / "catalogs" / "en.json"

# `panel.py` is the ⋮ that opens a subject's verbs.
ACTIONS_WORD_AT = {"panel.py"}

# Every subject with a panel ⋮, and the module whose `acts` its grid row menu draws.
GRID_OF = {
    "tag": "tageditor.py",
    "collection": "collections.py",
    "launcher": "launchers.py",
    "location": "locations.py",
    "theme": "themes.py",
    "device": "devices.py",
}

# Direct `ui.button(` calls outside `panel.py`. A count that only comes down: lower it
# when one moves to a constructor, never raise it.
BUTTON_CEILING = 78


def _tree(path: pathlib.Path) -> ast.Module:
    return trees.tree_for(path)


def _is_ui_call(node: ast.AST, attr: str) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == attr and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ui")


def _subject_verbs() -> set[str]:
    for node in _tree(CONSOLE / "workbench.py").body:
        target = getattr(node, "target", None)
        if isinstance(target, ast.Name) and target.id == "SUBJECT_VERBS" \
                and isinstance(node.value, ast.Dict):
            return {key.value for key in node.value.keys
                    if isinstance(key, ast.Constant)}
    return set()


class TestActionsSitWithTheirSubject(unittest.TestCase):
    def test_no_heading_or_section_is_called_actions(self) -> None:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        spelled = sorted(key for key, value in catalog.items() if value == "Actions")
        self.assertEqual(spelled, ["word.actions"],
                         "name the section for what it holds, or put the verbs in a strip")
        offenders = sorted(path.name for path in CONSOLE.rglob("*.py")
                           if '"word.actions"' in path.read_text(encoding="utf-8")
                           and path.name not in ACTIONS_WORD_AT)
        self.assertEqual(offenders, [])

    def test_no_section_key_is_an_actions_bucket(self) -> None:
        keys = [node.args[0].value
                for node in ast.walk(_tree(CONSOLE / "workbench.py"))
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Section"
                and node.args and isinstance(node.args[0], ast.Constant)]
        self.assertTrue(keys)
        self.assertEqual([key for key in keys if key.endswith("_actions")], [])

    def test_a_subject_menu_and_its_row_menu_share_one_list(self) -> None:
        self.assertEqual(_subject_verbs(), set(GRID_OF))
        for subject, name in GRID_OF.items():
            tree = _tree(CONSOLE / name)
            defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
            called = {node.func.attr for node in ast.walk(tree)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and isinstance(node.func.value, ast.Name)
                      and node.func.value.id == "panel"}
            with self.subTest(subject=subject):
                self.assertIn("acts", defined)
                self.assertIn("verb_menu", called)

    def test_hand_built_buttons_only_come_down(self) -> None:
        count = sum(1 for path in CONSOLE.rglob("*.py") if path.name != "panel.py"
                    for node in ast.walk(_tree(path)) if _is_ui_call(node, "button"))
        self.assertLessEqual(count, BUTTON_CEILING,
                             "build it with panel.action, panel.verb_menu or dialog.footer")
        if count < BUTTON_CEILING:
            self.fail(f"{count} now: lower BUTTON_CEILING to match")


if __name__ == "__main__":
    unittest.main()
