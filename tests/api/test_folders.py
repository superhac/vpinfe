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

    def _get(self, path: str = "", *, kind: str = "", suffix: list[str] | None = None):
        params: dict[str, str | list[str]] = {}
        if path:
            params["path"] = path
        if kind:
            params["kind"] = kind
        if suffix:
            params["suffix"] = suffix
        return self.client.get("/folders", params=params)

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

    def test_kind_exe_lists_an_executable_and_omits_a_non_executable_file(self) -> None:
        if sys.platform == "win32":
            self.skipTest("Windows decides this by PATHEXT, not os.access")
        runnable = self.root / "runme"
        runnable.write_text("#!/bin/sh\n")
        runnable.chmod(0o755)
        (self.root / "notes.txt").write_text("not executable")

        body = self._get(str(self.root), kind="exe").json()

        self.assertEqual([f["name"] for f in body["files"]], ["runme"])

    def test_kind_file_with_a_suffix_lists_only_that_suffix(self) -> None:
        (self.root / "a.ini").write_text("")
        (self.root / "b.txt").write_text("")

        body = self._get(str(self.root), kind="file", suffix=[".ini"]).json()

        self.assertEqual([f["name"] for f in body["files"]], ["a.ini"])

    def test_kind_file_with_no_suffix_lists_every_file(self) -> None:
        (self.root / "a.ini").write_text("")
        (self.root / "b.txt").write_text("")

        body = self._get(str(self.root), kind="file").json()

        self.assertEqual(sorted(f["name"] for f in body["files"]), ["a.ini", "b.txt"])

    def test_hidden_files_are_omitted(self) -> None:
        (self.root / ".hidden").write_text("")
        (self.root / "visible.txt").write_text("")

        body = self._get(str(self.root), kind="file").json()

        self.assertEqual([f["name"] for f in body["files"]], ["visible.txt"])

    def test_a_private_folders_files_are_never_listed(self) -> None:
        private = self.root / ".ssh"
        private.mkdir()
        (private / "id_ed25519").write_text("not a real key")

        with patch("common.folder_browse.Path.home", return_value=self.root):
            response = self._get(str(private), kind="file")

        self.assertEqual(response.status_code, 400)

    def test_a_file_path_lists_its_folder(self) -> None:
        child = self.root / "child"
        child.mkdir()
        (child / "table.vpx").write_text("")

        body = self._get(str(child / "table.vpx"), kind="file").json()

        self.assertEqual(body["path"], str(child))
        self.assertEqual([f["name"] for f in body["files"]], ["table.vpx"])

    def test_kind_exe_with_an_empty_path_starts_at_one_of_its_roots(self) -> None:
        body = self._get(kind="exe").json()

        self.assertIn(body["path"], [root["path"] for root in body["roots"]])

    def test_an_unknown_kind_is_refused(self) -> None:
        response = self._get(str(self.root), kind="folder")

        self.assertEqual(response.status_code, 400)

    def test_a_network_caller_is_refused_for_any_kind(self) -> None:
        with patch("httpapi.folders.caller_is_local", return_value=False):
            response = self._get(str(self.root), kind="exe")

        self.assertEqual(response.status_code, 403)

    def test_an_app_bundle_lands_in_files_under_exe(self) -> None:
        if sys.platform != "darwin":
            self.skipTest("`.app` bundles are a macOS thing")
        (self.root / "Pinball.app" / "Contents" / "MacOS").mkdir(parents=True)

        body = self._get(str(self.root), kind="exe").json()

        self.assertEqual([f["name"] for f in body["folders"]], [])
        self.assertEqual([f["name"] for f in body["files"]], ["Pinball.app"])


if __name__ == "__main__":
    unittest.main()
