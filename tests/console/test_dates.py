"""A day, written the way this install is set to write one."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from common import config_schema, i18n
from console import when

DAY = datetime(2026, 4, 29, 11, 26, 53, tzinfo=UTC)
CONSOLE = Path(__file__).resolve().parents[2] / "console"


def _set(**values: str):
    return patch("console.when._setting", lambda key, default: values.get(key, default))


class DateStyle(unittest.TestCase):
    def test_iso_writes_the_day_as_iso(self) -> None:
        with _set(dates="iso"):
            self.assertEqual("2026-04-29", when.day(DAY))

    def test_language_writes_it_as_the_catalog_does(self) -> None:
        with _set(dates="language"):
            self.assertEqual(i18n.date(DAY), when.day(DAY))

    def test_recent_says_how_long_ago_unless_that_is_turned_off(self) -> None:
        stamp = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        with _set(relative_dates="true"):
            self.assertEqual(i18n.t("date.days_ago", count=3), when.ago(stamp))
        with _set(relative_dates="false", dates="iso"):
            self.assertRegex(when.ago(stamp), r"^\d{4}-\d{2}-\d{2}$")

    def test_nothing_else_in_the_console_writes_a_day(self) -> None:
        found = sorted(path.name for path in CONSOLE.glob("*.py")
                       if path.name != "when.py" and "i18n.date(" in path.read_text())
        self.assertEqual([], found)


class ChoiceLabels(unittest.TestCase):
    def _labels(self, section: str, key: str) -> dict[str, str]:
        option = config_schema.option(section, key)
        assert option is not None
        return option.choice_labels

    def test_a_choice_the_catalog_names_carries_its_name(self) -> None:
        self.assertEqual({"language": "Language", "iso": "ISO"},
                         self._labels("console", "dates"))

    def test_a_choice_it_does_not_name_carries_none(self) -> None:
        self.assertEqual({}, self._labels("vpsdb", "download"))


if __name__ == "__main__":
    unittest.main()
