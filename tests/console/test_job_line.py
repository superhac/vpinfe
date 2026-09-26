"""Which failed job the drawer's footer line keeps."""

from __future__ import annotations

import unittest

from console.page import failed_since

OPENED = 1000.0


def _job(job_id: str, state: str, finished_at: float | None = None) -> dict:
    return {"id": job_id, "state": state, "finished_at": finished_at,
            "message": "Reading the library", "error": "It did not answer in time."}


class FailedSinceTests(unittest.TestCase):
    def test_one_that_failed_after_the_page_opened_is_kept(self) -> None:
        failed = _job("j2", "failed", 1010.0)

        self.assertIs(failed_since([failed, _job("j1", "done", 1005.0)], OPENED, set()),
                      failed)

    def test_one_that_failed_before_the_page_opened_is_not_news(self) -> None:
        self.assertIsNone(failed_since([_job("j1", "failed", 990.0)], OPENED, set()))

    def test_a_later_job_that_finished_clears_it(self) -> None:
        jobs = [_job("j2", "done", 1020.0), _job("j1", "failed", 1010.0)]

        self.assertIsNone(failed_since(jobs, OPENED, set()))

    def test_one_clicked_away_stays_away(self) -> None:
        self.assertIsNone(failed_since([_job("j1", "failed", 1010.0)], OPENED, {"j1"}))

    def test_a_running_job_is_passed_over_for_the_last_to_end(self) -> None:
        failed = _job("j1", "failed", 1010.0)

        self.assertIs(failed_since([_job("j2", "running"), failed], OPENED, set()),
                      failed)

    def test_nothing_run_keeps_nothing(self) -> None:
        self.assertIsNone(failed_since([], OPENED, set()))


if __name__ == "__main__":
    unittest.main()
