from __future__ import annotations

import unittest

from common.host import about


class AboutTests(unittest.TestCase):
    def setUp(self) -> None:
        about.reset_for_tests()

    def tearDown(self) -> None:
        about.reset_for_tests()

    def test_every_fact_answers_something(self) -> None:
        """A blank sends the reader looking for the reason it is blank. A machine that
        cannot answer says so in words."""
        for group in about.details():
            self.assertTrue(group["heading"])
            self.assertTrue(group["facts"], group["heading"])
            for label, value in group["facts"]:
                self.assertTrue(label)
                self.assertTrue(str(value).strip(), label)

    def test_the_text_carries_what_the_screen_shows(self) -> None:
        """The point of the page is the copy button, so the two renderings hold the same
        answer - a field on screen and absent from the paste is the failure this
        catches."""
        text = about.as_text()

        for group in about.details():
            self.assertIn(group["heading"], text)
            for label, value in group["facts"]:
                self.assertIn(label, text)
                self.assertIn(str(value), text)

    def test_it_is_read_once(self) -> None:
        """Every field costs a subprocess or a config read, and none of them changes
        while VPinFE is running."""
        first = about.details()

        self.assertIs(about.details(), first)
        self.assertIsNot(about.details(refresh=True), first)


if __name__ == "__main__":
    unittest.main()
