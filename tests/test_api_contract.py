"""Pins the HTTP behaviour every in-repo consumer depends on.

The drag-and-drop client, the theme frontend's remote-launch poll and the mobile
page's download link all speak to these routes, so a change here is a change a
user can see. Endpoints keep their entry once they move under /api/v1, which is
what makes a move provably behaviour-preserving.

Runs the app in a subprocess with a throwaway config dir: common.paths resolves
CONFIG_DIR at import time, so isolation is only reliable in a fresh interpreter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_probe() -> dict:
    with TemporaryDirectory() as tmp:
        config_dir = Path(tmp) / "config"
        tables_dir = Path(tmp) / "tables"
        tables_dir.mkdir(parents=True)

        env = dict(os.environ)
        env["VPINFE_CONFIG_DIR"] = str(config_dir)
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

        config_dir.mkdir(parents=True)
        (config_dir / "vpinfe.ini").write_text(
            f"[Settings]\ntablerootdir = {tables_dir}\n", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, "-m", "tests.api_probe"],
            cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
        )
    stdout = proc.stdout.strip().splitlines()
    payload = json.loads(stdout[-1]) if stdout else {"__error__": proc.stderr[-2000:]}
    if "__error__" in payload:
        raise AssertionError(f"probe failed: {payload['__error__']}\n{proc.stderr[-2000:]}")
    return payload


class ApiContractTests(unittest.TestCase):
    """Each assertion describes behaviour a consumer relies on. A failure after a
    route move means the move changed something visible."""

    @classmethod
    def setUpClass(cls) -> None:
        # Deliberately not skipped on failure: a safety net that quietly opts out
        # when it cannot run is not a safety net.
        cls.probe = _run_probe()

    # --- not yet moved -------------------------------------------------------

    def test_remote_launch_shape_and_cors(self) -> None:
        """Themes poll this at 1 Hz cross-origin from the asset server."""
        entry = self.probe["remote_launch"]

        self.assertEqual(entry["status"], 200)
        self.assertEqual(entry["json"], {"launching": False, "table_name": None})
        self.assertEqual(entry["cors"], "*", "themes call this from another origin")

    def test_archive_reports_a_missing_table_as_404_json(self) -> None:
        entry = self.probe["archive_missing"]

        self.assertEqual(entry["status"], 404)
        self.assertEqual(entry["json"], {"error": "Table not found"})

    def test_archive_rejects_a_path_traversal_attempt(self) -> None:
        entry = self.probe["archive_traversal"]

        self.assertEqual(entry["status"], 400)
        self.assertEqual(entry["json"], {"error": "Invalid table path"})

    # --- uploads, now under /api/v1 ------------------------------------------

    def test_the_drag_and_drop_upload_sequence_works_end_to_end(self) -> None:
        """begin -> add file -> summary -> delete, exactly as dnd_upload.js drives it."""
        begin = self.probe["upload_begin"]
        self.assertEqual(begin["status"], 200)
        self.assertTrue(begin["json"].get("id"), "the client reads .id")

        added = self.probe["upload_add_file"]
        self.assertEqual(added["status"], 200)
        self.assertEqual(added["json"], {"bytes": 5})

        summary = self.probe["upload_summary"]
        self.assertEqual(summary["status"], 200)
        self.assertEqual(summary["json"], {"file_count": 1, "total_bytes": 5})

        deleted = self.probe["upload_delete"]
        self.assertEqual(deleted["status"], 200)
        self.assertEqual(deleted["json"], {"ok": True})

    def test_an_unknown_upload_session_is_a_404_in_the_envelope(self) -> None:
        for key in ("upload_unknown_session", "upload_analysis_unknown"):
            with self.subTest(endpoint=key):
                entry = self.probe[key]
                self.assertEqual(entry["status"], 404)
                self.assertEqual(entry["json"]["error"]["code"], "not_found")

    def test_vps_search_returns_a_results_list(self) -> None:
        entry = self.probe["vps_search"]

        self.assertEqual(entry["status"], 200)
        self.assertIsInstance(entry["json"].get("results"), list)

    def test_the_old_upload_routes_are_gone(self) -> None:
        """Their only consumer was our own drag-and-drop client, which moved with them.

        Not asserted as a clean 404: NiceGUI's own 404 handler renders a page and
        needs the app config that ui.run() installs, which this harness never calls.
        Under a real server it is a 404; here the point is only that it no longer serves.
        """
        self.assertGreaterEqual(self.probe["legacy_upload_gone"]["status"], 400)

    def test_every_live_endpoint_answers_as_json(self) -> None:
        for name, entry in self.probe.items():
            if name == "legacy_upload_gone":
                continue  # handled by NiceGUI, not us - see above
            with self.subTest(endpoint=name):
                self.assertEqual(entry["content_type"], "application/json")


if __name__ == "__main__":
    unittest.main()
