"""A tag chip, drawn by the grid and by a panel, the same way."""

from __future__ import annotations

import json
import unittest

from common.games.tag_registry import COLORS
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


if __name__ == "__main__":
    unittest.main()
