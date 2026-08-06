"""Every setting the code reads is a setting the schema declares.

`config_schema` says it holds every setting VPinFE has, and the store fills a new file
from it - so a setting the schema does not know about is never written, never offered in
the Manager UI, and never covered by the naming and alias checks either. Two had already
slipped through that way, `assets_dir` and `wheelset`, both live and both documented.

Read from the source rather than by importing, so a call site behind a branch or an
optional dependency counts the same as one on the happy path.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from common import config_schema

REPO = Path(__file__).resolve().parent.parent.parent
READERS = {"cfg_get", "cfg_bool", "cfg_int", "cfg_list", "cfg_set"}

# Sections whose keys are declared elsewhere and resolved at runtime, so a literal here
# is a name in that vocabulary rather than a schema key.
GENERATED_SECTIONS = {"input"}


def _call_sites():
    """(file, line, section, key) for every reader called with both names literal."""
    for path in sorted(REPO.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith((".venv/", "tests/", "third-party/", "managerui/maps/")):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 3:
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in READERS:
                continue
            section, key = node.args[1], node.args[2]
            if not (isinstance(section, ast.Constant) and isinstance(key, ast.Constant)):
                continue
            if isinstance(section.value, str) and isinstance(key.value, str):
                yield rel, node.lineno, section.value, key.value


class CallSiteTests(unittest.TestCase):
    def test_every_setting_read_is_one_the_schema_declares(self) -> None:
        unknown = []
        for rel, line, section, key in _call_sites():
            if config_schema.canonical_section(section) in GENERATED_SECTIONS:
                continue
            resolved = config_schema.locate(section, key)
            if config_schema.option(*resolved) is None:
                unknown.append(f"{rel}:{line} reads {section}.{key}")
        self.assertEqual(sorted(unknown), [],
                         "declare it in config_schema, or it is written to no file and "
                         "offered in no UI")

    def test_there_are_call_sites_to_check(self) -> None:
        """The scan is a regex-shaped thing; an empty result would pass silently."""
        self.assertGreater(len(list(_call_sites())), 20)


if __name__ == "__main__":
    unittest.main()
