"""What `why()` puts under a failure's message."""

from __future__ import annotations

import errno
import socket
import unittest

import requests

from common import i18n
from common.failures import why
from common.http_client import HostQuietError
from tests.support.library import TempTree
from tests.support.skips import needs_posix_permissions


def _answered(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response.reason = "Refused"
    response.url = "https://catalog.example/data.json"
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        return exc
    raise AssertionError(status)


class WhyTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("en")

    @needs_posix_permissions
    def test_a_folder_it_may_not_write_names_the_path(self) -> None:
        locked = self.root / "locked"
        locked.mkdir(mode=0o500)
        self.addCleanup(locked.chmod, 0o700)

        with self.assertRaises(PermissionError) as raised:
            (locked / "one.txt").write_text("x", encoding="utf-8")

        self.assertEqual(why(raised.exception),
                         f"VPinFE does not have permission for {locked / 'one.txt'}")

    def test_a_file_failure_with_no_path_says_it_plainly(self) -> None:
        self.assertEqual(why(OSError(errno.ENOSPC, "No space left on device")),
                         "The disk is full")

    def test_nothing_at_a_path(self) -> None:
        with self.assertRaises(FileNotFoundError) as raised:
            (self.root / "gone.vpx").read_bytes()

        self.assertEqual(why(raised.exception), f"Nothing is at {self.root / 'gone.vpx'}")

    def test_a_port_nothing_listens_on(self) -> None:
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            port = free.getsockname()[1]

        with self.assertRaises(requests.ConnectionError) as raised:
            requests.get(f"http://127.0.0.1:{port}/", timeout=5)

        self.assertEqual(why(raised.exception), "Nothing answers at 127.0.0.1")

    def test_a_host_that_did_not_answer_in_time(self) -> None:
        request = requests.Request("GET", "https://catalog.example/data.json").prepare()

        self.assertEqual(why(requests.ReadTimeout(request=request)),
                         "catalog.example did not answer in time")

    def test_what_a_host_answered(self) -> None:
        self.assertEqual([why(_answered(status)) for status in (404, 403, 503)],
                         ["catalog.example does not have it", "catalog.example refused it",
                          "catalog.example is having trouble"])

    def test_a_host_that_asked_to_wait(self) -> None:
        said = why(HostQuietError("api.example", 0.0))

        self.assertTrue(said.startswith("api.example asked VPinFE to wait until "), said)

    def test_anything_else_is_the_exception_s_own_text(self) -> None:
        self.assertEqual([why(ValueError("Unexpected end of archive")), why(KeyError()),
                          why(OSError(errno.EIO, "Input/output error")), why(_answered(418))],
                         ["Unexpected end of archive", "KeyError",
                          "[Errno 5] Input/output error",
                          "418 Client Error: Refused for url: https://catalog.example/data.json"])


if __name__ == "__main__":
    unittest.main()
