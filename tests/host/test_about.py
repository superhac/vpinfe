from __future__ import annotations

import unittest
from unittest import mock

from common import i18n
from common.host import about

# Names a person reads the same in every language.
NAMES = {"VPinFE", "Python"}


def _plain(said: str) -> bool:
    return any("a" <= letter.lower() <= "z" for letter in said)


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

    def test_each_library_folder_is_listed(self) -> None:
        from common.games.locations import KIND_GAME, Location
        from common.i18n import t

        held = [Location("l1", "/games/first"), Location("l2", "/games/one", kind=KIND_GAME)]
        with mock.patch("common.games.locations.configured", return_value=held):
            facts = next(group["facts"] for group in about.details(refresh=True)
                         if group["heading"] == t("about.heading.locations"))

        self.assertEqual([value for label, value in facts if label == t("about.fact.tables")],
                         ["/games/first", "/games/one"])

    def test_it_is_read_once(self) -> None:
        """Every field costs a subprocess or a config read, and none of them changes
        while VPinFE is running."""
        first = about.details()

        self.assertIs(about.details(), first)
        self.assertIsNot(about.details(refresh=True), first)

    def test_the_words_around_each_value_are_the_readers(self) -> None:
        """Under the pseudo-locale, a heading, label or fallback in plain letters was
        written in place rather than looked up."""
        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("qps")
        with mock.patch.object(about, "_browser_path", return_value=""), \
                mock.patch("common.log_setup.log_file", return_value=None), \
                mock.patch.object(about.platform, "machine", return_value=""), \
                mock.patch.object(about, "_install_context",
                                  return_value={"reason": "source_build"}):
            groups = about.details(refresh=True)

        words = [group["heading"] for group in groups]
        words += [label for group in groups for label, _ in group["facts"]]
        facts = {(group["heading"], label): value
                 for group in groups for label, value in group["facts"]}
        words += [value for (_, label), value in facts.items()
                  if label in (i18n.t("about.fact.architecture"), i18n.t("about.fact.build"),
                               i18n.t("about.fact.log_file"))]
        browser = [value for (heading, _), value in facts.items()
                   if heading == i18n.t("about.heading.browser")]

        self.assertEqual([said for said in words if said not in NAMES and _plain(said)], [])
        self.assertEqual(len(browser), 3)
        self.assertEqual([said for said in browser if _plain(said)], [])


if __name__ == "__main__":
    unittest.main()
