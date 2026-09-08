"""The reporter that carries a long job's log and progress back to whoever asked."""

from __future__ import annotations

import unittest
from unittest import mock

from common.jobs import JobReporter


class JobReporterTests(unittest.TestCase):
    def test_job_reporter_wraps_log_and_progress_callbacks(self) -> None:
        messages: list[str] = []
        progress: list[tuple[int, int, str]] = []
        reporter = JobReporter(
            logger=mock.Mock(),
            log_cb=messages.append,
            progress_cb=lambda current, total, message: progress.append((current, total, message)),
        )

        reporter.log("hello")
        reporter.progress(1, 2, "half")

        self.assertEqual(messages, ["hello"])
        self.assertEqual(progress, [(1, 2, "half")])


if __name__ == "__main__":
    unittest.main()
