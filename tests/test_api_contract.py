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
        table = tables_dir / "Example Table (Bally 1990)"
        table.mkdir(parents=True)
        (table / "Example Table (Bally 1990).vpx").write_bytes(b"not really a vpx")
        (table / "Example Table (Bally 1990).info").write_text(json.dumps({
            "Info": {"Title": "Example Table", "Manufacturer": "Bally", "Year": "1990",
                     "Type": "SS", "VPSId": "vps-example"},
            "VPXFile": {"filename": "Example Table (Bally 1990).vpx", "rom": "exmpl"},
            "User": {"Rating": 3},
        }), encoding="utf-8")

        # A folder holding several .vpx, plus a .vbs that is not a game file.
        multi = tables_dir / "Multi File (Bally 1991)"
        multi.mkdir()
        for name in ("Multi File (Bally 1991).vpx", "Multi File (Bally 1991) - alt.vpx",
                     "Multi File (Bally 1991) - VPW.vpx"):
            (multi / name).write_bytes(b"vpx")
        (multi / "Multi File (Bally 1991).vbs").write_text("' sidecar", encoding="utf-8")
        (multi / "Multi File (Bally 1991).info").write_text(json.dumps({
            "Info": {"Title": "Multi File", "VPSId": "vps-multi"},
            "VPXFile": {"filename": "Multi File (Bally 1991).vpx"},
        }), encoding="utf-8")

        # .info names a .vpx that is not on disk.
        mismatch = tables_dir / "Mismatch (Bally 1992)"
        mismatch.mkdir()
        (mismatch / "Mismatch (Bally 1992).vpx").write_bytes(b"vpx")
        (mismatch / "Mismatch (Bally 1992).info").write_text(json.dumps({
            "Info": {"Title": "Mismatch", "VPSId": "vps-mismatch"},
            "VPXFile": {"filename": "does-not-exist.vpx"},
        }), encoding="utf-8")

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

    # --- tables, and the archive that used to be /api/download-table-vpxz -----

    def test_listing_tables_returns_addressable_resources(self) -> None:
        entry = self.probe["tables_list"]

        self.assertEqual(entry["status"], 200)
        body = entry["json"]
        self.assertEqual(body["total"], 3)
        table = [t for t in body["tables"] if t["name"] == "Example Table"][0]
        self.assertTrue(table["id"], "every listed table is addressable")
        self.assertEqual(table["vps_id"], "vps-example", "correlation, not identity")
        self.assertEqual(table["name"], "Example Table")

    def test_a_table_resource_links_to_its_sub_resources(self) -> None:
        table = self.probe["table_get"]["json"]

        self.assertEqual(self.probe["table_get"]["status"], 200)
        self.assertEqual(table["links"]["files"], f"/api/v1/tables/{table['id']}/files")
        self.assertEqual(table["links"]["archive"], f"/api/v1/tables/{table['id']}/archive")

    def test_game_files_are_a_list_even_though_there_is_one_today(self) -> None:
        """A table is not permanently one .vpx; the shape says so now."""
        entry = self.probe["table_files"]

        self.assertEqual(entry["status"], 200)
        files = entry["json"]["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["format"], "vpx")
        self.assertTrue(files[0]["default"])
        self.assertTrue(files[0]["available"])

    def test_archive_downloads_with_the_progress_cookie_preserved(self) -> None:
        """The mobile page watches for this cookie to know the download started."""
        entry = self.probe["table_archive"]

        self.assertEqual(entry["status"], 200)
        self.assertEqual(entry["content_type"], "application/octet-stream")
        self.assertIn(".vpxz", entry["disposition"])
        self.assertIn("vpinfe_vpxz_download_abc123=1", entry["set_cookie"] or "")
        self.assertGreater(entry["bytes"], 0)

    def test_a_folder_with_several_vpx_reports_all_of_them(self) -> None:
        """A table folder can hold more than one .vpx, and .vbs is not a game file."""
        files = self.probe["multi_file_files"]["json"]["files"]

        names = [f["filename"] for f in files]
        self.assertEqual(names, sorted(names, key=str.lower), "order must not depend on the disk")
        self.assertEqual(len(files), 3)
        self.assertNotIn("Multi File (Bally 1991).vbs", names)
        self.assertEqual([f["filename"] for f in files if f["default"]],
                         ["Multi File (Bally 1991).vpx"])
        self.assertTrue(all(f["available"] for f in files))

    def test_a_recorded_file_that_is_missing_is_reported_but_not_the_default(self) -> None:
        """Reporting it matters; pointing a caller at it to launch does not."""
        files = self.probe["mismatch_files"]["json"]["files"]

        by_name = {f["filename"]: f for f in files}
        self.assertFalse(by_name["does-not-exist.vpx"]["available"])
        self.assertFalse(by_name["does-not-exist.vpx"]["default"])
        self.assertTrue(by_name["Mismatch (Bally 1992).vpx"]["available"])
        self.assertTrue(by_name["Mismatch (Bally 1992).vpx"]["default"])

    def test_an_unknown_table_is_a_404_in_the_envelope(self) -> None:
        for key in ("table_unknown", "archive_unknown"):
            with self.subTest(endpoint=key):
                entry = self.probe[key]
                self.assertEqual(entry["status"], 404)
                self.assertEqual(entry["json"]["error"]["code"], "not_found")

    def test_the_old_archive_route_is_gone(self) -> None:
        """Addressing by id also retires the path-traversal case the old route had
        to guard: an id either maps to a known table or it does not exist."""
        self.assertGreaterEqual(self.probe["legacy_archive_gone"]["status"], 400)

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
            if name in ("legacy_upload_gone", "legacy_archive_gone", "table_archive"):
                continue  # NiceGUI's own 404s, and the archive is a file download
            with self.subTest(endpoint=name):
                self.assertEqual(entry["content_type"], "application/json")


if __name__ == "__main__":
    unittest.main()
