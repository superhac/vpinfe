"""What an install can be told to do to itself.

Two questions, and the difference between them is the point: the vocabulary says which
pairs exist, and the registry says which are wired up on this build. A button that
reports success while nothing happened is worse than one that is not offered.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpapi
from common import lifecycle
from tests.support.library import TempTree

try:
    from starlette.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
class ActionsApiTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        self.addCleanup(lifecycle.reset_for_tests)

    def _offer(self, scope: str, action: str) -> list:
        done = []
        lifecycle.register_performer(scope, action, done.append)
        return done

    def test_every_pair_is_listed_whether_or_not_it_is_wired_up(self) -> None:
        """Hiding one makes two installs look like different products."""
        body = self.client.get("/actions").json()

        self.assertEqual(body["count"], len(lifecycle.offered()))
        self.assertEqual({(a["scope"], a["action"]) for a in body["actions"]},
                         set(lifecycle.offered()))

    def test_each_one_is_named_in_the_words_a_person_reads(self) -> None:
        body = self.client.get("/actions").json()

        for entry in body["actions"]:
            with self.subTest(pair=(entry["scope"], entry["action"])):
                self.assertTrue(entry["label"].strip())
                self.assertNotEqual(entry["label"],
                                    f'{entry["action"]} the {entry["scope"]}')

    def test_one_nothing_performs_says_so_rather_than_being_offered(self) -> None:
        body = self.client.get("/actions").json()
        found = next(a for a in body["actions"]
                     if (a["scope"], a["action"]) == ("system", "restart"))

        self.assertFalse(found["available"])
        self.assertTrue(found["reason"].strip())

    def test_performing_one_goes_through_the_lifecycle_scope(self) -> None:
        done = self._offer("frontend", "restart")

        body = self.client.post("/actions",
                                json={"scope": "frontend", "action": "restart"}).json()

        self.assertTrue(body["performed"])
        self.assertEqual(body["what"], "Reopen the frontend windows")
        self.assertEqual([r.pair for r in done], [("frontend", "restart")])

    def test_the_reason_travels_with_it(self) -> None:
        """It reaches the log and every other surface, so "restarted from the Console"
        reads better afterwards than "restarted"."""
        done = self._offer("frontend", "restart")

        self.client.post("/actions", json={"scope": "frontend", "action": "restart",
                                           "reason": "because I said so"})

        self.assertEqual(done[0].reason, "because I said so")

    def test_asking_for_one_nothing_performs_is_refused(self) -> None:
        answer = self.client.post("/actions",
                                  json={"scope": "system", "action": "restart"})

        self.assertEqual(answer.status_code, 501)
        self.assertEqual(answer.json()["error"]["code"], "feature_unavailable")

    def test_asking_for_something_that_is_not_an_action_is_refused(self) -> None:
        answer = self.client.post("/actions",
                                  json={"scope": "toaster", "action": "toast"})

        self.assertEqual(answer.status_code, 400)

    def test_starting_a_table_is_not_something_an_install_does(self) -> None:
        """Starting one is a launch, which has to know which game."""
        answer = self.client.post("/actions",
                                  json={"scope": "table", "action": "start"})

        self.assertEqual(answer.status_code, 400)

    def test_closing_a_table_that_is_not_running_says_it_did_not(self) -> None:
        """Through the play route's own handler, which checks first. Reporting that it
        closed one when none was running is a confident wrong answer."""
        self._offer("table", "stop")

        body = self.client.post("/actions",
                                json={"scope": "table", "action": "stop"}).json()

        self.assertFalse(body["performed"])

    def test_one_that_takes_the_machine_away_answers_before_it_goes(self) -> None:
        """A process that is stopping cannot report that it stopped, so the work is
        handed to a background task and the response goes out first."""
        done = self._offer("app", "restart")

        with patch.object(httpapi.actions, "_perform",
                          side_effect=lambda *a: done.append(a)) as performed:
            body = self.client.post("/actions",
                                    json={"scope": "app", "action": "restart"}).json()

        self.assertTrue(body["performed"])
        self.assertTrue(performed.called, "the work was never handed over")


if __name__ == "__main__":
    unittest.main()
