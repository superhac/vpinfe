"""A field type is drawn in one place and named in one place, and they agree.

docs/extensions.md's field table is what an extension author reads before writing
`fields`; `console/wizard.FIELD_TYPES` is what the Console actually draws. This fails the
moment the two lists differ, in either direction.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from console import wizard

REPO = Path(__file__).resolve().parent.parent.parent
DOC = REPO / "docs" / "extensions.md"

# A row's first cell, backtick-quoted, under the "type" heading - `| `path` | a file or
# folder ... |`. Matched from the table itself, not the surrounding prose, so a type
# named in passing elsewhere in the doc is not mistaken for one that is documented.
TABLE = re.compile(r"\|\s*type\s*\|\s*asks for\s*\|\n\|[-|\s]+\|\n((?:\|.+\|\n)+)")
ROW_TYPE = re.compile(r"^\|\s*`([a-z]+)`\s*\|")


def _documented() -> set[str] | None:
    text = DOC.read_text(encoding="utf-8")
    match = TABLE.search(text)
    if not match:
        return None
    return {found.group(1) for line in match.group(1).splitlines()
            if (found := ROW_TYPE.match(line))}


class FieldTypesAreOneListTests(unittest.TestCase):
    def test_the_docs_and_the_renderer_name_the_same_types(self) -> None:
        documented = _documented()
        self.assertIsNotNone(documented, "docs/extensions.md has no field-type table")
        drawn = set(wizard.FIELD_TYPES)

        self.assertEqual(documented, drawn,
                         f"docs/extensions.md names {documented - drawn or '{}'} that "
                         f"wizard.FIELD_TYPES does not draw, and wizard.FIELD_TYPES draws "
                         f"{drawn - documented or '{}'} the docs never mention")

    def test_the_table_itself_can_be_found(self) -> None:
        """The regex that reads the table, proven against a table shaped like the real
        one - so a reformatting that breaks the match fails here, not silently."""
        sample = ("intro\n\n| type | asks for |\n|---|---|\n"
                  "| `string` | a line of text |\n| `path` | a folder |\n\nmore prose\n")
        match = TABLE.search(sample)
        self.assertIsNotNone(match)
        rows = {found.group(1) for line in match.group(1).splitlines()
               if (found := ROW_TYPE.match(line))}
        self.assertEqual(rows, {"string", "path"})


if __name__ == "__main__":
    unittest.main()
