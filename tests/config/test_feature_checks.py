"""A feature is enabled and its configuration does not let it work."""

from __future__ import annotations

import configparser
import os
import unittest
from tempfile import TemporaryDirectory

from common import feature_checks, install_identity, path_checks


class RequirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.games = os.path.join(self.tmp.name, "games")
        os.mkdir(self.games)
        self.launcher = os.path.join(self.tmp.name, "VPinballX")
        with open(self.launcher, "w", encoding="utf-8"):
            pass
        os.chmod(self.launcher, 0o755)

    def _config(self, **general: str):
        parser = configparser.ConfigParser()
        parser.add_section("general")
        for key, value in general.items():
            parser.set("general", key, value)
        return parser

    def _unmet(self, config, features):
        return [(u.feature, u.key, u.state)
                for u in feature_checks.unmet(config, features)]

    def test_a_fully_configured_install_reports_nothing(self) -> None:
        config = self._config(game_root_dir=self.games, vpx_bin_path=self.launcher)

        self.assertEqual(feature_checks.unmet(config, install_identity.FEATURES), [])

    def test_the_frontend_needs_a_launcher(self) -> None:
        config = self._config(game_root_dir=self.games)

        self.assertEqual(self._unmet(config, ["frontend"]),
                         [("frontend", "vpx_bin_path", path_checks.UNSET)])

    def test_the_library_does_not_need_a_launcher(self) -> None:
        """It curates games; it never starts one. Requiring it would mark a catalog
        install broken for lacking something it has no use for."""
        config = self._config(game_root_dir=self.games)

        self.assertEqual(feature_checks.unmet(config, ["library"]), [])

    def test_a_setting_two_features_need_is_reported_against_each(self) -> None:
        """Somebody is looking at one feature's page and needs to know that page is
        affected - not that some other feature is also unhappy about the same setting."""
        config = self._config(vpx_bin_path=self.launcher)

        self.assertEqual(self._unmet(config, ["library", "frontend"]),
                         [("library", "game_root_dir", path_checks.UNSET),
                          ("frontend", "game_root_dir", path_checks.UNSET)])

    def test_a_path_that_is_set_and_wrong_is_not_the_same_as_unset(self) -> None:
        """The reason differs, and so does the fix: one is 'fill this in', the other is
        'what you filled in is not there'."""
        config = self._config(game_root_dir=self.games, vpx_bin_path="/nope/vpx")

        self.assertEqual(self._unmet(config, ["frontend"]),
                         [("frontend", "vpx_bin_path", path_checks.MISSING)])

    def test_managing_devices_requires_nothing_of_its_own(self) -> None:
        """It reaches other installs over the network. An address that does not answer is
        that device's row to report, not a setting on this one."""
        self.assertEqual(feature_checks.unmet(self._config(), ["devices"]), [])

    def test_a_feature_that_is_off_is_not_checked(self) -> None:
        """Only what the operator asked for. An install that does not launch games is not
        misconfigured for having no launcher."""
        self.assertEqual(feature_checks.unmet(self._config(), ["devices"]), [])
        self.assertNotEqual(feature_checks.unmet(self._config(), ["frontend"]), [])

    def test_every_reason_says_what_is_wrong(self) -> None:
        """It is shown to the person who has to fix it, so 'no' on its own is not enough."""
        config = self._config()

        for item in feature_checks.unmet(config, install_identity.FEATURES):
            with self.subTest(setting=item.key):
                self.assertTrue(item.reason.strip(), f"{item.key} gave no reason")

    def test_features_in_trouble_names_them_once(self) -> None:
        config = self._config()

        self.assertEqual(feature_checks.features_in_trouble(config,
                                                            ["library", "frontend"]),
                         {"library", "frontend"})


if __name__ == "__main__":
    unittest.main()
