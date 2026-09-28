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
import inspect
import pathlib
import unittest

from tests.support import trees

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
    for node in ast.walk(trees.tree_for(path)):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
    return found


# The extension store's calls about one extension, which take its name first, and the
# ones about the store as a whole. Every public method is in one or the other - a test
# below holds that - so a new one has to be placed before this check can pass.
STORE_CALLS_NAMING_AN_EXTENSION = {"enabled", "set_enabled", "settings", "set_setting",
                                   "forget"}
STORE_CALLS_ABOUT_THE_STORE = {"migrations", "mark_migration"}


def _names_handed_to_the_store(tree: ast.Module) -> list[tuple[int, str]]:
    """(line, name) for each store call given an extension's name as a string, written
    at the call or held in a module-level constant. A name passed through a variable is
    the host's business: it is handed the names of whatever is installed."""
    methods = STORE_CALLS_NAMING_AN_EXTENSION
    constants = {target.id: node.value.value for node in tree.body
                 if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                 and isinstance(node.value.value, str)
                 for target in node.targets if isinstance(target, ast.Name)}
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in methods):
            continue
        given = node.args[:1] + [kw.value for kw in node.keywords if kw.arg == "name"]
        for argument in given:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.append((node.lineno, argument.value))
            elif isinstance(argument, ast.Name) and argument.id in constants:
                found.append((node.lineno, constants[argument.id]))
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
            tree = trees.tree_for(path)
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

    def test_common_names_no_extension_to_the_extension_store(self) -> None:
        """An extension's settings are its own. Core reading one by name makes a core
        fact live in an extension, and it goes wrong the moment that extension is off."""
        found = []
        for path in sorted((REPO / "common").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(REPO).as_posix()
            found += [f"{relative}:{line} names {name!r}"
                      for line, name in _names_handed_to_the_store(trees.tree_for(path))]
        self.assertEqual(found, [])

    def test_the_store_check_sees_a_name_written_either_way(self) -> None:
        tree = trees.parse_snippet(
            "OWNER = 'somebody'\n"
            "get_extension_store().settings('somebody')\n"
            "store.set_setting(OWNER, 'key', 'value')\n"
            "store.enabled(name='somebody')\n"
            "store.settings(extension)\n")

        self.assertEqual(_names_handed_to_the_store(tree),
                         [(2, "somebody"), (3, "somebody"), (4, "somebody")])

    def test_every_store_call_is_placed(self) -> None:
        from common.extensions.store import ExtensionStore

        public = {name for name, _ in inspect.getmembers(ExtensionStore, inspect.isfunction)
                  if not name.startswith("_")}
        self.assertEqual(public - STORE_CALLS_NAMING_AN_EXTENSION
                         - STORE_CALLS_ABOUT_THE_STORE, set())

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
