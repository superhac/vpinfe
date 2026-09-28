"""What each panel section holds, read from the rows it would draw."""

import unittest
from typing import Any

from nicegui import ui

from common.i18n import t
from console import game_tables, workbench


def _table(table_id: str, **extra: Any) -> dict[str, Any]:
    return {"id": table_id, "filename": f"{table_id}.vpx", "available": True,
            "features": {"ssf": True}, "user": {"tags": ["Night"]}, "rating": 3,
            **extra}


def _context(lens: str = "") -> dict[str, Any]:
    tables = [_table("alpha", default=True, default_kind=game_tables.DERIVED),
              _table("beta")]
    game = {"name": "Sample Game", "folder": "/library/Sample Game", "rating": 4,
            "user": {"favorite": True, "tags": ["Night"]}, "overrides": {}}
    return {"library": object(), "game": game, "game_id": "g1", "tables": tables,
            "launchers": [], "state": {}, "lens": lens, "redraws": [],
            "slot": {"kind": None}}


def _groups(entries: list[tuple[Any, Any]]) -> list[tuple[str, list[str]]]:
    """Each heading, in order, with the labels of the rows under it."""
    groups: list[tuple[str, list[str]]] = [("", [])]
    for label, value in entries:
        if label == workbench.HEADING:
            groups.append((value, []))
        elif isinstance(label, str):
            groups[-1][1].append(label)
    return [group for group in groups if group[0] or group[1]]


def _headings(entries: list[tuple[Any, Any]]) -> list[str]:
    return [heading for heading, _ in _groups(entries)]


def _under(entries: list[tuple[Any, Any]], heading: str) -> list[str]:
    return next(labels for name, labels in _groups(entries) if name == heading)


YOURS = t("console.workbench.yours")
RATING = t("console.workbench.your_rating")
FAVORITE = t("word.favorite")
PRIVATE = game_tables.PRIVATE_WORDS[0]
TAGS = t("console.workbench.tags")
MARKS = {RATING, FAVORITE, PRIVATE, TAGS}
DOF_EVENT = t("console.workbench.dof_event")


class GameSectionTests(unittest.TestCase):
    def setUp(self) -> None:
        context = _context()
        self.entries = workbench._game_entries(context, {}, [], held=False)

    def test_the_marks_sit_under_yours(self) -> None:
        self.assertEqual(_under(self.entries, YOURS), [RATING, FAVORITE, PRIVATE, TAGS])

    def test_yours_follows_the_details(self) -> None:
        headings = _headings(self.entries)

        self.assertEqual(headings.index(YOURS),
                         headings.index(t("console.workbench.details")) + 1)

    def test_the_dof_event_sits_under_frontend_after_yours(self) -> None:
        headings = _headings(self.entries)

        self.assertEqual(_under(self.entries, game_tables.FRONTEND), [DOF_EVENT])
        self.assertEqual(headings.index(game_tables.FRONTEND), headings.index(YOURS) + 1)


class TableSectionTests(unittest.TestCase):
    def setUp(self) -> None:
        context = _context()
        self.entries = workbench._table_entries(context["tables"][0], context)

    def test_the_marks_sit_under_yours(self) -> None:
        """A table has no favorite of its own: the game carries it."""
        self.assertEqual(_under(self.entries, YOURS), [RATING, TAGS])

    def test_yours_sits_between_what_the_file_is_and_how_it_runs(self) -> None:
        headings = _headings(self.entries)

        self.assertEqual(headings[headings.index(YOURS) - 1:headings.index(YOURS) + 2],
                         [game_tables.FEATURES, YOURS, game_tables.LAUNCH])

    def test_hidden_sits_in_launch(self) -> None:
        """Whether the frontend offers a file, beside whether and how it runs."""
        self.assertIn(t("word.hidden"), _under(self.entries, game_tables.LAUNCH))

    def test_the_default_is_not_set_here(self) -> None:
        """One place sets it: the game's Tables block, beside every candidate."""
        labels = {label for _, labels in _groups(self.entries) for label in labels}

        self.assertNotIn(game_tables.DEFAULT_LABEL, labels)

    def test_without_a_context_there_is_nothing_to_write_to(self) -> None:
        """The same facts drawn read-only elsewhere carry no marks."""
        entries = workbench._table_entries(_context()["tables"][0])

        self.assertNotIn(YOURS, _headings(entries))


def _radio(table: dict[str, Any]) -> tuple[ui.element, str]:
    """The radio a row draws, and its tooltip."""
    with ui.card() as card:
        workbench._default_mark(_context(), table, several=True)
    radio, tip = card.default_slot.children
    assert isinstance(tip, ui.tooltip)
    return radio, tip.text


class DefaultRadioTests(unittest.TestCase):
    """The radio on each row of the game's Tables block."""

    def test_a_hidden_row_s_radio_is_disabled_and_says_why(self) -> None:
        radio, tip = _radio(_table("beta", hidden=True))

        self.assertIn("opacity-30", radio.classes)
        self.assertNotIn("cursor-pointer", radio.classes)
        self.assertEqual(tip, t("console.game_tables.hidden_cannot_default"))

    def test_an_offered_row_s_radio_makes_it_the_default(self) -> None:
        radio, tip = _radio(_table("beta"))

        self.assertIn("cursor-pointer", radio.classes)
        self.assertEqual(tip, t("console.workbench.make_default"))


class PlaySectionTests(unittest.TestCase):
    def test_a_game_s_play_holds_no_marks(self) -> None:
        labels = {label for _, labels in _groups(workbench._play_entries(_context()))
                  for label in labels}

        self.assertFalse(labels & MARKS)

    def test_a_game_s_play_holds_only_its_record(self) -> None:
        labels = {label for _, labels in _groups(workbench._play_entries(_context()))
                  for label in labels}

        self.assertNotIn(DOF_EVENT, labels)

    def test_a_table_s_play_holds_no_marks(self) -> None:
        entries = workbench._play_entries(_context(lens="beta"))
        labels = {label for _, labels in _groups(entries) for label in labels}

        self.assertFalse(labels & MARKS)

    def test_a_table_s_play_holds_only_its_record(self) -> None:
        entries = workbench._play_entries(_context(lens="beta"))
        labels = {label for _, labels in _groups(entries) for label in labels}

        self.assertFalse(labels & {game_tables.DEFAULT_LABEL, t("word.hidden")})

    def test_a_table_s_play_shows_both_records(self) -> None:
        entries = workbench._play_entries(_context(lens="beta"))

        self.assertEqual(_headings(entries), [t("console.workbench.game_details"),
                                              t("console.workbench.table_details")])


if __name__ == "__main__":
    unittest.main()
