"""Asking VPinFE to look at the disk again.

The counterpart to `POST /library/scan`, which goes to VPSdb. This one only reads
folders, so it is what you call after copying a table in by hand.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from common import jobs


class LibraryRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        jobs.reset_for_tests()
        self.addCleanup(jobs.reset_for_tests)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def test_it_accepts_and_hands_back_a_job_to_watch(self) -> None:
        with patch("common.games.library_refresh.refresh", return_value={}) as ran:
            response = self.client.post("/library/refresh")

        self.assertEqual(response.status_code, 202)
        self.assertIn("/api/v1/jobs/", response.headers["Location"])
        self.assertEqual(response.json()["kind"], jobs.KIND_LIBRARY_SCAN)
        ran.assert_called_once()

    def test_it_will_not_run_beside_a_scan(self) -> None:
        """Both write a .info for every game they touch, so the second caller is
        refused rather than left to interleave writes with the first."""
        with jobs.track(jobs.KIND_LIBRARY_SCAN):
            response = self.client.post("/library/refresh")

        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
