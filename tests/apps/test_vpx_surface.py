"""How much of Visual Pinball core still knows about, pinned so it cannot grow.

Core is meant to ask an app what a file is, how to launch it and what it can do. Today
it still knows a great deal directly - the score parser reads NVRAM, the importer places
sidecars by name, the ini editor edits an ini. Moving that is the work after the
contract, and this test is what stops the boundary eroding while it is in flight.

The baseline is per file, so a reference moved from one module to another is visible
rather than netting out. It ratchets in one direction: a file may lose references and
never gain them. When a file is emptied, delete its line.
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

# The dirs that are meant to be app-agnostic. `apps/` is where this knowledge belongs
# and `managerui/` is on its way out, so neither is scanned.
SCANNED = ("common", "console", "httpapi", "frontend")

PATTERN = re.compile(r"\.vpx|vpinballx|directb2s|pinmame|nvram", re.IGNORECASE)

# Compatibility and migration, where naming the old world is the job. A 2.x theme reads
# `deletedNVRamOnClose`; a migration reads what the previous version wrote.
EXEMPT = frozenset({
    "common/deprecations.py",
    "common/games/info_migration.py",
    "common/games/launcher_migration.py",
    "frontend/theme_contract.py",
})

# Lines mentioning Visual Pinball, per file, as of the commit that introduced the
# contract. Lower these as the extraction lands; never raise one.
BASELINE: dict[str, int] = {
    "common/apps/__init__.py": 1,
    "common/config_schema.py": 2,
    "common/games/archive_service.py": 4,
    "common/games/asset_registry.py": 3,
    "common/games/asset_resolver.py": 11,
    "common/games/collection_resolver.py": 3,
    "common/games/export_bundle.py": 4,
    "common/games/game.py": 2,
    "common/games/game_metadata.py": 2,
    "common/games/game_parser.py": 4,
    "common/games/game_play_service.py": 11,
    "common/games/game_repository.py": 2,
    "common/games/game_service.py": 17,
    "common/games/info_file.py": 7,
    "common/games/info_maintenance.py": 1,
    "common/games/launchers.py": 1,
    "common/games/library_discovery.py": 1,
    "common/games/library_enrichment.py": 2,
    "common/games/media_lookup.py": 2,
    "common/games/media_placement.py": 1,
    "common/games/metadata_service.py": 1,
    "common/games/score_parser.py": 10,
    "common/games/standalone_scripts.py": 2,
    "common/games/tables.py": 8,
    "common/games/vpx_parser.py": 13,
    "common/host/launch.py": 6,
    "common/host/launch_state.py": 1,
    "common/host/pinmame_catalog.py": 14,
    "common/host/pinmame_worker.py": 14,
    "common/host/vpx_log.py": 1,
    "common/labels.py": 1,
    "common/launcher_path.py": 1,
    "common/online/pinmame_score_parser_updater.py": 7,
    "common/online/vps_kinds.py": 1,
    "common/uploads/asset_analyzer_service.py": 6,
    "common/uploads/asset_import_service.py": 21,
    "console/assets.py": 2,
    "console/data.py": 1,
    "console/game_tables.py": 1,
    "console/games.py": 9,
    "console/media.py": 1,
    "console/media_ownership.py": 2,
    "console/mediasource.py": 2,
    "console/sections.py": 2,
    "console/table_features.py": 1,
    "console/theme.py": 2,
    "console/workbench.py": 31,
    "httpapi/assets.py": 3,
    "httpapi/core_capabilities.py": 5,
    "httpapi/filesystem.py": 2,
    "httpapi/games.py": 23,
    "httpapi/library.py": 1,
    "httpapi/models.py": 15,
    "httpapi/tables.py": 3,
    "httpapi/uploads.py": 2,
}


def _counts() -> dict[str, int]:
    """Matching lines per file, keyed by the path relative to the repo root."""
    found: dict[str, int] = {}
    for directory in SCANNED:
        for source in sorted((ROOT / directory).rglob("*.py")):
            relative = source.relative_to(ROOT).as_posix()
            if relative in EXEMPT:
                continue
            hits = sum(1 for line in source.read_text(encoding="utf-8").splitlines()
                       if PATTERN.search(line))
            if hits:
                found[relative] = hits
    return found


class VPXSurfaceRatchetTests(unittest.TestCase):
    def test_no_file_gains_a_reference(self) -> None:
        counts = _counts()

        for path in sorted(counts):
            with self.subTest(path=path):
                self.assertLessEqual(
                    counts[path], BASELINE.get(path, 0),
                    f"{path} names Visual Pinball on {counts[path]} lines, up from "
                    f"{BASELINE.get(path, 0)}. Ask the app instead, or raise the "
                    f"baseline deliberately.")

    def test_the_exempt_files_are_real(self) -> None:
        """An exemption for a file that has been renamed away is a hole nobody sees."""
        for path in sorted(EXEMPT):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())

    def test_the_baseline_names_no_file_that_is_gone(self) -> None:
        counts = _counts()

        self.assertEqual(
            sorted(path for path in BASELINE
                   if path not in counts and not (ROOT / path).is_file()),
            [],
            "The baseline names files that no longer exist. Delete their lines.")


if __name__ == "__main__":
    unittest.main()
