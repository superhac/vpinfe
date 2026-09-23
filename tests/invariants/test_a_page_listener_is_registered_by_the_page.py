"""A page-level listener is registered by the page function itself, never from a handler
or a helper."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOT_SOURCE = {"tests", ".venv", ".git", "node_modules"}

LATE_TODAY = frozenset({("managerui/pages/dnd_drop_zone.py", "create_drop_zone")})


def _registers(call: ast.Call) -> bool:
    """`ui.on(...)`, or `.on(...)` on a page's layout: both add to the page's own set."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "on":
        return False
    owner = func.value
    return (isinstance(owner, ast.Name) and owner.id == "ui") \
        or (isinstance(owner, ast.Attribute) and owner.attr == "layout")


def _is_page(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == "page" \
           and isinstance(target.value, ast.Name) and target.value.id == "ui":
            return True
    return False


class _Registrations(ast.NodeVisitor):
    """Each registration, and whether the function it sits directly in is a page."""

    def __init__(self) -> None:
        self.enclosing: list[ast.AST] = []
        self.found: list[tuple[int, str, bool]] = []

    def _inside(self, node: ast.AST) -> None:
        self.enclosing.append(node)
        self.generic_visit(node)
        self.enclosing.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._inside(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._inside(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._inside(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _registers(node):
            inner = self.enclosing[-1] if self.enclosing else None
            name = "<module>" if inner is None else getattr(inner, "name", "<lambda>")
            self.found.append((node.lineno, name, inner is not None and _is_page(inner)))
        self.generic_visit(node)


def _registrations(tree: ast.AST) -> list[tuple[int, str, bool]]:
    seen = _Registrations()
    seen.visit(tree)
    return seen.found


def _tree() -> list[tuple[str, int, str, bool]]:
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        where = path.relative_to(ROOT)
        if where.parts[0] in NOT_SOURCE or "__pycache__" in where.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found += [(str(where), *one) for one in _registrations(tree)]
    return found


class PageListeners(unittest.TestCase):
    def setUp(self) -> None:
        self.found = _tree()

    def test_every_one_is_registered_directly_by_its_page(self) -> None:
        late = [f"{where}:{line} in {name}" for where, line, name, by_page in self.found
                if not by_page and (where, name) not in LATE_TODAY]

        self.assertEqual(late, [], "register it in the page function, reach it through state")

    def test_the_named_ones_are_still_there(self) -> None:
        still = {(where, name) for where, _line, name, by_page in self.found if not by_page}

        self.assertEqual(sorted(LATE_TODAY - still), [], "take these off LATE_TODAY")

    def test_it_found_the_pages_own(self) -> None:
        """An empty sweep passes and measures nothing, which reads the same as clean."""
        self.assertGreaterEqual(sum(by_page for *_, by_page in self.found), 10)

    def test_a_handler_a_lambda_and_a_helper_are_each_refused(self) -> None:
        tree = ast.parse('@ui.page("/x")\n'
                         'async def page():\n'
                         '    ui.on("a", go)\n'
                         '    ui.context.client.layout.on("b", go)\n'
                         '    def later():\n'
                         '        ui.on("c", go)\n'
                         '    ui.on("d", lambda e: ui.on("e", go))\n'
                         '    button.on("click", go)\n'
                         'def helper():\n'
                         '    ui.on("f", go)\n')

        self.assertEqual([(name, by_page) for _line, name, by_page in _registrations(tree)],
                         [("page", True), ("page", True), ("later", False),
                          ("page", True), ("<lambda>", False), ("helper", False)])


if __name__ == "__main__":
    unittest.main()
