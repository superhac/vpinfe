"""A superseded VPS override is history, not a second place to look up an id.

`alt_vpsid` is a user-typed correction to VPSdb matching: automatic matching got a table
wrong, somebody looked up the right record and said so. Replacing the .vpx it was claimed
against used to delete it outright - which is right about the claim being stale and wrong
about the value being worthless, and the 2.x Manager UI worked around it by rebuilding
before saving so the user's entry would survive.

It is parked now instead of deleted. Nothing resolves through the parked value: every
consumer sees exactly what it saw when this deleted it, so the behavior is unchanged and
the Manager UI can offer it back after 3.0 ships.

That last part is the whole risk. A key sitting beside `alt_vpsid` invites a future reader
to fall back to it "just in case", and the moment anything does, a stale claim is live
again - poisoning collection membership, media matching and the VPinPlay payload, which is
what the deletion existed to prevent. So it is asserted rather than trusted.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from common.games.info_file import ALT_VPSID_PREVIOUS_KEY

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Where the parked value is allowed to be named at all: the module that writes it, and
# whatever surfaces it to a person. Nothing in resolution, matching or any payload.
MAY_NAME_IT = {
    "common/games/info_file.py",          # writes it
}
# Added when the Manager UI grows the confirm-or-discard control it exists for.
MAY_SURFACE_IT: set[str] = set()


def _sources():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        # `.claude/` holds agent worktrees: a second checkout of this repo, not our tree.
        if rel.startswith((".venv/", ".claude/", "tests/", "build/", "third_party/",
                           "managerui/maps/")):
            continue
        yield rel, path


class ParkedOverrideTests(unittest.TestCase):
    def test_nothing_resolves_through_the_parked_value(self) -> None:
        offenders = []
        for rel, path in _sources():
            if rel in MAY_NAME_IT or rel in MAY_SURFACE_IT:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for number, line in enumerate(text.splitlines(), 1):
                if ALT_VPSID_PREVIOUS_KEY in line:
                    offenders.append(f"{rel}:{number}")
        self.assertEqual(offenders, [],
                         "a superseded override must not resolve as an id - add the file "
                         "to MAY_SURFACE_IT only if it shows the value to a person")

    def test_the_allowlist_names_files_that_exist(self) -> None:
        """An entry for a file that has moved would silently stop guarding anything."""
        missing = sorted(name for name in MAY_NAME_IT | MAY_SURFACE_IT
                         if not (REPO_ROOT / name).is_file())
        self.assertEqual(missing, [])

    def test_a_schema_upgrade_carries_it_without_naming_it(self) -> None:
        """info_migration passes unknown vpinfe keys through, so the parked value
        survives an upgrade without that module having to know it exists."""
        from common.games.info_migration import _VPINFE_KEYS
        self.assertNotIn(ALT_VPSID_PREVIOUS_KEY, _VPINFE_KEYS)

    def test_the_writer_is_the_only_one_that_names_it_today(self) -> None:
        """The scan could pass by matching nothing at all."""
        naming = [rel for rel, path in _sources()
                  if ALT_VPSID_PREVIOUS_KEY in path.read_text(encoding="utf-8", errors="ignore")]
        self.assertIn("common/games/info_file.py", naming)


if __name__ == "__main__":
    unittest.main()
