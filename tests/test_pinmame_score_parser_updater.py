from __future__ import annotations

import configparser
import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


if "platformdirs" not in sys.modules:
    platformdirs = types.ModuleType("platformdirs")
    platformdirs.user_config_dir = lambda *args, **kwargs: "/tmp"
    sys.modules["platformdirs"] = platformdirs

if "requests" not in sys.modules:
    requests = types.ModuleType("requests")
    sys.modules["requests"] = requests


updater = importlib.import_module("common.pinmame_score_parser_updater")


class _FakeIniConfig:
    def __init__(self, path: Path) -> None:
        self.configfilepath = path
        self.config = configparser.ConfigParser()
        self.config.add_section("pinmame-score-parser")

    def save(self) -> None:
        with open(self.configfilepath, "w", encoding="utf-8") as fh:
            self.config.write(fh)


class _FakeStreamResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int = 1024 * 1024):
        yield self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


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
            ini = _FakeIniConfig(temp_path / "vpinfe.ini")

            with mock.patch.object(updater, "CONFIG_DIR", temp_path), \
                mock.patch.object(updater, "ROMS_JSON_PATH", temp_path / "roms.json"), \
                mock.patch.object(updater, "_request_json", return_value=release_payload), \
                mock.patch.object(updater, "requests") as mock_requests:
                mock_requests.get.return_value = _FakeStreamResponse(roms_bytes)

                result = updater.ensure_latest_roms_json(ini)

            self.assertEqual(result["status"], "downloaded")
            self.assertEqual((temp_path / "roms.json").read_bytes(), roms_bytes)
            self.assertEqual(
                ini.config.get("pinmame-score-parser", "romsupdatesha"),
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
            ini = _FakeIniConfig(temp_path / "vpinfe.ini")
            ini.config.set("pinmame-score-parser", "romsupdatesha", roms_sha)

            with mock.patch.object(updater, "CONFIG_DIR", temp_path), \
                mock.patch.object(updater, "ROMS_JSON_PATH", temp_path / "roms.json"), \
                mock.patch.object(updater, "_request_json", return_value=release_payload), \
                mock.patch.object(updater, "requests") as mock_requests:
                result = updater.ensure_latest_roms_json(ini)

            self.assertEqual(result["status"], "up_to_date")
            mock_requests.get.assert_not_called()
