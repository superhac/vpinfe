"""One name and one direction per fact, which is the rule three surfaces broke.

`Hidden` read one way in the grid and the opposite in the panel, and `Missing` did the
same - so the words are asserted here rather than left to each surface to spell.
"""

import unittest

from hubui import game_tables


class WordTests(unittest.TestCase):
    def test_the_notable_state_is_the_first_of_the_pair(self) -> None:
        """The direction every one of these reads: true is the state worth spotting."""
        self.assertEqual(game_tables.word_for(game_tables.HIDDEN_WORDS, True), "Hidden")
        self.assertEqual(game_tables.word_for(game_tables.FILE_WORDS, True), "Missing")

    def test_a_file_that_is_there_reads_present(self) -> None:
        """The inversion this helper exists to stop: a `pair[not present]` at the call
        site put "Missing" on a file that was on disk."""
        self.assertEqual(game_tables.word_for(game_tables.FILE_WORDS, False), "Present")
        self.assertEqual(game_tables.word_for(game_tables.HIDDEN_WORDS, False),
                         "Offered")

    def test_a_default_says_what_it_is_not_who_set_it(self) -> None:
        """"User" named the actor; the cell holds a state, and the two states have to
        differ in kind - a decision, or the absence of one."""
        chosen, chosen_why = game_tables.default_state(game_tables.CHOSEN)
        automatic, automatic_why = game_tables.default_state(game_tables.DERIVED)

        self.assertEqual((chosen, automatic), ("Chosen", "Automatic"))
        self.assertNotEqual(chosen_why, automatic_why)

    def test_the_reason_is_the_consequence_not_the_provenance(self) -> None:
        """What a reader does with it: a choice stays put, a derived pick can move."""
        self.assertIn("Stays", game_tables.default_state(game_tables.CHOSEN)[1])
        self.assertIn("move", game_tables.default_state(game_tables.DERIVED)[1])

    def test_a_table_that_is_not_the_default_has_no_word(self) -> None:
        self.assertIsNone(game_tables.default_state(""))


if __name__ == "__main__":
    unittest.main()
