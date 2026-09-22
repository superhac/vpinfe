"""A grid's context menu never opens with nothing in it.

`grid.build` installs a client-side guard; these fail when something escapes it.

**What this cannot prove:** that the guard itself works. That needs a browser.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

CONSOLE = pathlib.Path(__file__).resolve().parent.parent.parent / "console"
GUARD = "_suppress_empty_menu"


def _calls(tree: ast.AST, attr: str) -> list[ast.Call]:
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == attr]


def _function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    return next((node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef) and node.name == name), None)


class ContextMenusAreGuarded(unittest.TestCase):
    def test_build_installs_the_guard(self) -> None:
        source = (CONSOLE / "grid.py").read_text(encoding="utf-8")
        built = _function(ast.parse(source), "build")
        self.assertIsNotNone(built, "console/grid.py no longer defines build()")
        called = {getattr(node.func, "id", "") or getattr(node.func, "attr", "")
                  for node in ast.walk(built) if isinstance(node, ast.Call)}
        self.assertIn(GUARD, called, f"grid.build no longer calls {GUARD}")

    def test_the_guard_runs_in_the_browser_at_capture(self) -> None:
        source = (CONSOLE / "grid.py").read_text(encoding="utf-8")
        guard = _function(ast.parse(source), GUARD)
        self.assertIsNotNone(guard, f"console/grid.py no longer defines {GUARD}()")
        self.assertTrue(_calls(guard, "run_javascript"),
                        f"{GUARD} no longer runs in the browser")
        self.assertIn("}, true);", ast.get_source_segment(source, guard) or "",
                      f"{GUARD}'s listener is no longer on the capture phase")

    def test_every_context_menu_belongs_to_a_built_grid(self) -> None:
        """Module-level: the menu is created beside the grid it serves, never by it."""
        stray: list[str] = []
        for path in sorted(CONSOLE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if _calls(tree, "context_menu") and not _calls(tree, "build"):
                stray.append(path.name)
        self.assertEqual([], stray, f"context menus built outside grid.build: {stray}")


if __name__ == "__main__":
    unittest.main()
