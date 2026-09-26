"""The update check, kept a day and worked out against the running version on each read.

The transport is stubbed: nothing here reaches GitHub.
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import requests

from common import http_client
from common.online import app_updater

MANIFEST_URL = "https://github.com/superhac/vpinfe/releases/download/v3.1.0/manifest.json"
RELEASE = {
    "tag_name": "v3.1.0",
    "body": "Notes nobody keeps",
    "assets": [
        {"name": "manifest.json", "browser_download_url": MANIFEST_URL, "size": 1},
        {"name": "vpinfe-linux-x64.zip", "browser_download_url": "https://x/linux.zip"},
    ],
}
MANIFEST = {"version": "v3.1.0",
            "assets": {"linux-x64": {"file": "vpinfe-linux-x64.zip", "sha256": "0"}}}
INSTALL = {"supported": True, "reason": None, "triplet": "linux-x64",
           "current_version": "v3.0.0"}
SOURCE = {**INSTALL, "supported": False, "reason": "source_build",
          "current_version": "3.0.0-dev"}
HOUR = 60 * 60


class UpdateCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "cache" / "update.json"
        self.asked: list[str] = []
        self.failure: Exception | None = None
        self.install: dict[str, Any] = dict(INSTALL)
        self.now = time.time()
        clock = mock.Mock()
        clock.time = lambda: self.now
        for patch in (mock.patch.object(app_updater, "UPDATE_CHECK_PATH", self.path),
                      mock.patch.object(app_updater, "get_json", self._get_json),
                      mock.patch.object(app_updater, "get_install_context",
                                        lambda: dict(self.install)),
                      mock.patch.object(app_updater, "time", clock)):
            patch.start()
            self.addCleanup(patch.stop)

    def _get_json(self, url: str, **_: Any) -> dict:
        self.asked.append(url)
        if self.failure is not None:
            raise self.failure
        answers: dict[str, dict] = {app_updater.LATEST_RELEASE_URL: RELEASE,
                                    MANIFEST_URL: MANIFEST}
        return answers[url]

    def _kept(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_a_first_check_asks_and_keeps_what_github_said(self) -> None:
        answer = app_updater.check_now()

        self.assertEqual(self.asked, [app_updater.LATEST_RELEASE_URL, MANIFEST_URL])
        self.assertTrue(answer["update_available"] and answer["update_supported"])
        self.assertEqual(answer["asset_name"], "vpinfe-linux-x64.zip")
        self.assertIsNone(answer["error"])
        kept = self._kept()
        self.assertEqual(kept["release"]["tag_name"], "v3.1.0")
        self.assertNotIn("body", kept["release"])
        self.assertEqual(kept["manifest"], MANIFEST)
        self.assertEqual(answer["checked_at"], kept["checked_at"])

    def test_within_a_day_nothing_is_asked(self) -> None:
        app_updater.check_now()
        self.asked.clear()
        self.now += 23 * HOUR

        self.assertTrue(app_updater.check_now()["update_supported"])
        self.assertEqual(self.asked, [])

    def test_after_a_day_it_asks_again(self) -> None:
        app_updater.check_now()
        self.asked.clear()
        self.now += 25 * HOUR

        app_updater.check_now()
        self.assertEqual(self.asked[0], app_updater.LATEST_RELEASE_URL)

    def test_refresh_asks_now(self) -> None:
        app_updater.check_now()
        self.asked.clear()

        app_updater.check_now(refresh=True)
        self.assertEqual(self.asked[0], app_updater.LATEST_RELEASE_URL)

    def test_an_install_that_just_updated_reads_itself_as_current(self) -> None:
        app_updater.check_now()
        self.asked.clear()
        self.install["current_version"] = "v3.1.0"

        answer = app_updater.check_now()
        self.assertFalse(answer["update_available"])
        self.assertEqual(answer["current_version"], "v3.1.0")
        self.assertEqual(self.asked, [])

    def test_a_kept_release_missing_the_manifest_it_now_needs_is_asked_again(self) -> None:
        self.install = {**SOURCE, "current_version": "v3.2.0"}
        app_updater.check_now()
        self.assertIsNone(self._kept()["manifest"])
        self.asked.clear()
        self.install = dict(INSTALL)

        self.assertTrue(app_updater.check_now()["update_supported"])
        self.assertEqual(self.asked, [app_updater.LATEST_RELEASE_URL, MANIFEST_URL])

    def _failing(self, level: str = "WARNING") -> Any:
        return self.assertLogs("vpinfe.common.online.app_updater", level)

    def test_a_failed_attempt_says_so_beside_the_last_success(self) -> None:
        checked = app_updater.check_now()["checked_at"]
        self.now += 25 * HOUR
        self.failure = requests.ConnectionError("no route")

        with self._failing():
            answer = app_updater.check_now()
        self.assertEqual(answer["error"], "remote_check_failed")
        self.assertEqual(answer["checked_at"], checked)
        self.assertEqual(answer["latest_version"], "v3.1.0")

    def test_a_failed_attempt_waits_an_hour_unless_refreshed(self) -> None:
        self.failure = requests.ConnectionError("no route")
        with self._failing():
            self.assertIsNone(app_updater.check_now()["checked_at"])
        self.asked.clear()

        self.now += HOUR - 60
        self.assertEqual(app_updater.check_now()["error"], "remote_check_failed")
        self.assertEqual(self.asked, [])

        with self._failing():
            app_updater.check_now(refresh=True)
        self.assertEqual(len(self.asked), 1)

        self.now += HOUR + 60
        self.failure = None
        answer = app_updater.check_now()
        self.assertIsNone(answer["error"])
        self.assertIsNotNone(answer["checked_at"])

    def test_a_network_failure_is_one_line(self) -> None:
        self.failure = requests.HTTPError("503 Server Error")
        with self._failing() as logs:
            app_updater.check_now()
        self.assertEqual([(r.levelname, r.exc_info) for r in logs.records
                          if r.levelname != "INFO"], [("WARNING", None)])
        self.assertIn("503 Server Error", logs.output[0])

    def test_a_host_that_said_wait_is_not_warned_about_again(self) -> None:
        self.failure = http_client.HostQuietError("api.github.com", self.now + 60)
        with self._failing("DEBUG") as logs:
            self.assertEqual(app_updater.check_now()["error"], "remote_check_failed")
        self.assertEqual([r.levelname for r in logs.records if r.levelname == "WARNING"], [])

    def test_anything_else_keeps_its_traceback(self) -> None:
        self.failure = KeyError("tag_name")
        with self._failing("ERROR") as logs:
            self.assertEqual(app_updater.check_now()["error"], "remote_check_failed")
        self.assertIsNotNone(logs.records[0].exc_info)

    def test_a_source_build_is_not_an_error(self) -> None:
        self.install = dict(SOURCE)

        answer = app_updater.check_now()
        self.assertIsNone(answer["error"])
        self.assertEqual(answer["support_reason"], "source_build")
        self.assertEqual(self.asked, [app_updater.LATEST_RELEASE_URL])

    def test_a_kept_answer_that_cannot_be_read_is_asked_again(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")

        with self.assertLogs("vpinfe.common.online.app_updater", "WARNING"):
            app_updater.check_now()
        self.assertEqual(self.asked[0], app_updater.LATEST_RELEASE_URL)


if __name__ == "__main__":
    unittest.main()
