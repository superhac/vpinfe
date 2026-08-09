"""Which package may import which, asserted rather than remembered.

`docs/common.md` says nothing in `common/` may import a domain package above it, and
`docs/managerui.md` says the Manager UI is one consumer of the shared services rather
than their owner. Neither was checked, and both had drifted: `httpapi` reached into
`managerui.services` at nine sites for game, archive, upload and asset logic, and
`managerui` reached into `frontend` at five for the things a hub does to a player.

Nothing in either direction was deliberate - they are what happens when a rule lives
only in prose. This file is the check, so the next one fails here instead of being
found by reading.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent

# `common/host/` is the player's own package, so a frontend import inside it is a
# player-to-player edge rather than a layering break. It predates this rule and is
# listed so that a *new* one still fails.
ALLOWED = {
    ("common/host/display_service.py", "frontend"),
    # The local resolution of the player client: deferred inside functions so that
    # importing it does not pull the frontend into a hub-only install.
    ("common/player_client.py", "frontend"),
}


def _imports(path: pathlib.Path) -> set[str]:
    """Every top-level package this module imports, however it spells it."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
    return found


def _offenders(package: str, forbidden: set[str]) -> list[str]:
    out = []
    for path in sorted((REPO / package).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(REPO).as_posix()
        for imported in sorted(_imports(path) & forbidden):
            if (relative, imported) not in ALLOWED:
                out.append(f"{relative} imports {imported}")
    return out


class LayeringTests(unittest.TestCase):
    def test_common_does_not_import_the_packages_above_it(self) -> None:
        """Anything may depend on `common/`, so it may depend on nothing that depends
        on it - otherwise a hub install has to ship a frontend to import a game."""
        self.assertEqual(_offenders("common", {"managerui", "httpapi", "frontend"}), [])

    def test_the_api_does_not_reach_into_a_user_interface(self) -> None:
        """Business logic under a UI package makes that UI privileged: a replacement
        would import the incumbent, which is a skin rather than a replacement."""
        self.assertEqual(_offenders("httpapi", {"managerui"}), [])

    def test_a_user_interface_does_not_reach_into_the_player(self) -> None:
        """What the Manager UI does *to* a player goes through `common.player_client`,
        which is one interface whether that player is local or another machine."""
        self.assertEqual(_offenders("managerui", {"frontend"}), [])

    def test_the_allowlist_only_names_files_that_exist(self) -> None:
        """A stale entry silently permits whatever moves into that path."""
        missing = sorted(name for name, _ in ALLOWED if not (REPO / name).exists())
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
