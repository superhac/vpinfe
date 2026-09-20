import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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
from common.games import score_parser
from common.games.score_parser import ParsedEntry, result_to_jsonable


@contextlib.contextmanager
def _initials_held_by(extension: str = "", config: str = ""):
    """The two places initials can live, so a test says which one is answering."""
    store = type("_Store", (), {
        "settings": lambda _self, _name: {"initials": extension} if extension else {},
    })()
    with mock.patch.object(score_parser, "get_extension_store", lambda: store), \
            mock.patch.object(score_parser, "get_ini_config",
                              lambda: {"vpinplay": {"initials": config}}), \
            mock.patch.object(score_parser, "cfg_get",
                              lambda src, section, key, default="":
                                  (src.get(section) or {}).get(key) or default):
        yield


class TestScoreParser(unittest.TestCase):
    def test_get_roms_path_resolves_to_the_user_config_copy(self) -> None:
        with TemporaryDirectory() as temp_dir:
            roms_path = Path(temp_dir) / "roms.json"
            roms_path.write_text('{"foo": {"scoretype": "HIGH SCORE"}}', encoding="utf-8")
            with mock.patch.object(score_parser, "USER_ROMS_PATH", roms_path):
                self.assertEqual(score_parser.get_roms_candidate_paths(), [roms_path])
                self.assertEqual(score_parser.get_roms_path(), roms_path)

    def test_get_roms_path_error_names_the_path_it_checked(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "roms.json"
            with mock.patch.object(score_parser, "USER_ROMS_PATH", missing_path):
                with self.assertRaises(FileNotFoundError) as ctx:
                    score_parser.get_roms_path()

        self.assertIn(str(missing_path), str(ctx.exception))

    def test_result_to_jsonable_returns_direct_score_payload_for_scalar_scores(self) -> None:
        result = result_to_jsonable("agent777", 123456)

        self.assertEqual(
            result,
            {
                "rom": "agent777",
                "resolved_rom": "agent777",
                "score_kind": "HIGH SCORE",
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
                "score_kind": "Leaderboard",
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
                "score_kind": "ini",
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
        with _initials_held_by(extension="JSM"):
            result = result_to_jsonable(
                "aar_101",
                [ParsedEntry(section="HIGH SCORES", rank=1, initials="", score=1000)],
            )

        self.assertEqual(
            result,
            {
                "rom": "aar_101",
                "resolved_rom": "aar_101",
                "score_kind": "Leaderboard",
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

    def test_initials_come_from_the_extension_that_holds_them(self) -> None:
        """The handover moved them there, and its settings surface is where they are
        typed, so a config left holding an older answer does not win."""
        with _initials_held_by(extension="NEO", config="OLD"):
            self.assertEqual(score_parser.get_default_initials(), "NEO")

    def test_the_config_answers_when_the_extension_holds_none(self) -> None:
        """An install that has not run the handover yet, or has VPinPlay switched off."""
        with _initials_held_by(config="OLD"):
            self.assertEqual(score_parser.get_default_initials(), "OLD")

    def test_initials_nobody_has_set_are_blank(self) -> None:
        with _initials_held_by():
            self.assertEqual(score_parser.get_default_initials(), "")

    def test_result_to_jsonable_preserves_existing_initials(self) -> None:
        with _initials_held_by(extension="JSM"):
            result = result_to_jsonable(
                "aar_101",
                [ParsedEntry(section="HIGH SCORES", rank=1, initials="AAA", score=1000)],
            )

        self.assertEqual(result["entries"][0]["initials"], "AAA")

    def test_result_to_jsonable_does_not_fill_blank_non_score_entries(self) -> None:
        with _initials_held_by(extension="JSM"):
            result = result_to_jsonable(
                "aar_101",
                [ParsedEntry(section="HIGH SCORES", rank=1, initials="",
                             extra_lines=["SPECIAL"])],
            )

        self.assertEqual(result["entries"][0]["initials"], "")

    def test_resolve_score_input_path_prefers_nvram_for_game_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir)
            nvram_path = game_dir / "pinmame" / "nvram" / "agent777.nv"
            vpreg_path = game_dir / "user" / "VPReg.ini"
            nvram_path.parent.mkdir(parents=True)
            vpreg_path.parent.mkdir(parents=True)
            nvram_path.write_bytes(b"nv")
            vpreg_path.write_text("[Dummy]\n", encoding="utf-8")

            resolved = score_parser.resolve_score_input_path("agent777", str(game_dir))

        self.assertEqual(resolved, str(nvram_path))

    def test_resolve_score_input_path_falls_back_to_vpreg_ini(self) -> None:
        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir)
            vpreg_path = game_dir / "user" / "VPReg.ini"
            vpreg_path.parent.mkdir(parents=True)
            vpreg_path.write_text("[Dummy]\n", encoding="utf-8")

            resolved = score_parser.resolve_score_input_path("agent777", str(game_dir))

        self.assertEqual(resolved, str(vpreg_path))

    def test_resolve_rom_name_matches_rom_entries_case_insensitively(self) -> None:
        self.assertEqual(score_parser.resolve_rom_name("matrix"), "Matrix")

    def test_resolve_score_input_path_matches_nvram_case_insensitively(self) -> None:
        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir)
            nvram_path = game_dir / "pinmame" / "nvram" / "Matrix.nv"
            nvram_path.parent.mkdir(parents=True)
            nvram_path.write_bytes(b"nv")

            resolved = score_parser.resolve_score_input_path("matrix", str(game_dir))

        self.assertEqual(resolved, str(nvram_path))

    def test_read_rom_with_source_returns_resolved_special_text_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir)
            text_path = game_dir / "user" / "OKIES.txt"
            text_path.parent.mkdir(parents=True)
            text_path.write_text("123456\n", encoding="utf-8")

            with mock.patch.object(score_parser, "decode_special_text_score_file",
                                   return_value=123456) as decoder:
                result, resolved = score_parser.read_rom_with_source(
                    "OKIES_TornadoRally", str(game_dir))

        decoder.assert_called_once_with("OKIES_TornadoRally", str(text_path))
        self.assertEqual(result, 123456)
        self.assertEqual(resolved, str(text_path))

    def test_read_rom_with_source_parses_expressway_score_text(self) -> None:
        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir)
            text_path = game_dir / "user" / "Expressway.txt"
            text_path.parent.mkdir(parents=True)
            text_path.write_text("playerscore1    10100\n", encoding="utf-8")

            result, resolved = score_parser.read_rom_with_source("Expressway", str(game_dir))

        self.assertEqual(resolved, str(text_path))
        self.assertEqual(result, [ParsedEntry(section="", rank=None, initials="", score=10100)])

    def test_decode_ini_file_skips_blank_scores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ini_path = Path(temp_dir) / "VPReg.ini"
            ini_path.write_text(
                "\n".join(
                    [
                        "[Aerosmith]",
                        "Score1Name = AAA",
                        "Score1 = ",
                        "Score2Name = BBB",
                        "Score2 = 12,345",
                        "Hiscore = ",
                        "[Other]",
                        "Highscore = 100",
                    ]
                ),
                encoding="utf-8",
            )

            result = score_parser.decode_ini_file(str(ini_path))

        self.assertEqual(
            result,
            [
                ParsedEntry(section="Score", rank=2, initials="BBB", score=12345),
                ParsedEntry(section="Other", rank=None, initials="", score=100),
            ],
        )


if __name__ == "__main__":
    unittest.main()
