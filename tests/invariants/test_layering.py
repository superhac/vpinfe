"""Which package may import which, asserted rather than remembered.

`docs/common.md` says nothing in `common/` may import a domain package above it, and
`docs/managerui.md` says the Manager UI is one consumer of the shared services rather
than their owner. Neither was checked, and both had drifted: `httpapi` reached into
`managerui.services` at nine sites for game, archive, upload and asset logic, and
`managerui` reached into `frontend` at five for the things one install does to another.

Nothing in either direction was deliberate - they are what happens when a rule lives
only in prose. This file is the check, so the next one fails here instead of being
found by reading.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent

# `common/host/` is the device's own package, so a frontend import inside it is a
# device-to-device edge rather than a layering break. It predates this rule and is
# listed so that a *new* one still fails.
ALLOWED = {
    ("common/host/display_service.py", "frontend"),
    # The local resolution of the device client: deferred inside functions so that
    # importing it does not pull the frontend into an install that has no frontend.
    ("common/device_client.py", "frontend"),
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
        on it - otherwise a library install has to ship a frontend to import a game."""
        self.assertEqual(_offenders("common", {"managerui", "httpapi", "frontend"}), [])

    def test_the_infrastructure_layer_does_not_import_a_domain_package(self) -> None:
        """`docs/common.md`: nothing in `common/` itself may import `games`, `online` or
        `host`. Only the top level - the domain packages may of course import each other.

        Two are grandfathered, both because the thing they reach for is genuinely about
        that domain. A third would mean a generic helper filed in the wrong place, which
        is what `common/atomic_write.py` exists to have fixed.
        """
        allowed = {("config_store.py", "common.games.info_migration"),   # .info backups
                   ("install_identity.py", "common.games.ids")}          # the id alphabet
        domains = {"games", "online", "host"}
        found = set()
        # `_imports` reports the top-level package only; the full dotted name is what
        # distinguishes `common.games` from `common.paths`, so this walks it directly.
        for path in sorted((REPO / "common").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                elif isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                for name in names:
                    parts = name.split(".")
                    if len(parts) >= 2 and parts[0] == "common" and parts[1] in domains:
                        found.add((path.name, name))

        self.assertEqual(sorted(found - allowed), [])

    def test_the_api_does_not_reach_into_a_user_interface(self) -> None:
        """Business logic under a UI package makes that UI privileged: a replacement
        would import the incumbent, which is a skin rather than a replacement."""
        self.assertEqual(_offenders("httpapi", {"managerui"}), [])

    def test_a_user_interface_does_not_reach_into_the_device(self) -> None:
        """What the Manager UI does *to* a device goes through `common.device_client`,
        which is one interface whether that device is local or another machine."""
        self.assertEqual(_offenders("managerui", {"frontend"}), [])

    def test_the_allowlist_only_names_files_that_exist(self) -> None:
        """A stale entry silently permits whatever moves into that path."""
        missing = sorted(name for name, _ in ALLOWED if not (REPO / name).exists())
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
