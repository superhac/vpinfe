"""The library-wide rollup: every kind counted in games, not files.

The reason it exists is a negative result: a consumer can only conclude "you own zero
toppers, stop showing me toppers" if it can see the whole library. Four kinds in a real
library had zero installed anywhere.

Counted on a job rather than served live, because resolving media for every game was
measured at 650ms over 149 folders - CPU, not disk, so a warm run does not help.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from common import jobs as job_registry
from common.games import library_vps_state as rollup


def _state(matched=True, **held):
    """One game's answer, in the shape `vps_state_of` produces."""
    return {
        "matched": matched,
        "kinds": [{"kind": kind, "held": h, "identified": i, "listed": ll,
                   "obtainable": o, "updated": False, "new_upstream": 0}
                  for kind, (h, i, ll, o) in held.items()],
    }


class RollupCountTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(rollup, "store")
        self.stored = patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_kind_no_game_holds_counts_zero_across_the_library(self) -> None:
        """The result the rollup exists for. Nothing per-game can say it."""
        answers = [_state(topperFiles=(False, False, 1, 1)),
                   _state(topperFiles=(False, False, 1, 0))]
        counted = rollup.compute({"g1": 1, "g2": 2}, lambda game, gid: answers.pop(0))

        tally = {item["kind"]: item for item in counted["kinds"]}["topperFiles"]
        self.assertEqual(tally["holding"], 0)
        self.assertEqual(tally["listed"], 2)

    def test_games_are_counted_not_files(self) -> None:
        """A game holding four backglasses is one game holding backglasses. Counting
        files would let one hoarder read as a library-wide answer."""
        answers = [_state(b2sFiles=(True, True, 3, 3)),
                   _state(b2sFiles=(True, False, 1, 1))]
        counted = rollup.compute({"g1": 1, "g2": 2}, lambda game, gid: answers.pop(0))

        tally = {item["kind"]: item for item in counted["kinds"]}["b2sFiles"]
        self.assertEqual(tally["holding"], 2)
        self.assertEqual(tally["identified"], 1)

    def test_a_game_that_cannot_be_read_still_counts_in_the_total(self) -> None:
        """Dropping it would shrink the denominator every ratio is read against, and
        the rollup would quietly report a healthier library than there is."""
        def answer(game, game_id):
            if game == 2:
                raise OSError("unreadable")
            return _state(b2sFiles=(True, False, 1, 1))

        counted = rollup.compute({"g1": 1, "g2": 2, "g3": 3}, answer)

        self.assertEqual(counted["games"], 3)
        self.assertEqual(counted["matched"], 2)

    def test_every_kind_is_present_even_at_zero(self) -> None:
        """So a consumer's columns do not appear and vanish with the library."""
        counted = rollup.compute({"g1": 1}, lambda game, gid: _state())

        self.assertEqual(len(counted["kinds"]), 9)
        self.assertTrue(all("holding" in item for item in counted["kinds"]))


class RollupStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patcher = patch.object(rollup, "ROLLUP_PATH",
                               Path(self.dir.name) / "vps-rollup.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_never_counted_reads_as_empty_not_as_zero(self) -> None:
        self.assertEqual(rollup.stored(), {})

    def test_what_was_written_comes_back(self) -> None:
        rollup.store({"computed": "2026-09-02T00:00:00Z", "games": 3, "kinds": []})

        self.assertEqual(rollup.stored()["games"], 3)

    def test_a_rollup_from_another_schema_is_ignored(self) -> None:
        """Rather than half-read: the shape is what the counts mean."""
        rollup.ROLLUP_PATH.write_text(json.dumps({"schema": 99, "games": 7}))

        self.assertEqual(rollup.stored(), {})


class RollupRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        job_registry.reset_for_tests()
        patcher = patch.object(rollup, "stored", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(httpapi.create_api_app(),
                                 raise_server_exceptions=False)

    def test_a_library_never_counted_says_so_rather_than_404(self) -> None:
        body = self.client.get("/library/vps_state").json()

        self.assertEqual(body["computed"], "")
        self.assertEqual(body["kinds"], [])

    def test_counting_is_accepted_not_done(self) -> None:
        with patch("httpapi.games._catalog", return_value={}):
            response = self.client.post("/library/vps_state")

        self.assertEqual(response.status_code, 202, response.text)
        self.assertTrue(response.headers["Location"].startswith("/api/v1/jobs/"))

    def test_it_takes_its_own_job_kind(self) -> None:
        """Not the scan's. This only reads, so queueing it behind a write would make
        a cheap question wait on an expensive one for no reason."""
        self.assertNotEqual(job_registry.KIND_VPS_ROLLUP,
                            job_registry.KIND_LIBRARY_SCAN)


if __name__ == "__main__":
    unittest.main()
