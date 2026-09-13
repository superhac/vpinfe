"""An extension may import the contract, the standard library, and what it declares.

Python will not stop one under `extensions/` importing `game_service` and reaching past
the context it was handed, which is the whole guarantee. Nothing at runtime can make that
impossible, so the boundary is a test - the same way every route is made to declare a
scope, and the same way `tests/apps/test_app_boundary.py` holds the app contract.

It matters most for the ones we write. A first-party extension with a private hook would
advertise a surface that does not work for anybody else.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import unittest

EXTENSIONS_DIR = pathlib.Path(__file__).resolve().parents[2] / "extensions"

# The one module of ours an extension may import: the manifest types and the ABI. Its
# reach into everything else is the context, which is handed to it and imported from
# nowhere.
CONTRACT = "common.extensions.contract"

FIRST_PARTY = frozenset({"apps", "common", "console", "extensions", "frontend",
                         "httpapi", "managerui", "tests"})

# Third-party an extension may use, one line per library, because adding a dependency to
# an extension should be a decision somebody made rather than one nobody saw.
ALLOWED_THIRD_PARTY = frozenset({
    "fastapi",      # ctx.add_router takes an APIRouter
})

STDLIB = frozenset(sys.stdlib_module_names)


def _imports(tree: ast.AST) -> list[str]:
    """Every module an import names, dotted and absolute. A relative import resolves
    inside the extension itself and carries no module name to check."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append(node.module)
    return found


def _sources() -> list[pathlib.Path]:
    return sorted(path for path in EXTENSIONS_DIR.rglob("*.py")
                  if "__pycache__" not in path.parts)


class ImportBoundaryTests(unittest.TestCase):
    def test_there_are_extensions_to_check(self) -> None:
        """A boundary test over an empty directory passes and means nothing."""
        self.assertTrue(_sources(), f"No extension sources under {EXTENSIONS_DIR}")

    def test_an_extension_imports_the_contract_and_nothing_else_of_ours(self) -> None:
        for source in _sources():
            tree = ast.parse(source.read_text(encoding="utf-8"), str(source))
            for module in _imports(tree):
                root = module.split(".")[0]
                if root in STDLIB or root in ALLOWED_THIRD_PARTY:
                    continue
                if module == CONTRACT or module.startswith(f"{CONTRACT}."):
                    continue
                with self.subTest(source=source.name, module=module):
                    self.assertNotIn(root, FIRST_PARTY,
                                     f"{source.relative_to(EXTENSIONS_DIR)} imports "
                                     f"{module}; an extension reaches core through the "
                                     f"context it is given, or through {CONTRACT}")


if __name__ == "__main__":
    unittest.main()
