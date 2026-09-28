"""A `dir` field always draws Browse beside its input."""

from __future__ import annotations

import ast
import pathlib
import unittest

from tests.support import trees

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
CONSOLE = REPO / "console"


def _dir_fields_without_browse(tree: ast.Module) -> list[int]:
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "path_field"):
            continue
        wants = next((kw.value for kw in node.keywords if kw.arg == "wants"), None)
        if not (isinstance(wants, ast.Constant) and wants.value == "dir"):
            continue
        if not any(kw.arg == "browse" for kw in node.keywords):
            found.append(node.lineno)
    return found


class TestFolderFieldsOfferBrowse(unittest.TestCase):
    def test_every_dir_field_carries_browse(self) -> None:
        offenders = []
        for path in sorted(CONSOLE.rglob("*.py")):
            for line in _dir_fields_without_browse(trees.tree_for(path)):
                offenders.append(f"{path.relative_to(REPO)}:{line}")
        self.assertEqual(offenders, [], "give it browse=, so typing is not the only way in")

    def test_the_check_flags_one_with_no_browse_and_passes_one_with_it(self) -> None:
        flagged = trees.parse_snippet('panel.path_field(wants="dir")\n')
        cleared = trees.parse_snippet('panel.path_field(wants="dir", browse=library.folders)\n')

        self.assertEqual(_dir_fields_without_browse(flagged), [1])
        self.assertEqual(_dir_fields_without_browse(cleared), [])


if __name__ == "__main__":
    unittest.main()
