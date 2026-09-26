from __future__ import annotations

import configparser
import importlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

updater = importlib.import_module("common.online.pinmame_score_parser_updater")


class _FakeConfigStore:
    def __init__(self, path: Path) -> None:
        self.configfilepath = path
        self.config = configparser.ConfigParser()
        self.config.add_section("pinmame_score_parser")

    def save(self) -> None:
        with open(self.configfilepath, "w", encoding="utf-8") as fh:
            self.config.write(fh)


class TestPinmameScoreParserUpdater(unittest.TestCase):
    def test_ensure_latest_roms_json_downloads_and_tracks_release_digest(self) -> None:
        roms_bytes = json.dumps({"foo": {"scoretype": "HIGH SCORE"}}).encode("utf-8")
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "roms.json",
                    "browser_download_url": "https://example.invalid/roms.json",
                    "digest": f"sha256:{updater.hashlib.sha256(roms_bytes).hexdigest()}",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            ini = _FakeConfigStore(temp_path / "vpinfe.ini")

            with mock.patch.object(updater, "CONFIG_DIR", temp_path), \
                mock.patch.object(updater, "ROMS_JSON_PATH", temp_path / "roms.json"), \
                mock.patch.object(updater, "_request_json", return_value=release_payload), \
                mock.patch.object(updater.http_client, "download_file",
                                  side_effect=lambda url, dest, **_: dest.write_bytes(roms_bytes)):
                result = updater.ensure_latest_roms_json(ini)

            self.assertEqual(result["status"], "downloaded")
            self.assertEqual((temp_path / "roms.json").read_bytes(), roms_bytes)
            self.assertEqual(
                ini.config.get("pinmame_score_parser", "roms_update_sha"),
                updater.hashlib.sha256(roms_bytes).hexdigest(),
            )

    def test_ensure_latest_roms_json_skips_download_when_digest_matches(self) -> None:
        roms_bytes = json.dumps({"foo": {"scoretype": "HIGH SCORE"}}).encode("utf-8")
        roms_sha = updater.hashlib.sha256(roms_bytes).hexdigest()
        release_payload = {
            "assets": [
                {
                    "name": "roms.json",
                    "browser_download_url": "https://example.invalid/roms.json",
                    "digest": f"sha256:{roms_sha}",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "roms.json").write_bytes(roms_bytes)
            ini = _FakeConfigStore(temp_path / "vpinfe.ini")
            ini.config.set("pinmame_score_parser", "roms_update_sha", roms_sha)

            with mock.patch.object(updater, "CONFIG_DIR", temp_path), \
                mock.patch.object(updater, "ROMS_JSON_PATH", temp_path / "roms.json"), \
                mock.patch.object(updater, "_request_json", return_value=release_payload), \
                mock.patch.object(updater.http_client, "download_file") as download:
                result = updater.ensure_latest_roms_json(ini)

            self.assertEqual(result["status"], "up_to_date")
            download.assert_not_called()
            self.assertTrue(ini.config.get("pinmame_score_parser", "roms_checked"))


class TestAskedOnceADay(unittest.TestCase):
    """A start does not ask GitHub for the release it asked about in the last day."""

    RELEASE = {"assets": [{"name": "roms.json",
                           "browser_download_url": "https://example.invalid/roms.json",
                           "digest": "sha256:abc"}]}

    def setUp(self) -> None:
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        self.root = Path(held.name)
        self.ini = _FakeConfigStore(self.root / "vpinfe.ini")
        self.ini.config.set("pinmame_score_parser", "roms_update_sha", "abc")
        for one in (mock.patch.object(updater, "CONFIG_DIR", self.root),
                    mock.patch.object(updater, "ROMS_JSON_PATH", self.root / "roms.json")):
            one.start()
            self.addCleanup(one.stop)

    def _checked(self, hours_ago: float) -> None:
        self.ini.config.set("pinmame_score_parser", "roms_checked",
                            updater.timestamps.epoch_to_iso(time.time() - hours_ago * 3600))

    def _run(self, **lookup: Any) -> tuple[dict | None, mock.MagicMock]:
        with mock.patch.object(updater, "_request_json", **lookup) as asked:
            try:
                return updater.ensure_latest_roms_json(self.ini), asked
            except OSError:
                return None, asked

    def test_checked_today_is_not_asked(self) -> None:
        (self.root / "roms.json").write_text("{}")
        self._checked(hours_ago=23)
        result, asked = self._run(return_value=self.RELEASE)
        asked.assert_not_called()
        self.assertEqual((result or {}).get("status"), "checked_recently")

    def test_checked_yesterday_is_asked_and_stamped(self) -> None:
        (self.root / "roms.json").write_text("{}")
        self._checked(hours_ago=25)
        before = self.ini.config.get("pinmame_score_parser", "roms_checked")
        result, asked = self._run(return_value=self.RELEASE)
        asked.assert_called_once()
        self.assertEqual((result or {}).get("status"), "up_to_date")
        self.assertNotEqual(self.ini.config.get("pinmame_score_parser", "roms_checked"),
                            before)

    def test_a_missing_file_is_asked_for_however_recent_the_check(self) -> None:
        self._checked(hours_ago=1)
        _, asked = self._run(side_effect=OSError("offline"))
        asked.assert_called_once()

    def test_a_failed_lookup_leaves_the_stamp_alone(self) -> None:
        (self.root / "roms.json").write_text("{}")
        self._checked(hours_ago=30)
        before = self.ini.config.get("pinmame_score_parser", "roms_checked")
        result, asked = self._run(side_effect=OSError("offline"))
        asked.assert_called_once()
        self.assertIsNone(result)
        self.assertEqual(self.ini.config.get("pinmame_score_parser", "roms_checked"), before)
