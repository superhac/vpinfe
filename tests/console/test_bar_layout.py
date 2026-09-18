"""The bar above a grid keeps its two rows in order."""

from __future__ import annotations

import ast
import pathlib
import unittest

CONSOLE = pathlib.Path(__file__).resolve().parent.parent.parent / "console"
KEY = "console-tier-key"


def _ends(tree: ast.AST) -> list[ast.With]:
    """Every `with ... panel.bar_end():` block - the right-aligned end of a row."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            call = item.context_expr
            if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "bar_end":
                found.append(node)
                break
    return found


def _classes_named(node: ast.AST, wanted: str) -> bool:
    return any(isinstance(inner, ast.Constant) and isinstance(inner.value, str)
               and wanted in inner.value
               for inner in ast.walk(node))


class TheKeyIsNotAnAction(unittest.TestCase):
    """A key to a view's marks is drawn on the description line, not in the end."""

    def test_no_key_in_a_row_end(self):
        wrong = []
        for path in sorted(CONSOLE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for end in _ends(tree):
                if _classes_named(end, KEY):
                    wrong.append(f"console/{path.name}:{end.lineno}: a mark key drawn "
                                 "in a bar's right-aligned end")
        self.assertEqual(wrong, [], "\n" + "\n".join(wrong))

    def test_it_found_the_keys_and_the_ends(self):
        """An empty sweep passes and measures nothing, which reads the same as clean."""
        source = "\n".join(p.read_text(encoding="utf-8")
                           for p in CONSOLE.glob("*.py"))
        self.assertGreater(source.count(KEY), 1)
        self.assertGreater(sum(len(_ends(ast.parse(p.read_text(encoding="utf-8"))))
                               for p in CONSOLE.glob("*.py")), 5)


if __name__ == "__main__":
    unittest.main()
