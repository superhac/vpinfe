"""Every `<owner>/static/` directory is one the build actually ships.

`docs/conventions.md` says a directory added under an owner's `static/` must also reach
`packaging/vpinfe.spec`, and said in the same breath that no test covered it. That is the
worst shape for a rule: the failure is a missing image in a release artifact, found by a
person looking at a cabinet, and never by a red suite.

The spec lists roots and PyInstaller takes each one whole, so a new subdirectory under an
existing root needs nothing. What needs saying is a new *owner* - the Console's own
`static/` was exactly that, and it arrived after this rule was written.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
SPEC = REPO / "packaging" / "vpinfe.spec"


def _declared_roots() -> set[str]:
    """The DATA_ROOTS list out of the spec, read rather than imported.

    The spec is a PyInstaller script and running it needs PyInstaller's own globals, so
    this parses it instead of importing it.
    """
    tree = ast.parse(SPEC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if "DATA_ROOTS" not in names:
            continue
        return {
            element.value for element in node.value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
    raise AssertionError("packaging/vpinfe.spec no longer declares DATA_ROOTS")


def _static_dirs_in_tree() -> set[str]:
    """Every directory named `static` that holds a file we ship."""
    found = set()
    for path in REPO.rglob("static"):
        if not path.is_dir():
            continue
        relative = path.relative_to(REPO).as_posix()
        if relative.startswith((".", "third-party/", "third_party/", "chromium/", "web/")):
            continue
        if "node_modules" in relative or "__pycache__" in relative:
            continue
        found.add(relative)
    return found


class BuildDataTests(unittest.TestCase):
    def test_every_static_directory_is_one_the_build_ships(self) -> None:
        """A static directory the spec does not name is simply absent from a release,
        and nothing else reports that."""
        declared = _declared_roots()
        missing = sorted(
            directory for directory in _static_dirs_in_tree()
            if not any(directory == root or directory.startswith(f"{root}/")
                       for root in declared)
        )
        self.assertEqual(missing, [])

    def test_the_spec_names_nothing_that_has_gone(self) -> None:
        """A root that no longer exists means the build copies nothing and says nothing.

        `third_party/` is not in a checkout: it is gitignored and the fetch scripts fill it
        before PyInstaller runs, so it is absent here and present in a build.
        """
        gone = sorted(
            root for root in _declared_roots()
            if not root.startswith("third_party/") and not (REPO / root).exists()
        )
        self.assertEqual(gone, [])

    def test_the_checker_can_actually_fail(self) -> None:
        """It reads the spec rather than trusting a constant, so prove it reads one."""
        declared = _declared_roots()
        self.assertIn("frontend/static", declared)
        self.assertNotIn("nothing/static", declared)
