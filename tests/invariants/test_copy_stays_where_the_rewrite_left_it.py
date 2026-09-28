"""Ceilings over every owner's catalog."""

from __future__ import annotations

import unittest

from tests.support.catalogs import served

LABEL = 40
PROSE = 160
OVER = 80

OVER_EIGHTY = 122

TOO_LONG_TODAY = frozenset({
    "console.media.why_file_not_one.help",
    "console.assets.files_left_behind_table.help",
    "console.assets.why_file_not_one.help",
})

RETIRED = ("manager ui", "managerui", "hubui")


def _strings() -> dict[str, str]:
    """Every word a person reads, with a plural's forms under their own keys."""
    said: dict[str, str] = {}
    for key, value in served().items():
        if isinstance(value, str):
            said[key] = value
        elif isinstance(value, dict):
            for form, text in value.items():
                said[f"{key}[{form}]"] = str(text)
    return said


class Ceilings(unittest.TestCase):
    def setUp(self) -> None:
        self.said = _strings()

    def test_a_label_is_short_enough_to_sit_beside_its_control(self) -> None:
        over = {key: len(text) for key, text in self.said.items()
                if key.endswith(".label") and len(text) > LABEL}

        self.assertEqual(over, {})

    def test_a_description_or_help_string_stops_at_a_paragraph(self) -> None:
        over = {key: len(text) for key, text in self.said.items()
                if key.rsplit(".", 1)[-1] in ("description", "help")
                and len(text) > PROSE and key not in TOO_LONG_TODAY}

        self.assertEqual(over, {})

    def test_the_list_of_long_ones_holds_nothing_already_fixed(self) -> None:
        stale = sorted(key for key in TOO_LONG_TODAY
                       if len(self.said.get(key, "")) <= PROSE)

        self.assertEqual(stale, [])

    def test_the_count_over_eighty_only_comes_down(self) -> None:
        long = [key for key, text in self.said.items() if len(text) > OVER]

        self.assertLessEqual(len(long), OVER_EIGHTY,
                             f"{len(long)} over {OVER}; lower the ceiling as it falls")


class RetiredNames(unittest.TestCase):
    def test_nothing_on_screen_names_a_surface_that_is_going_away(self) -> None:
        found = sorted(key for key, text in _strings().items()
                       if any(word in text.lower() for word in RETIRED))

        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
