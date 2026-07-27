"""Slow work as a job: one event shape, one at a time, answerable after the fact.

The rules under test are the ones a consumer depends on - that a job publishes the
shape common/events.py documents whoever started it, that two of a kind cannot run
at once over the same files, and that finishing is observable both by event and by
asking later.
"""

from __future__ import annotations

import threading
import unittest

from common import events, jobs


class _Recorder:
    """Collects the bus traffic a remote subscriber would see."""

    def __init__(self, test):
        self.seen = []
        for name in (events.JOB_PROGRESS, events.JOB_DONE, events.JOB_FAILED):
            test.addCleanup(events.subscribe(name, self._make(name)))

    def _make(self, name):
        def handler(**payload):
            self.seen.append((name, payload))
        return handler

    def names(self):
        return [name for name, _ in self.seen]

    def payloads(self, name):
        return [payload for seen, payload in self.seen if seen == name]


class TrackTests(unittest.TestCase):
    def setUp(self) -> None:
        jobs.reset_for_tests()
        self.addCleanup(jobs.reset_for_tests)
        self.bus = _Recorder(self)

    def test_progress_reaches_the_bus_in_the_documented_shape(self) -> None:
        with jobs.track("test.kind") as job:
            job.progress(1, 4, "quarter")

        progress = self.bus.payloads(events.JOB_PROGRESS)
        self.assertEqual(progress, [{"job_id": job.id, "pct": 25, "message": "quarter"}])
        self.assertEqual(self.bus.payloads(events.JOB_DONE), [{"job_id": job.id}])

    def test_a_starters_own_callbacks_still_fire(self) -> None:
        """The Manager UI keeps its progress bar; the bus is additive."""
        seen, logged = [], []

        with jobs.track("test.kind", progress_cb=lambda c, t, m: seen.append((c, t, m)),
                        log_cb=logged.append) as job:
            job.progress(2, 4, "half")
            job.log("working")
            self.assertEqual(job.pct, 50, "reported mid-flight, before completion")

        self.assertEqual(seen, [(2, 4, "half")])
        self.assertEqual(logged, ["working"])
        self.assertEqual(job.pct, 100, "completion is always 100, whatever was reported")

    def test_a_broken_callback_does_not_break_the_job(self) -> None:
        def explode(*_args):
            raise RuntimeError("bad listener")

        with self.assertLogs("vpinfe.common.jobs", level="DEBUG") as caught:
            with jobs.track("test.kind", progress_cb=explode, log_cb=explode) as job:
                job.progress(1, 2, "still fine")
                job.log("still fine")

        self.assertTrue(any("callback failed" in line.lower() for line in caught.output),
                        "the failure is contained, not swallowed silently")
        self.assertEqual(job.state, jobs.DONE)
        self.assertEqual(self.bus.payloads(events.JOB_DONE), [{"job_id": job.id}])

    def test_zero_total_does_not_divide_by_zero(self) -> None:
        with jobs.track("test.kind") as job:
            job.progress(0, 0, "nothing to do")
            self.assertEqual(job.pct, 0)

    def test_a_raising_job_fails_loudly_and_records_why(self) -> None:
        with self.assertRaises(ValueError):
            with jobs.track("test.kind") as job:
                raise ValueError("scan blew up")

        self.assertEqual(job.state, jobs.FAILED)
        self.assertEqual(job.error, "scan blew up")
        self.assertEqual(self.bus.payloads(events.JOB_FAILED),
                         [{"job_id": job.id, "error": "scan blew up"}])
        self.assertNotIn(events.JOB_DONE, self.bus.names())

    def test_one_kind_at_a_time(self) -> None:
        """Two library scans would interleave writes to the same .info files."""
        with jobs.track("test.kind"):
            with self.assertRaises(jobs.JobBusyError):
                with jobs.track("test.kind"):
                    pass

    def test_different_kinds_do_not_block_each_other(self) -> None:
        with jobs.track("test.one"), jobs.track("test.two"):
            self.assertEqual(len(jobs.active()), 2)

    def test_the_slot_frees_after_a_failure(self) -> None:
        """A crashed scan must not lock the kind out until restart."""
        with self.assertRaises(ValueError):
            with jobs.track("test.kind"):
                raise ValueError("boom")

        with jobs.track("test.kind") as second:
            self.assertEqual(second.state, jobs.RUNNING)


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        jobs.reset_for_tests()
        self.addCleanup(jobs.reset_for_tests)

    def test_submit_runs_off_thread_and_the_result_is_queryable_after(self) -> None:
        started, release = threading.Event(), threading.Event()

        def work(job):
            started.set()
            release.wait(5)
            job.progress(1, 1, "done working")

        job = jobs.submit("test.kind", work)
        self.assertTrue(started.wait(5))
        self.assertEqual(jobs.get(job.id).state, jobs.RUNNING, "returns before finishing")

        release.set()
        for _ in range(500):
            if jobs.get(job.id).state != jobs.RUNNING:
                break
            threading.Event().wait(0.01)

        finished = jobs.get(job.id)
        self.assertEqual(finished.state, jobs.DONE)
        self.assertEqual(finished.pct, 100)
        self.assertIsNotNone(finished.finished_at)

    def test_a_failing_submitted_job_is_recorded_not_raised(self) -> None:
        def work(_job):
            raise RuntimeError("worker died")

        with self.assertLogs("vpinfe.common.jobs", level="ERROR"):
            job = jobs.submit("test.kind", work)
            for _ in range(500):
                if jobs.get(job.id).state != jobs.RUNNING:
                    break
                threading.Event().wait(0.01)

        self.assertEqual(jobs.get(job.id).state, jobs.FAILED)
        self.assertEqual(jobs.get(job.id).error, "worker died")

    def test_an_unknown_id_is_none_rather_than_an_error(self) -> None:
        self.assertIsNone(jobs.get("nope"))

    def test_history_is_bounded_so_a_long_session_does_not_grow(self) -> None:
        for index in range(jobs._HISTORY_LIMIT + 5):
            with jobs.track(f"test.kind{index}"):
                pass

        self.assertEqual(len(jobs.recent()), jobs._HISTORY_LIMIT)

    def test_recent_lists_running_jobs_before_finished_ones(self) -> None:
        with jobs.track("test.finished"):
            pass
        with jobs.track("test.running"):
            kinds = [job.kind for job in jobs.recent()]

        self.assertEqual(kinds[0], "test.running")
        self.assertIn("test.finished", kinds)


class JobEndpointTests(unittest.TestCase):
    """The wire side: jobs are readable, and a scan is accepted rather than awaited."""

    def setUp(self) -> None:
        from starlette.testclient import TestClient

        import httpapi

        jobs.reset_for_tests()
        self.addCleanup(jobs.reset_for_tests)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def test_a_running_job_is_listed_and_addressable(self) -> None:
        with jobs.track("test.kind") as job:
            job.progress(1, 2, "halfway")
            listed = self.client.get("/jobs").json()["jobs"]
            one = self.client.get(f"/jobs/{job.id}").json()

        self.assertEqual([row["id"] for row in listed], [job.id])
        self.assertEqual(one["state"], "running")
        self.assertEqual(one["pct"], 50)
        self.assertEqual(one["message"], "halfway")
        self.assertEqual(one["links"]["self"], f"/api/v1/jobs/{job.id}")
        self.assertEqual(one["links"]["events"], "/api/v1/events")

    def test_the_outcome_survives_the_job_finishing(self) -> None:
        """A client that missed job.done can still learn how it went."""
        with jobs.track("test.kind") as job:
            pass

        body = self.client.get(f"/jobs/{job.id}").json()

        self.assertEqual(body["state"], "done")
        self.assertEqual(body["pct"], 100)
        self.assertIsNone(body["error"])
        self.assertIsNotNone(body["finished_at"])

    def test_filtering_by_kind(self) -> None:
        with jobs.track("test.wanted"), jobs.track("test.other"):
            rows = self.client.get("/jobs", params={"kind": "test.wanted"}).json()["jobs"]

        self.assertEqual([row["kind"] for row in rows], ["test.wanted"])

    def test_an_unknown_job_is_a_not_found_envelope(self) -> None:
        response = self.client.get("/jobs/nope")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_a_scan_is_accepted_and_points_at_its_job(self) -> None:
        from unittest.mock import patch

        started = threading.Event()

        def fake_build(job=None, **_kwargs):
            started.set()
            job.progress(1, 1, "scanned")
            return {"found": 1, "not_found": 0}

        with patch("managerui.services.table_service.build_metadata", fake_build):
            response = self.client.post("/library/scan", json={"download_media": False})
            self.assertTrue(started.wait(5))

        body = response.json()
        self.assertEqual(response.status_code, 202, "accepted, not awaited")
        self.assertEqual(response.headers["Location"], f"/api/v1/jobs/{body['id']}")
        self.assertEqual(body["kind"], jobs.KIND_LIBRARY_SCAN)

    def test_a_second_scan_is_refused_while_one_runs(self) -> None:
        with jobs.track(jobs.KIND_LIBRARY_SCAN):
            response = self.client.post("/library/scan")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "conflict")

    def test_discovery_advertises_the_jobs_collection(self) -> None:
        links = self.client.get("/").json()["links"]

        self.assertEqual(links["jobs"], "/api/v1/jobs")


if __name__ == "__main__":
    unittest.main()
