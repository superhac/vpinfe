"""Every module we import is a module that exists.

Renaming a module and missing one of its importers is not a test failure - the suite
never imports `main.py`, so the entry point can be broken while 992 tests pass. That is
exactly what happened when `clioptions.py` became `cli_options.py`: the app could not
start at all, and the first thing to notice was the cabinet.

This reads the import statements rather than executing them, so it covers `main.py` and
everything else the suite cannot import for its side effects.
"""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Our own packages, plus the vendored drop we do not lint or own.
SKIP_DIRS = {".venv", "build", "third-party", "chromium", "web", "tests", "__pycache__"}
VENDORED = {"managerui/maps"}


def _source_files():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if any(str(rel).startswith(v) for v in VENDORED):
            continue
        yield path, rel


def _is_ours(name: str) -> bool:
    return (REPO_ROOT / f"{name}.py").exists() or (REPO_ROOT / name).is_dir()


class ImportsResolveTests(unittest.TestCase):
    def test_every_imported_module_exists(self) -> None:
        missing = []
        for path, rel in _source_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                self.fail(f"{rel} does not parse: {exc}")
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                else:
                    continue
                for name in names:
                    if _is_ours(name) or importlib.util.find_spec(name) is not None:
                        continue
                    missing.append(f"{rel}:{node.lineno} imports '{name}'")

        self.assertEqual(missing, [], "imports that name nothing:\n" + "\n".join(missing))


if __name__ == "__main__":
    unittest.main()
