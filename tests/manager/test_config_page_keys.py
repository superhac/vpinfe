"""Every setting the Manager UI names by hand still lives where it says it does.

Two migrations moved settings out from under this code. The snake_case rename changed
the spellings, and the [Displays] split gave each window its own section. Both kept every
*read* working through aliases, which is why neither was noticed: what broke is the code
that names a setting to decide something - `key in options` to sort keys into cards,
`section == x and key == y` to pick a control. An alias cannot rescue a membership test,
so those silently stopped matching.

The damage was always the same shape. Nothing raised, nothing logged, and the page still
rendered - just as one column instead of two, or with a monitor picker degraded to a text
box that wants an ID the user has no way to look up.

So rather than pin a list of names, these tests find the (section, key) pairs the source
actually names and ask the schema whether each one still exists.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from common.config_schema import CONFIG_OPTIONS, canonical_section, locate

MANAGER_UI = Path(__file__).resolve().parents[2] / "managerui"

# Sections that are not ours: VPX's own ini, which we render but do not own.
FOREIGN_SECTIONS = {"DefaultCamera", "TableOverride", "DMD", "Alpha", "Standalone"}


def _live_pairs() -> set[tuple[str, str]]:
    return {(option.section, option.key) for option in CONFIG_OPTIONS}


def _named_pairs(tree: ast.AST) -> set[tuple[str, str]]:
    """(section, key) pairs a `section == ... and key == ...` test names together."""
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.BoolOp):
            continue
        sections: list[str] = []
        keys: list[str] = []
        for part in ast.walk(node):
            if not isinstance(part, ast.Compare):
                continue
            name = getattr(part.left, "id", getattr(part.left, "attr", ""))
            if name not in ("section", "key"):
                continue
            target = sections if name == "section" else keys
            for comparator in part.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    target.append(comparator.value)
                elif isinstance(comparator, (ast.Tuple, ast.List, ast.Set)):
                    target += [
                        element.value for element in comparator.elts
                        if isinstance(element, ast.Constant) and isinstance(element.value, str)
                    ]
        found.update((section, key) for section in sections for key in keys)
    return found


class ManagerUiConfigKeyTests(unittest.TestCase):
    def test_named_section_key_pairs_still_exist(self) -> None:
        live = _live_pairs()
        stale = []
        for path in sorted(MANAGER_UI.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for section, key in sorted(_named_pairs(tree)):
                if section in FOREIGN_SECTIONS or (section, key) in live:
                    continue
                moved = locate(section, key)
                if moved and moved != (section, key):
                    stale.append(f"{path.name}: {section}.{key} now lives at {moved}")
        self.assertEqual(stale, [], "Manager UI names settings that have moved: " + str(stale))

    def test_section_presentation_maps_use_live_names(self) -> None:
        """An icon or blurb keyed by a name no section has silently falls back."""
        from managerui.pages.vpinfe_config import SECTION_DESCRIPTIONS, SECTION_ICONS
        live_sections = {option.section for option in CONFIG_OPTIONS}
        for label, mapping in (("SECTION_ICONS", SECTION_ICONS),
                               ("SECTION_DESCRIPTIONS", SECTION_DESCRIPTIONS)):
            for section in mapping:
                with self.subTest(map=label, section=section):
                    self.assertIn(section, live_sections)
                    self.assertEqual(canonical_section(section), section)

    def test_repeated_keys_are_labelled_per_section(self) -> None:
        """A key that exists in several sections needs the section to be named right."""
        from managerui.config_options import get_friendly_name
        seen: dict[str, set[str]] = {}
        for option in CONFIG_OPTIONS:
            seen.setdefault(option.key, set()).add(option.section)
        for key, sections in seen.items():
            if len(sections) < 2:
                continue
            for section in sections:
                with self.subTest(section=section, key=key):
                    expected = next(o.label for o in CONFIG_OPTIONS
                                    if o.section == section and o.key == key)
                    if expected:
                        self.assertEqual(get_friendly_name(key, section), expected)

    def test_input_mapping_order_covers_the_real_actions(self) -> None:
        """The order list sorts nothing for an action it spells differently."""
        from common.input_registry import INPUT_ACTIONS
        from managerui.config_fields import INPUT_MAPPING_ACTION_ORDER
        self.assertEqual(sorted(INPUT_MAPPING_ACTION_ORDER),
                         sorted(action.name for action in INPUT_ACTIONS))
