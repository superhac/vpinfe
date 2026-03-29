import unittest

from common.score_parser import ParsedEntry, result_to_jsonable


class TestScoreParser(unittest.TestCase):
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
                        "value_suffix": None,
                        "extra_lines": [],
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
                        "value_suffix": None,
                        "extra_lines": [],
                    }
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
