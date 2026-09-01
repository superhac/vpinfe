"""What a table's script was seen to use, and how the grid says it.

The three states are the point. Null means nobody has read this table's script, and a
reader that treats it as false gives an unparsed table a clean bill of health - which is
the only way this vocabulary can be wrong in a way nobody notices.
"""

import unittest

from hubui import features, games


class StateTests(unittest.TestCase):
    def test_null_is_its_own_answer(self) -> None:
        self.assertEqual(features.key_of(None), features.UNKNOWN)

    def test_true_and_false_are_the_other_two(self) -> None:
        self.assertEqual(features.key_of(True), features.IN_SCRIPT)
        self.assertEqual(features.key_of(False), features.UNUSED)

    def _drawn(self, key: str) -> str:
        state = features.state_for(key)
        return state.glyph or state.mark

    def test_not_used_draws_nothing(self) -> None:
        """The state most cells are in draws nothing at all, or the matrix is solid ink
        and the two states worth seeing are lost in it."""
        self.assertEqual(self._drawn(features.UNUSED), "")
        self.assertTrue(self._drawn(features.IN_SCRIPT))
        self.assertTrue(self._drawn(features.UNKNOWN))

    def test_both_drawn_states_are_characters(self) -> None:
        """A tick for the plain yes, the same as the asset and media columns beside
        these, and a question mark for the answer nobody has - which says itself, where
        a shape needs a legend to say it."""
        self.assertEqual(features.state_for(features.IN_SCRIPT).glyph, "\u2713")
        self.assertEqual(features.state_for(features.UNKNOWN).glyph, "?")

    def test_no_feature_state_borrows_a_media_tier_shape(self) -> None:
        """A dashed circle already means Missing in `media_ownership`, and a table
        nobody has read is not a missing one. Shapes are shared across vocabularies on
        purpose, so the one that would be wrong has to be kept out deliberately."""
        for key in features.STATES:
            with self.subTest(state=key):
                self.assertEqual(features.state_for(key).mark, "")

    def test_present_is_green_and_unread_is_quiet(self) -> None:
        """`docs/conventions.md`: green is present, and accent is the current value and
        nothing else - so a tick on every true cell of a matrix cannot be accent. An
        unread table is not a fault and must not be coloured as one."""
        self.assertEqual(features.state_for(features.IN_SCRIPT).glyph_class, "hub-tick")
        self.assertEqual(features.state_for(features.UNKNOWN).glyph_class,
                         "hub-unknown")

    def test_the_vocabulary_keeps_all_three(self) -> None:
        """The legend is a narrower list - only what is drawn - but a caller mapping a
        value has to be able to reach every state."""
        self.assertEqual(set(features.STATES),
                         {features.IN_SCRIPT, features.UNUSED, features.UNKNOWN})

    def test_pinmame_is_not_a_feature_here(self) -> None:
        """The ROM answers it, in more detail than a tick could."""
        self.assertNotIn("pinmame", features.LABELS)


class ViewTests(unittest.TestCase):
    def test_a_row_carries_one_field_per_feature(self) -> None:
        """The payload nests them; a grid column reads a field."""
        rows = games.table_rows([{"id": "t1", "features": {"ssf": True, "lut": None}}])

        self.assertIs(rows[0]["feature_ssf"], True)
        self.assertIsNone(rows[0]["feature_lut"])

    def test_a_table_nobody_parsed_stays_unknown(self) -> None:
        """Not False. Defaulting here would turn "nobody looked" into "does not use it"
        for every feature of every unparsed table."""
        rows = games.table_rows([{"id": "t1"}])

        self.assertIsNone(rows[0]["feature_ssf"])

    def test_the_features_view_shows_features_and_what_names_the_row(self) -> None:
        columns = games.TABLE_VIEWS["Features"]

        self.assertEqual([c for c in columns if not c.startswith("feature_")],
                         ["game", "version", "author"])
        self.assertEqual({c.removeprefix("feature_") for c in columns
                          if c.startswith("feature_")},
                         set(features.LABELS))


if __name__ == "__main__":
    unittest.main()
