"""Every menu item in the Console takes the menu treatment.

One menu is one language: a row's context menu, a column's, the view's and the actions on
a selection all read alike, or the odd one out reads as a different kind of thing.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

CONSOLE = pathlib.Path(__file__).resolve().parent.parent.parent / "console"
DRAWN = ("menu_item", "item_label")
TREATMENT = "console-menu"


def _dressed_calls(tree: ast.AST) -> set[int]:
    """The menu calls that are the receiver of a `.classes(...)` naming the treatment.

    Walked from the `.classes` call down its own chain, rather than by reading nearby
    lines: a bare item sitting beside a dressed one passes any window wide enough to
    hold both.
    """
    dressed: set[int] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "attr", "") == "classes"):
            continue
        # A class list built above the call is still a class list; only a literal that
        # names something else is a miss.
        literal = [a for a in node.args
                   if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if literal and not any(TREATMENT in a.value for a in literal):
            continue
        inner = node.func.value
        while isinstance(inner, ast.Call):
            if getattr(inner.func, "attr", "") in DRAWN:
                dressed.add(id(inner))
                break
            inner = inner.func.value if isinstance(inner.func, ast.Attribute) else inner
            if not isinstance(inner, ast.Call | ast.Attribute):
                break
    return dressed


def _bare() -> list[str]:
    out = []
    for path in sorted(CONSOLE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        dressed = _dressed_calls(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", "") in DRAWN
                    and id(node) not in dressed):
                out.append(f"console/{path.name}:{node.lineno}: a menu item with no "
                           "menu treatment")
    return out


class MenuItemsAreDressed(unittest.TestCase):

    def test_none_is_bare(self):
        bare = _bare()
        self.assertEqual(bare, [], "\n" + "\n".join(bare))

    def test_it_found_the_menus(self):
        """An empty sweep passes and measures nothing, which reads the same as clean."""
        seen = sum(
            1
            for path in CONSOLE.glob("*.py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in DRAWN)
        self.assertGreater(seen, 30)


if __name__ == "__main__":
    unittest.main()
