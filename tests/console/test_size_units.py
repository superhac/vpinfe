"""A byte count on screen, written by `i18n.size` and nothing else."""

import ast
import re
import unittest
from pathlib import Path

from common import i18n

KB, MB, GB, TB = 1024, 1024**2, 1024**3, 1024**4
CONSOLE = Path(__file__).resolve().parents[2] / "console"


class SizeUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("en")

    def test_each_unit_starts_at_its_boundary(self) -> None:
        for count, said in ((0, "0 B"), (1023, "1023 B"), (KB, "1.0 KB"), (MB, "1.0 MB"),
                            (GB, "1.0 GB"), (TB, "1.0 TB"), (10**21, "909494701.8 TB")):
            self.assertEqual(said, i18n.size(count), count)

    def test_the_unit_is_the_languages(self) -> None:
        i18n.set_language("qps")
        self.assertEqual(i18n.t("size.megabytes", value="1.5"), i18n.size(MB + MB // 2))
        self.assertNotEqual("1.5 MB", i18n.size(MB + MB // 2))

    def test_nothing_else_in_the_console_writes_a_unit(self) -> None:
        unit = re.compile(r"^\s*B$|\b[KMGT]B\b")
        found = sorted(path.name for path in CONSOLE.glob("*.py")
                       if any(unit.search(one) for one in _literals(path)))
        self.assertEqual([], found)


def _literals(path: Path) -> list[str]:
    """Every string the module could put on screen: its constants, docstrings aside."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = {id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docs]


if __name__ == "__main__":
    unittest.main()
