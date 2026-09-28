"""The High Scores group in a game's Play section, as rows before anything is drawn."""

from __future__ import annotations

import unittest

from common.games import high_scores
from common.i18n import t
from common.labels import field_label
from console import panel
from console.workbench import _high_score_rows, _score_lines
from tests.games.test_high_scores import CHAMPION_AND_RANKED, MULTILINE, ONE_NUMBER


def _table(table_id: str, filename: str, rom: str, **rest) -> dict:
    return {"id": table_id, "filename": filename,
            "dependencies": {"pinmame": {"declared": rom}}, **rest}


TABLES = [_table("t1", "Example.vpx", "abc_l1", default=True,
                 overrides={"delete_nvram_on_close": False}),
          _table("t2", "Example (Mod).vpx", "abc_l1",
                 overrides={"delete_nvram_on_close": True})]


def _scores(reading: dict, *, table_id: str = "t1", new: tuple[int, ...] = ()) -> dict:
    held = high_scores.record(reading, None, "2026-09-27T12:00:00Z")
    held["new"] = list(new)
    return high_scores.shown("abc_l1", table_id, held)


def _context(lens: str = "", tables: list[dict] | None = None) -> dict:
    return {"lens": lens, "tables": tables if tables is not None else TABLES}


def _aside(rows: list) -> list[tuple[str, str]]:
    """The lines under the heading, as (text, hint)."""
    (drawn,) = [value for label, value in rows if label is panel.LEDE]
    return drawn.args[0]


def _labels(rows: list) -> list:
    return [label for label, _value in rows if label not in (panel.LEDE, panel.ASIDE)]


class HighScoreRowsTests(unittest.TestCase):
    def test_nothing_to_show_is_no_group(self) -> None:
        self.assertEqual(_high_score_rows(_context(), {}), [])

    def test_one_row_per_entry_the_section_named_on_its_first(self) -> None:
        rows = _high_score_rows(_context(), _scores(CHAMPION_AND_RANKED))

        self.assertEqual(_labels(rows), [panel.HEADING, "GRAND CHAMPION", "HIGH SCORES",
                                         "", ""])
        self.assertEqual(rows[0][1], t("console.workbench.high_scores"))

    def test_a_section_name_is_the_machines_word_not_a_catalog_one(self) -> None:
        reading = {"score_kind": "Leaderboard", "entries": [
            {"section": "ZORBLAX CHAMPION", "rank": None, "initials": "ABC", "score": 1}]}

        (label,) = _labels(_high_score_rows(_context(), _scores(reading)))[1:]

        self.assertEqual(field_label(label), "Zorblax Champion")

    def test_a_one_number_machine_is_one_row_under_the_maps_name(self) -> None:
        rows = _high_score_rows(_context(), _scores(ONE_NUMBER, new=(0,)))

        self.assertEqual(_labels(rows)[1:], ["HIGHEST SCORE"])

    def test_lines_past_the_first_sit_under_their_row(self) -> None:
        rows = _high_score_rows(_context(), _scores(MULTILINE))

        self.assertEqual([label for label, _value in rows].count(panel.ASIDE), 1)

    def test_a_state_with_nothing_to_list_is_one_line(self) -> None:
        for state in ("none", "unsupported", "unreadable"):
            with self.subTest(state=state):
                scores = high_scores.shown("abc_l1", "t1", None, state=state, reason="why")

                rows = _high_score_rows(_context(), scores)

                self.assertEqual([label for label, _value in rows],
                                 [panel.HEADING, panel.LEDE])

    def test_whose_table_is_named_only_where_the_roms_differ(self) -> None:
        mixed = [TABLES[0], _table("t2", "Example (Mod).vpx", "abc_mod")]

        same = _high_score_rows(_context(), _scores(CHAMPION_AND_RANKED))
        differ = _high_score_rows(_context(tables=mixed), _scores(CHAMPION_AND_RANKED))
        under_table = _high_score_rows(_context("t1", mixed), _scores(CHAMPION_AND_RANKED))

        said = [[text for text, _hint in _aside(rows)] for rows in (same, differ, under_table)]
        self.assertEqual([len(lines) for lines in said], [1, 2, 1])
        self.assertTrue(said[1][0].startswith("From"), said[1])

    def test_a_table_that_clears_on_exit_says_so_instead_of_when(self) -> None:
        rows = _high_score_rows(_context("t2"), _scores(CHAMPION_AND_RANKED, table_id="t2"))

        self.assertEqual(_aside(rows), [(t("console.workbench.high_scores_cleared"), "")])


class ScoreLinesTests(unittest.TestCase):
    def _entries(self, reading: dict) -> list[dict]:
        return [entry for section in _scores(reading)["sections"]
                for entry in section["entries"]]

    def test_a_number_is_grouped_as_the_language_groups_digits(self) -> None:
        first = self._entries(CHAMPION_AND_RANKED)[0]

        self.assertEqual(_score_lines(first), ["200,000,000"])

    def test_the_machines_words_stay_around_the_number(self) -> None:
        ruler, loops, combos, dollars = self._entries(MULTILINE)

        self.assertEqual([_score_lines(one) for one in (loops, combos, dollars)],
                         [["12 LOOPS"], ["4-WAY"], ["$ 5,000"]])
        self.assertEqual(_score_lines(ruler), ["INAUGURATED", "5 JAN, 2024 9:15 PM"])

    def test_a_number_the_machine_writes_its_own_way_is_left_as_written(self) -> None:
        entry = {"score": 255, "prefix": "", "suffix": "", "text": "FF"}

        self.assertEqual(_score_lines(entry), ["FF"])


if __name__ == "__main__":
    unittest.main()
