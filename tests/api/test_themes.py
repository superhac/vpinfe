"""Theme calls over HTTP."""

from __future__ import annotations

import errno
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import httpapi
from common.i18n import t
from common.online import theme_ops
from tests.support.library import TempTree


class SourcesThatWillNotLoadTests(TempTree):
    CALLS: tuple[tuple[str, str, dict | None], ...] = (
             ("get", "/themes", None),
             ("post", "/themes/Reference/install", None),
             ("delete", "/themes/Reference", None),
             ("put", "/themes/active", {"key": "Reference"}),
             ("get", "/themes/Reference/options", None),
             ("put", "/themes/Reference/options", {"values": {}}))

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        self.enterContext(patch.object(
            theme_ops, "_loaded",
            side_effect=OSError(errno.EHOSTUNREACH, "No route to host")))

    def test_every_call_says_so_in_words_rather_than_breaking(self) -> None:
        said = t("said.why.unreachable")
        for method, path, body in self.CALLS:
            with self.subTest(method=method, path=path):
                answer = self.client.request(method, path, json=body)

                self.assertEqual(answer.status_code, 503)
                self.assertEqual(answer.json()["error"]["message"], said)


class NoThemeNamedTests(TempTree):
    def test_making_no_theme_active_asks_for_its_name(self) -> None:
        client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        with patch.object(theme_ops, "_loaded"):
            answer = client.put("/themes/active", json={"key": " "})

        self.assertEqual(answer.status_code, 400)
        self.assertEqual(answer.json()["error"]["message"],
                         t("error.themes.name_theme_to_activate"))


if __name__ == "__main__":
    unittest.main()
