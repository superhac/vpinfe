"""A tag chip, drawn by the grid and by a panel, the same way."""

from __future__ import annotations

import json
import unittest

from nicegui import ui

from common.games.tag_registry import COLORS, derived_color
from console import renderers, tag_chips, theme


class OneChipTwoDrawings(unittest.TestCase):
    def test_the_grid_draws_the_classes_the_panel_draws(self) -> None:
        for token in (tag_chips.BOX, tag_chips.CHIP, tag_chips.DOT, tag_chips.LOOKS):
            with self.subTest(token=token):
                self.assertIn(token, tag_chips.RENDERER)
        self.assertIn(json.dumps(list(COLORS)), tag_chips.RENDERER)

    def test_a_color_nobody_knows_is_grey(self) -> None:
        self.assertEqual(f"{tag_chips.DOT} {tag_chips.DOT}--gray",
                         tag_chips.dot_class("chartreuse"))

    def test_every_color_has_a_dot_to_wear(self) -> None:
        css = theme.base_css()
        for color in COLORS:
            with self.subTest(color=color):
                self.assertIn(f".{tag_chips.DOT}--{color} {{ background: var(--tag-{color}); }}",
                              css)

    def test_a_column_can_be_drawn_as_tags(self) -> None:
        self.assertIs(renderers.REGISTRY["tags"].js, tag_chips.RENDERER)


LOOKS = {"night": {"color": "purple", "description": "Plays well in the dark"},
         "shortlist": {"color": "amber", "description": ""}}


def _picker(value: list[str], *, adds: bool = True) -> tag_chips.Picker:
    with ui.card():
        return tag_chips.Picker(["night", "shortlist"], value=value, looks=LOOKS, adds=adds)


def _dots(items: list[dict]) -> dict[str, str]:
    return {str(one["label"]): str(one["dot"]) for one in items}


class ThePickerWearsTheColors(unittest.TestCase):
    def test_a_chosen_tag_carries_its_dot_and_its_description(self) -> None:
        chosen = _picker(["night"])._props["model-value"]
        self.assertEqual(_dots(chosen), {"night": tag_chips.dot_class("purple")})
        self.assertEqual(chosen[0]["help"], "Plays well in the dark")

    def test_every_option_carries_its_dot(self) -> None:
        self.assertEqual(_dots(_picker([])._props["options"]),
                         {"night": tag_chips.dot_class("purple"),
                          "shortlist": tag_chips.dot_class("amber")})

    def test_a_tag_typed_in_wears_the_color_the_library_will_give_it(self) -> None:
        picker = _picker([])
        picker.set_options(["night", "shortlist", "brand new"], value=["brand new"])
        self.assertEqual(_dots(picker._props["model-value"]),
                         {"brand new": tag_chips.dot_class(derived_color("brand new"))})

    def test_the_dots_survive_an_update(self) -> None:
        picker = _picker(["shortlist"])
        picker.update()
        self.assertEqual(_dots(picker._props["model-value"]),
                         {"shortlist": tag_chips.dot_class("amber")})

    def test_only_a_picker_that_adds_takes_new_words(self) -> None:
        self.assertEqual(_picker([])._props.get("new-value-mode"), "add-unique")
        self.assertNotIn("new-value-mode", _picker([], adds=False)._props)

    def test_the_slots_read_the_fields_the_payload_carries(self) -> None:
        for slot in (tag_chips.Picker.SELECTED, tag_chips.Picker.OPTION):
            with self.subTest(slot=slot[:40]):
                self.assertIn("props.opt.dot", slot)
                self.assertIn("props.opt.help", slot)
        self.assertIn(f'class="{tag_chips.CHIP}"', tag_chips.Picker.SELECTED)


if __name__ == "__main__":
    unittest.main()
