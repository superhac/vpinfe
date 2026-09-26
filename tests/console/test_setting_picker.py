"""Add a Setting's picker: each option with its area, and a heading over each run."""

from __future__ import annotations

import unittest

from nicegui import ui

from console import panel


def _picker() -> panel.SettingPicker:
    with ui.card():
        return panel.SettingPicker(
            {"a": "Alpha", "b": "Beta", "c": "Gamma"},
            areas={"a": "Sound", "b": "Sound", "c": "Displays"},
            headings={"a": "First Run", "c": "Second Run"}, label="Add")


def _listed(picker: panel.SettingPicker) -> list[tuple[str, str, str, bool]]:
    return [(str(one["label"]), str(one.get("area", "")), str(one.get("heading", "")),
             bool(one.get("disable")))
            for one in picker._props["options"]]


class SettingPickerTests(unittest.TestCase):

    def test_a_heading_is_its_own_option_above_the_run_it_starts(self):
        self.assertEqual(_listed(_picker()), [
            ("", "", "First Run", True), ("Alpha", "Sound", "", False),
            ("Beta", "Sound", "", False), ("", "", "Second Run", True),
            ("Gamma", "Displays", "", False)])

    def test_a_setting_s_option_carries_its_key_for_the_filter(self):
        self.assertEqual([one.get("also") for one in _picker()._props["options"]],
                         [None, "a", "b", None, "c"])

    def test_the_payload_survives_an_update(self):
        picker = _picker()
        before = _listed(picker)
        picker.update()

        self.assertEqual(_listed(picker), before)

    def test_the_option_slot_reads_the_fields_the_payload_carries(self):
        for field in ("props.opt.heading", "props.opt.area"):
            with self.subTest(field=field):
                self.assertIn(field, panel.SettingPicker.SLOT)


if __name__ == "__main__":
    unittest.main()
