"""The Themes grid: what each row says, and what the panel leaves out."""

from __future__ import annotations

import unittest

from console import themes


def _theme(**more) -> dict:
    return {"key": "k", "name": "Name", "author": "someone", "version": "1.0",
            "installed_version": "", "installed": False, "active": False,
            "update_available": False, "type": "", "preview": "", **more}


class ARow(unittest.TestCase):
    def test_each_state_is_one_of_four(self) -> None:
        self.assertEqual(
            [themes.ACTIVE, themes.UPDATE, themes.INSTALLED, themes.AVAILABLE],
            [themes.status(_theme(installed=True, active=True)),
             themes.status(_theme(installed=True, update_available=True)),
             themes.status(_theme(installed=True)),
             themes.status(_theme())])

    def test_made_for_says_only_what_the_manifest_declared(self) -> None:
        self.assertEqual(["cab", ""], [row["made_for"] for row in themes.rows(
            [_theme(key="a", type="cab"), _theme(key="b", type="")])])

    def test_an_update_reads_as_the_version_you_have_and_the_one_on_offer(self) -> None:
        said = themes.version_said(_theme(installed=True, update_available=True,
                                          installed_version="1.7", version="1.9"))
        self.assertIn("1.7", said)
        self.assertIn("1.9", said)


class TheChangelog(unittest.TestCase):
    def test_a_template_placeholder_is_not_news(self) -> None:
        self.assertEqual("", themes.changes_worth_showing(
            _theme(change_log="What changed in this version?")))

    def test_it_is_shown_before_installing_and_with_an_update_waiting(self) -> None:
        self.assertEqual("Faster", themes.changes_worth_showing(_theme(change_log="Faster")))
        self.assertEqual("Faster", themes.changes_worth_showing(
            _theme(change_log="Faster", installed=True, update_available=True)))

    def test_it_is_old_news_on_the_copy_you_run(self) -> None:
        self.assertEqual("", themes.changes_worth_showing(
            _theme(change_log="Faster", installed=True)))


if __name__ == "__main__":
    unittest.main()
