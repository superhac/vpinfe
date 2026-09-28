"""Every button says what pressing it does: `panel.action` and `panel.remote_action`
each carry a `hint=`, drawn as its tooltip, and it is never empty."""

from __future__ import annotations

import ast
import pathlib
import unittest

from tests.support import trees

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
CONSOLE = REPO / "console"

# `_account` and `run_act` are being rewritten in the same window as this sweep; their
# hints are that work's call, not this one's.
EXEMPT_FUNCTIONS = {("players.py", "_account"), ("players.py", "run_act")}


def _sources() -> list[tuple[pathlib.Path, ast.Module]]:
    return [(p, trees.tree_for(p)) for p in sorted(CONSOLE.rglob("*.py"))]


def _action_calls(tree: ast.Module) -> list[ast.Call]:
    got = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if not isinstance(owner, ast.Name) or owner.id != "panel":
            continue
        if node.func.attr in ("action", "remote_action"):
            got.append(node)
    return got


def _enclosing_def_names(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[str]:
    """Every function this node nests inside, walking the whole chain outward."""
    names = []
    at = parents.get(node)
    while at is not None:
        if isinstance(at, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(at.name)
        at = parents.get(at)
    return names


def _excused(path: pathlib.Path, node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    return any((path.name, name) in EXEMPT_FUNCTIONS
              for name in _enclosing_def_names(node, parents))


def _has_hint(node: ast.Call) -> bool:
    hint_kw = next((kw for kw in node.keywords if kw.arg == "hint"), None)
    if hint_kw is None:
        return False
    return not (isinstance(hint_kw.value, ast.Constant) and hint_kw.value.value == "")


class TestEveryButtonSaysWhatPressingItDoes(unittest.TestCase):
    def test_every_action_carries_a_hint(self) -> None:
        offenders = []
        total = 0
        for path, tree in _sources():
            parents = {child: node for node in ast.walk(tree)
                      for child in ast.iter_child_nodes(node)}
            for node in _action_calls(tree):
                total += 1
                if _excused(path, node, parents):
                    continue
                if not _has_hint(node):
                    offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
        self.assertGreater(total, 70)
        self.assertEqual(offenders, [], "give it a hint= that says what pressing it does")


if __name__ == "__main__":
    unittest.main()
