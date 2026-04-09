import unittest
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import json
import tempfile

if "platformdirs" not in sys.modules:
    platformdirs = types.ModuleType("platformdirs")
    platformdirs.user_config_dir = lambda *args, **kwargs: "/tmp"
    sys.modules["platformdirs"] = platformdirs

_test_config_dir = Path(tempfile.mkdtemp(prefix="vpinfe-score-parser-test-"))
(_test_config_dir / "roms.json").write_text(
    json.dumps(
        {
            "agent777": {"scoretype": "HIGH SCORE", "decoder": "dummy"},
            "aar_101": {"scoretype": "Leaderboard", "decoder": "dummy"},
            "Matrix": {"scoretype": "HIGH SCORE", "decoder": "dummy"},
        }
    ),
    encoding="utf-8",
)
sys.modules["platformdirs"].user_config_dir = lambda *args, **kwargs: str(_test_config_dir)

from common import score_parser
from common.score_parser import ParsedEntry, result_to_jsonable


class TestScoreParser(unittest.TestCase):
    def test_get_roms_path_prefers_user_config_copy(self) -> None:
        with TemporaryDirectory() as temp_dir:
            roms_path = Path(temp_dir) / "roms.json"
            roms_path.write_text('{"foo": {"scoretype": "HIGH SCORE"}}', encoding="utf-8")
            with mock.patch.object(score_parser, "USER_ROMS_PATH", roms_path):
                self.assertEqual(score_parser.get_roms_path(), roms_path)

    def test_result_to_jsonable_returns_direct_score_payload_for_scalar_scores(self) -> None:
        result = result_to_jsonable("agent777", 123456)

        self.assertEqual(
            result,
            {
                "rom": "agent777",
                "resolved_rom": "agent777",
                "score_type": "HIGH SCORE",
                "value": 123456,
            },
        )

    def test_result_to_jsonable_filters_empty_entries(self) -> None:
        result = result_to_jsonable(
            "aar_101",
            [
                ParsedEntry(section="HIGH SCORES", rank=1, initials="AAA", score=1000),
                ParsedEntry(section="HIGH SCORES", rank=2, initials="", score=None),
            ],
        )

        self.assertEqual(
            result,
            {
                "rom": "aar_101",
                "resolved_rom": "aar_101",
                "score_type": "Leaderboard",
                "entries": [
                    {
                        "section": "HIGH SCORES",
                        "rank": 1,
                        "initials": "AAA",
                        "score": 1000,
                        "value_prefix": None,
                        "value_suffix": None,
                        "value_format": None,
                        "extra_lines": [],
                        "multiline": False,
                    }
                ],
            },
        )

    def test_result_to_jsonable_uses_ini_score_type_for_ini_sources(self) -> None:
        result = result_to_jsonable(
            "Matrix",
            [ParsedEntry(section="Scores", rank=1, initials="NEO", score=424242)],
            "/tmp/VPReg.ini",
        )

        self.assertEqual(
            result,
            {
                "rom": "Matrix",
                "resolved_rom": "Matrix",
                "score_type": "ini",
                "entries": [
                    {
                        "section": "Scores",
                        "rank": 1,
                        "initials": "NEO",
                        "score": 424242,
                        "value_prefix": None,
                        "value_suffix": None,
                        "value_format": None,
                        "extra_lines": [],
                        "multiline": False,
                    }
                ],
            },
        )

    def test_result_to_jsonable_uses_vpinplay_initials_for_blank_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "vpinfe.ini"
            config_path.write_text("[vpinplay]\ninitials = JSM\n", encoding="utf-8")
            with mock.patch.object(score_parser, "USER_CONFIG_PATH", config_path):
                result = result_to_jsonable(
                    "aar_101",
                    [ParsedEntry(section="HIGH SCORES", rank=1, initials="", score=1000)],
                )

        self.assertEqual(
            result,
            {
                "rom": "aar_101",
                "resolved_rom": "aar_101",
                "score_type": "Leaderboard",
                "entries": [
                    {
                        "section": "HIGH SCORES",
                        "rank": 1,
                        "initials": "JSM",
                        "score": 1000,
                        "value_prefix": None,
                        "value_suffix": None,
                        "value_format": None,
                        "extra_lines": [],
                        "multiline": False,
                    }
                ],
            },
        )

    def test_result_to_jsonable_preserves_existing_initials(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "vpinfe.ini"
            config_path.write_text("[vpinplay]\ninitials = JSM\n", encoding="utf-8")
            with mock.patch.object(score_parser, "USER_CONFIG_PATH", config_path):
                result = result_to_jsonable(
                    "aar_101",
                    [ParsedEntry(section="HIGH SCORES", rank=1, initials="AAA", score=1000)],
                )

        self.assertEqual(result["entries"][0]["initials"], "AAA")

    def test_result_to_jsonable_does_not_fill_blank_non_score_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "vpinfe.ini"
            config_path.write_text("[vpinplay]\ninitials = JSM\n", encoding="utf-8")
            with mock.patch.object(score_parser, "USER_CONFIG_PATH", config_path):
                result = result_to_jsonable(
                    "aar_101",
                    [ParsedEntry(section="HIGH SCORES", rank=1, initials="", extra_lines=["SPECIAL"])],
                )

        self.assertEqual(result["entries"][0]["initials"], "")


if __name__ == "__main__":
    unittest.main()
