"""A picture beside a name is drawn by `console/list_art.py` and nowhere else.

Every list shows one frame: one size, one ground, the row's own glyph where there is no
picture. The address inside it is `console/art.py`'s, which
`test_art_addresses_go_through_one_helper.py` holds to; this holds the frame.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
CONSOLE = REPO / "console"
HELPER = CONSOLE / "list_art.py"

# The frame's own classes. The stylesheet styles them, and only the helper writes them.
FRAME_CLASSES = ("console-cell-pictured", "console-cell-art-box", "console-cell-noart")


def _fragments(source: str) -> list[tuple[int, str]]:
    return [(node.lineno, node.value) for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _frames(path: pathlib.Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    pieces = (_fragments(source) if path.suffix == ".py"
              else list(enumerate(source.splitlines(), 1)))
    return [f"{path.relative_to(REPO)}:{line}" for line, text in pieces
            if any(name in text for name in FRAME_CLASSES)]


class ListArtIsDrawnOnceTests(unittest.TestCase):
    def test_no_console_module_draws_a_name_picture(self) -> None:
        offenders = []
        for path in sorted([*CONSOLE.rglob("*.py"), *CONSOLE.rglob("*.js")]):
            if path != HELPER:
                offenders += _frames(path)
        self.assertEqual(offenders, [], "draw it with console/list_art.py")

    def test_the_scan_finds_each_of_the_helper_s_classes(self) -> None:
        """Or a scan that matches nothing would pass the test above as well."""
        source = HELPER.read_text(encoding="utf-8")
        written = " ".join(text for _line, text in _fragments(source))
        for name in FRAME_CLASSES:
            with self.subTest(name=name):
                self.assertIn(name, written)


if __name__ == "__main__":
    unittest.main()
