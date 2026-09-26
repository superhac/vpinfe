"""Theme calls over HTTP when the theme sources cannot be read."""

from __future__ import annotations

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
        self.enterContext(patch.object(theme_ops, "_loaded",
                                       side_effect=OSError("no route to host")))

    def test_every_call_says_so_in_words_rather_than_breaking(self) -> None:
        said = t("error.themes.could_not_read_theme", exc=OSError("no route to host"))
        for method, path, body in self.CALLS:
            with self.subTest(method=method, path=path):
                answer = self.client.request(method, path, json=body)

                self.assertEqual(answer.status_code, 503)
                self.assertEqual(answer.json()["error"]["message"], said)


if __name__ == "__main__":
    unittest.main()
