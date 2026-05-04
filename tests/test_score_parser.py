import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import json
import tempfile

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

from common import paths
paths.USER_ROMS_PATH = _test_config_dir / "roms.json"
paths.USER_CONFIG_PATH = _test_config_dir / "vpinfe.ini"
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

    def test_resolve_score_input_path_prefers_nvram_for_table_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir)
            nvram_path = table_dir / "pinmame" / "nvram" / "agent777.nv"
            vpreg_path = table_dir / "user" / "VPReg.ini"
            nvram_path.parent.mkdir(parents=True)
            vpreg_path.parent.mkdir(parents=True)
            nvram_path.write_bytes(b"nv")
            vpreg_path.write_text("[Dummy]\n", encoding="utf-8")

            resolved = score_parser.resolve_score_input_path("agent777", str(table_dir))

        self.assertEqual(resolved, str(nvram_path))

    def test_resolve_score_input_path_falls_back_to_vpreg_ini(self) -> None:
        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir)
            vpreg_path = table_dir / "user" / "VPReg.ini"
            vpreg_path.parent.mkdir(parents=True)
            vpreg_path.write_text("[Dummy]\n", encoding="utf-8")

            resolved = score_parser.resolve_score_input_path("agent777", str(table_dir))

        self.assertEqual(resolved, str(vpreg_path))

    def test_resolve_rom_name_matches_rom_entries_case_insensitively(self) -> None:
        self.assertEqual(score_parser.resolve_rom_name("matrix"), "Matrix")

    def test_resolve_score_input_path_matches_nvram_case_insensitively(self) -> None:
        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir)
            nvram_path = table_dir / "pinmame" / "nvram" / "Matrix.nv"
            nvram_path.parent.mkdir(parents=True)
            nvram_path.write_bytes(b"nv")

            resolved = score_parser.resolve_score_input_path("matrix", str(table_dir))

        self.assertEqual(resolved, str(nvram_path))

    def test_read_rom_with_source_returns_resolved_special_text_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir)
            text_path = table_dir / "user" / "OKIES.txt"
            text_path.parent.mkdir(parents=True)
            text_path.write_text("123456\n", encoding="utf-8")

            with mock.patch.object(score_parser, "decode_special_text_score_file", return_value=123456) as decoder:
                result, resolved = score_parser.read_rom_with_source("OKIES_TornadoRally", str(table_dir))

        decoder.assert_called_once_with("OKIES_TornadoRally", str(text_path))
        self.assertEqual(result, 123456)
        self.assertEqual(resolved, str(text_path))

    def test_read_rom_with_source_parses_expressway_score_text(self) -> None:
        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir)
            text_path = table_dir / "user" / "Expressway.txt"
            text_path.parent.mkdir(parents=True)
            text_path.write_text("playerscore1    10100\n", encoding="utf-8")

            result, resolved = score_parser.read_rom_with_source("Expressway", str(table_dir))

        self.assertEqual(resolved, str(text_path))
        self.assertEqual(result, [ParsedEntry(section="", rank=None, initials="", score=10100)])


if __name__ == "__main__":
    unittest.main()
