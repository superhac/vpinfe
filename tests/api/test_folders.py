"""Browsing this machine for a folder, over the wire."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import httpapi
from tests.support.library import TempTree

# One non-dot private folder per platform, to prove a parent listing omits a private
# child that dot-folder filtering alone would not catch.
_NON_DOT_PRIVATE = {
    "darwin": ("Library", "Keychains"),
    "linux": (".config", "google-chrome"),
    "win32": ("AppData/Roaming/Microsoft", "Credentials"),
}


def _client() -> TestClient:
    return TestClient(httpapi.create_api_app(), raise_server_exceptions=False)


class FolderApiTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.client = _client()

    def _get(self, path: str = ""):
        return self.client.get("/folders", params={"path": path} if path else {})

    def test_only_subfolders_are_listed_sorted_by_name(self) -> None:
        (self.root / "bravo").mkdir()
        (self.root / "Alpha").mkdir()
        (self.root / ".hidden").mkdir()
        (self.root / "a file.txt").write_text("not a folder")

        body = self._get(str(self.root)).json()

        self.assertEqual([f["name"] for f in body["folders"]], ["Alpha", "bravo"])

    def test_a_subfolders_parent_is_its_parent(self) -> None:
        child = self.root / "child"
        child.mkdir()

        body = self._get(str(child)).json()

        self.assertEqual(body["parent"], str(self.root))

    def test_a_missing_path_is_not_found(self) -> None:
        response = self._get(str(self.root / "nowhere"))

        self.assertEqual(response.status_code, 404)

    def test_an_empty_path_answers_the_home_folder(self) -> None:
        with patch("common.folder_browse.Path.home", return_value=self.root):
            body = self._get("").json()

        self.assertEqual(body["path"], str(self.root))

    def test_roots_is_never_empty(self) -> None:
        body = self._get(str(self.root)).json()

        self.assertTrue(body["roots"])

    def test_a_network_caller_is_refused(self) -> None:
        with patch("httpapi.folders.caller_is_local", return_value=False):
            response = self._get(str(self.root))

        self.assertEqual(response.status_code, 403)

    def test_a_private_folder_cannot_be_listed(self) -> None:
        (self.root / ".ssh").mkdir()

        with patch("common.folder_browse.Path.home", return_value=self.root):
            response = self._get(str(self.root / ".ssh"))

        self.assertEqual(response.status_code, 400)

    def test_a_private_folder_is_omitted_from_its_parent(self) -> None:
        case = _NON_DOT_PRIVATE.get(sys.platform)
        if case is None:
            self.skipTest(f"no non-dot private-folder case recorded for {sys.platform}")
        parent_rel, child_name = case
        parent = self.root / parent_rel
        parent.mkdir(parents=True)
        (parent / child_name).mkdir()
        (parent / "visible").mkdir()

        with patch("common.folder_browse.Path.home", return_value=self.root):
            body = self._get(str(parent)).json()

        self.assertEqual([f["name"] for f in body["folders"]], ["visible"])


if __name__ == "__main__":
    unittest.main()
