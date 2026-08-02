"""The 3.0 parity gate: this tree behaves like master, except where the ledger says.

Compares a live capture of this tree (tests/parity_capture.py, run in a fresh
interpreter) against the committed master baseline. Every allowed difference is
named by a PAR- id in docs/compatibility-3.0.md; an unlisted difference is a
failure. That file explains how to refresh the baseline when master moves.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "tests" / "parity_baseline_master.json"
LEDGER = REPO_ROOT / "docs" / "compatibility-3.0.md"

# The differences the ledger permits, keyed by the entries that permit them.
LEDGER_ALLOWS = {
    "PAR-03": {"remote_launch", "upload_begin", "archive_download"},
    "PAR-04": {"removed": "update_frontend_dof_for_table",
               "added": "notify_game_selected"},
    # PAR-21: every old spelling stays in the allowlist and forwards, so this is
    # additive - nothing is removed, and a theme calling the old name still works.
    "PAR-21": {"get_games", "get_initial_game_index", "set_games_by_collection",
               "launch_game", "get_game_rating", "set_game_rating",
               "get_playfield_orientation", "get_playfield_rotation",
               # PAR-04's name, kept as an alias by PAR-21 even though master
               # never served it - a 3.0-era theme may already call it.
               "notify_table_selected"},
    # PAR-27: one method added so the browser can report a deprecated name it used.
    # Additive - a theme that never calls it is unaffected.
    "PAR-27": {"report_deprecated_use"},
    # New media kinds add theme-payload keys. Additive only: every key master
    # had must still be present and equal.
    "PAR-11": {"RuleCardImagePath", "TopperPath", "TopperVideoPath",
               "LoadingVideoPath", "AudioLaunchPath", "RuleSheetPath"},
    "PAR-12": {"LogoImagePath"},
    "PAR-15": {"ManufacturerLogoPath"},
}

# Every theme-payload key the ledger permits adding, across entries.
ALLOWED_NEW_PAYLOAD_KEYS = (LEDGER_ALLOWS["PAR-11"] | LEDGER_ALLOWS["PAR-12"]
                            | LEDGER_ALLOWS["PAR-15"])


def _capture_current() -> dict:
    env = dict(os.environ)
    env.pop("VPINFE_CONFIG_DIR", None)
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "parity_capture.py")],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=env, timeout=300,
    )
    payload = json.loads(proc.stdout)
    if "__error__" in payload:
        raise AssertionError(f"capture failed: {payload['__error__']}\n{proc.stderr[-1500:]}")
    return payload


class LedgerTests(unittest.TestCase):
    """The ledger's own shape. Separate from ParityTests so a doc mistake is caught
    without paying for the capture subprocess, and still reported when it fails.
    """

    def test_every_entry_has_its_own_id(self) -> None:
        """Two entries sharing an id makes one of them unreachable: the gate looks an id
        up to find the reason for a difference, and finds the wrong one. It has happened.
        """
        ids = re.findall(r"^\*\*(PAR-\d+)", LEDGER.read_text(), re.MULTILINE)
        duplicates = sorted({par_id for par_id in ids if ids.count(par_id) > 1})

        self.assertEqual(duplicates, [], f"ledger ids used more than once: {duplicates}")
        self.assertTrue(ids, "no ledger entries found - has the heading format changed?")


class ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.master = json.loads(BASELINE.read_text())
        cls.current = _capture_current()
        cls.ledger_text = LEDGER.read_text()

    def test_every_id_this_gate_relies_on_is_in_the_ledger(self) -> None:
        """The gate may only allow what the ledger explains."""
        for par_id in LEDGER_ALLOWS:
            self.assertIn(f"**{par_id}", self.ledger_text,
                          f"{par_id} is enforced here but missing from the ledger")

    def test_the_theme_payload_only_grows_by_the_listed_keys(self) -> None:
        """Master's keys must all survive with equal values; the only additions
        allowed are PAR-11's new media kinds. Removing or changing a key a theme
        already reads has no ledger entry and never will."""
        master = self.master["theme_payload"]
        current = self.current["theme_payload"]

        self.assertEqual(master["count"], current["count"])
        self.assertEqual(master["stable_values"], current["stable_values"])
        self.assertEqual(master["resolved_media_fields"], current["resolved_media_fields"])

        master_keys = set(master["keys"])
        current_keys = set(current["keys"])
        self.assertEqual(master_keys - current_keys, set(),
                         "a key a theme may already read has vanished")
        self.assertEqual(current_keys - master_keys, ALLOWED_NEW_PAYLOAD_KEYS,
                         "only the ledger's listed additions are permitted")

    def test_a_scan_never_writes_on_either_side(self) -> None:
        """Reading the library is a read. The PAR-01/02 migrations are first-run
        writes through their own paths, not scan side effects."""
        self.assertEqual(self.master["scan_writes"], [])
        self.assertEqual(self.current["scan_writes"], [])

    def test_ws_allowlist_differs_only_by_the_documented_rename(self) -> None:
        master = set(self.master["ws_allowlist"])
        current = set(self.current["ws_allowlist"])
        rename = LEDGER_ALLOWS["PAR-04"]

        self.assertEqual(master - current, {rename["removed"]},
                         "only PAR-04's removal is permitted - every renamed method "
                         "keeps its old name as a forwarding alias")
        self.assertEqual(
            current - master,
            {rename["added"]} | LEDGER_ALLOWS["PAR-21"] | LEDGER_ALLOWS["PAR-27"],
            "only PAR-04's, PAR-21's and PAR-27's additions are permitted")

    def test_legacy_endpoints_served_on_master_and_do_not_serve_here(self) -> None:
        """PAR-03: removed, not aliased - and the removal itself is asserted, so
        the ledger can't drift into fiction if someone quietly restores one."""
        for name in LEDGER_ALLOWS["PAR-03"]:
            with self.subTest(endpoint=name):
                master_entry = self.master["legacy_endpoints"][name]
                current_entry = self.current["legacy_endpoints"][name]
                self.assertIsNotNone(master_entry["keys"],
                                     "baseline shows the route answering JSON")
                self.assertNotEqual(current_entry["keys"], master_entry["keys"],
                                    "the route must not answer its old shape")


if __name__ == "__main__":
    unittest.main()
