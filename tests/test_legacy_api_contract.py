"""Pins the HTTP behaviour of the endpoints that predate /api/v1.

These endpoints have live consumers - themes poll /api/remote-launch at 1 Hz, the
mobile page links to /api/download-table-vpxz, the Manager UI drag-and-drop uses
/api/asset-upload/* - so moving them under /api/v1 has to leave them answering
exactly as they do now. This is the safety net for that move.

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
            [sys.executable, "-m", "tests.legacy_api_probe"],
            cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
        )
    stdout = proc.stdout.strip().splitlines()
    payload = json.loads(stdout[-1]) if stdout else {"__error__": proc.stderr[-2000:]}
    if "__error__" in payload:
        raise AssertionError(f"probe failed: {payload['__error__']}\n{proc.stderr[-2000:]}")
    return payload


class LegacyApiContractTests(unittest.TestCase):
    """Every assertion here describes today's behaviour. If one fails after a route
    move, the move changed something a live consumer can see."""

    @classmethod
    def setUpClass(cls) -> None:
        # Deliberately not skipped on failure: a safety net that quietly opts out
        # when it cannot run is not a safety net.
        cls.probe = _run_probe()

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

    def test_upload_begin_returns_an_upload_id(self) -> None:
        entry = self.probe["upload_begin"]

        self.assertEqual(entry["status"], 200)
        self.assertTrue(entry["json"].get("upload_id"))

    def test_upload_abort_acknowledges(self) -> None:
        entry = self.probe["upload_abort"]

        self.assertEqual(entry["status"], 200)
        self.assertEqual(entry["json"], {"ok": True})

    def test_an_unknown_upload_session_is_a_400_with_a_bare_error_string(self) -> None:
        """Legacy shape: {"error": "..."} - not the /api/v1 envelope."""
        for key in ("upload_unknown_session", "upload_analyze_unknown"):
            with self.subTest(endpoint=key):
                entry = self.probe[key]
                self.assertEqual(entry["status"], 400)
                self.assertIsInstance(entry["json"].get("error"), str)

    def test_vps_search_returns_a_results_list(self) -> None:
        entry = self.probe["vps_search"]

        self.assertEqual(entry["status"], 200)
        self.assertIsInstance(entry["json"].get("results"), list)

    def test_every_legacy_endpoint_answers_as_json(self) -> None:
        for name, entry in self.probe.items():
            with self.subTest(endpoint=name):
                self.assertEqual(entry["content_type"], "application/json")


if __name__ == "__main__":
    unittest.main()
