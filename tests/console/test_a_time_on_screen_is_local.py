"""A time drawn in the Console is the reader's, and the cell behind it still sorts."""

from __future__ import annotations

import ast
import pathlib
import unittest
from datetime import UTC, datetime, timedelta

from console import when

CONSOLE = pathlib.Path(__file__).resolve().parent.parent.parent / "console"


class LocalTime(unittest.TestCase):
    def test_a_utc_stamp_becomes_local(self) -> None:
        stamp = "2026-09-22T12:46:11Z"
        expected = (datetime.fromisoformat("2026-09-22T12:46:11+00:00")
                    .astimezone().strftime(when.SHOWN))
        self.assertEqual(expected, when.local(stamp))

    def test_an_offset_is_read_as_well_as_a_z(self) -> None:
        self.assertEqual(when.local("2026-09-22T12:46:11Z"),
                         when.local("2026-09-22T12:46:11+00:00"))

    def test_nothing_in_becomes_nothing_out(self) -> None:
        self.assertEqual("", when.local(""))

    def test_an_unreadable_stamp_comes_back_whole(self) -> None:
        self.assertEqual("not a time", when.local("not a time"))

    def test_the_zone_is_resolved_not_read_once(self) -> None:
        winter = when.local("2026-01-15T12:00:00Z")
        summer = when.local("2026-07-15T12:00:00Z")
        if datetime(2026, 1, 15, tzinfo=UTC).astimezone().utcoffset() == \
                datetime(2026, 7, 15, tzinfo=UTC).astimezone().utcoffset():
            self.skipTest("this machine's zone has no summer time")
        self.assertNotEqual(winter[11:], summer[11:])


class TheCellKeepsTheValue(unittest.TestCase):
    def test_devices_puts_a_sortable_stamp_in_the_row(self) -> None:
        source = (CONSOLE / "devices.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Dict) and any(
                    isinstance(k, ast.Constant) and k.value == "last_seen"
                    for k in node.keys if k is not None)):
                continue
            value = next(v for k, v in zip(node.keys, node.values, strict=False)
                         if isinstance(k, ast.Constant) and k.value == "last_seen")
            # A bare `_when(...)` is a Name, `when.local(...)` an Attribute.
            called = {getattr(sub.func, "attr", "") or getattr(sub.func, "id", "")
                      for sub in ast.walk(value) if isinstance(sub, ast.Call)}
            self.assertEqual(
                set(), called & {"local", "_when"},
                "last_seen is drawn into the row rather than the column")

    def test_the_column_draws_it(self) -> None:
        source = (CONSOLE / "devices.py").read_text(encoding="utf-8")
        self.assertIn("when.CELL", source, "the Last Seen column has no formatter")

    def test_iso_stamps_sort_chronologically_as_text(self) -> None:
        base = datetime(2026, 9, 22, 12, 46, 11, tzinfo=UTC)
        stamps = [(base + timedelta(seconds=n)).isoformat(timespec="seconds")
                  .replace("+00:00", "Z")
                  for n in (0, 59, 60, 3600, 86400, 86400 * 400)]
        self.assertEqual(stamps, sorted(stamps))


if __name__ == "__main__":
    unittest.main()
