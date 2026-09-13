"""The library's own metadata files, over the wire.

Two operations that rewrite a file in every game folder, so the things worth pinning are
that they take the scan's job kind, that they refuse rather than overlap, and that the
caller is handed something to watch.
"""

from __future__ import annotations

import unittest
from unittest import mock

import httpapi
from common import jobs as job_registry
from console import sections

try:
    from starlette.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
class InfoRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        job_registry.reset_for_tests()
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        self.addCleanup(job_registry.reset_for_tests)

    def test_it_reports_the_three_states_apart(self) -> None:
        """`newer_than_us` is the one that has to stay separate: a file written by a
        later build is not one this build can upgrade, and counting it with the pending
        ones would report "I upgraded these" about files it cannot fully read."""
        with mock.patch("common.games.game_repository.info_maintenance_counts",
                        return_value={"pending_upgrade": 3, "restorable": 9,
                                      "newer_than_us": 1}), \
                mock.patch("common.games.game_repository.unreadable_games",
                           return_value=[{"name": "Bad One", "reason": "empty"}]), \
                mock.patch("common.games.game_service.newest_backup_stamp",
                           return_value="20260909T110917Z"), \
                mock.patch("common.games.game_service.pending_upgrade_game_names",
                           return_value=["A", "B", "C"]), \
                mock.patch("common.games.game_service.restorable_game_names",
                           return_value=["A"]):
            body = self.client.get("/library/info").json()

        self.assertEqual(body["pending_upgrade"], 3)
        self.assertEqual(body["newer_than_us"], 1)
        self.assertEqual(body["restorable"], 9)
        self.assertEqual([one["name"] for one in body["unreadable"]], ["Bad One"])

    def _start(self, which: str, done: list):
        return mock.patch(f"common.games.game_service.{which}",
                          side_effect=lambda **kw: done.append(kw))

    def test_an_upgrade_hands_back_a_job_to_watch(self) -> None:
        done: list = []
        with self._start("upgrade_info", done):
            answer = self.client.post("/library/info/upgrade")

        self.assertEqual(answer.status_code, 202)
        self.assertTrue(answer.headers["Location"].startswith("/api/v1/jobs/"))
        self.assertEqual(answer.json()["kind"], job_registry.KIND_LIBRARY_SCAN)

    def test_the_route_owns_the_job_rather_than_the_service(self) -> None:
        """Otherwise the service registers a second one of the same kind and refuses
        itself as busy - which is a 500 for work that was about to run fine."""
        done: list = []
        with self._start("upgrade_info", done):
            self.client.post("/library/info/upgrade")

        self.assertEqual(len(done), 1)
        self.assertIn("job", done[0])
        self.assertIsNotNone(done[0]["job"])

    def test_a_restore_is_the_same_kind_as_a_scan(self) -> None:
        """Both rewrite a .info for every game they touch, so running them at once would
        interleave writes to the same files."""
        done: list = []
        with self._start("restore_info", done):
            answer = self.client.post("/library/info/restore")

        self.assertEqual(answer.json()["kind"], job_registry.KIND_LIBRARY_SCAN)

    def test_one_at_a_time(self) -> None:
        """A second pass while one is running is refused rather than queued: the two
        would be rewriting the same files."""
        job_registry.submit(job_registry.KIND_LIBRARY_SCAN,
                            lambda job: _never_finishes())

        answer = self.client.post("/library/info/upgrade")

        self.assertEqual(answer.status_code, 409)


class MetadataCardTests(unittest.TestCase):
    """What the Overview says about it."""

    def test_a_backup_stamp_reads_as_a_date(self) -> None:
        """It is shown to somebody deciding whether to go back to it, and nobody reads
        an ISO basic-format timestamp at a glance."""
        self.assertEqual(sections._stamp("20260909T110917Z"), "2026-09-09")

    def test_no_stamp_says_nothing_rather_than_guessing(self) -> None:
        self.assertEqual(sections._stamp(""), "")
        self.assertEqual(sections._stamp("2026"), "")


def _never_finishes() -> None:
    import threading

    threading.Event().wait(30)
