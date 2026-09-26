"""What the Console's API client raises when nothing answers it."""

from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

import requests

from common.i18n import t
from console.api import ApiClient, ApiError


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class NothingAnsweredTests(unittest.TestCase):
    def test_nothing_on_the_port_is_said_in_words(self) -> None:
        client = ApiClient(f"http://127.0.0.1:{_closed_port()}")

        with self.assertRaises(ApiError) as caught:
            client.discovery()

        self.assertEqual(str(caught.exception), t("device.reason.refused"))
        self.assertIsInstance(caught.exception.__cause__, requests.ConnectionError)

    def test_an_answer_that_never_came_says_it_may_be_asleep(self) -> None:
        with patch.object(requests.adapters.HTTPAdapter, "send",
                          side_effect=requests.ReadTimeout()), \
                self.assertRaises(ApiError) as caught:
            ApiClient("http://127.0.0.1:1").set_favorite("g1", True)

        self.assertEqual(str(caught.exception), t("device.reason.timed_out"))


if __name__ == "__main__":
    unittest.main()
