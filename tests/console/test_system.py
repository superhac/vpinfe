"""System is always reachable, and everything beside it is not.

The bootstrap case is the one worth pinning: an install with nothing switched on still
has to be able to switch something on, and every other section in the rail is gone by
then.
"""

import unittest
from urllib.parse import parse_qs

from common import feature_checks, install_identity, path_checks
from console import deeplink, page, panel
from console import settings as settings_page


def _rail(features) -> list[str]:
    return [key for _parent, items in page.nav_for(features) for key, *_rest in items]


def _pages(features) -> list[str]:
    return [item[0] for _group, item in settings_page.system_pages(features)]


class NavTests(unittest.TestCase):
    """What the rail holds, for the features an install declares."""

    def test_every_section_is_there_when_every_feature_is(self) -> None:
        rail = _rail(install_identity.FEATURES)

        self.assertEqual(rail, [key for _parent, items in page.NAV_GROUPS
                                for key, *_rest in items])

    def test_system_survives_an_install_that_is_for_nothing(self) -> None:
        """The bootstrap case: features are switched on from in here."""
        self.assertIn("system", _rail([]))
        self.assertIn("system", _rail(["nonsense"]))

    def test_overview_has_to_be_asked_for(self) -> None:
        """It is a rollup of the other three rather than something an install does, so
        the default set and the fallback both leave it out."""
        self.assertNotIn(install_identity.OVERVIEW,
                         install_identity.DEFAULT_FEATURES)
        self.assertNotIn("overview", _rail(install_identity.DEFAULT_FEATURES))
        self.assertIn("overview", _rail(install_identity.FEATURES))

    def test_a_typo_does_not_switch_overview_on(self) -> None:
        """An unreadable setting falls back to the defaults, which is why a feature that
        has to be asked for must not be one of them."""
        import configparser

        config = configparser.ConfigParser()
        config.add_section("install")
        config.set("install", "features", "libary, frontnd")

        self.assertEqual(install_identity.features(config),
                         list(install_identity.DEFAULT_FEATURES))

    def test_no_library_takes_the_library_sections_with_it(self) -> None:
        rail = _rail([install_identity.FRONTEND])

        self.assertNotIn("games", rail)
        self.assertNotIn("collections", rail)
        self.assertIn("system", rail)

    def test_a_group_with_nothing_left_in_it_goes_too(self) -> None:
        """A disclosure with no entries under it is a control that does nothing."""
        parents = [parent for parent, _items in page.nav_for([install_identity.DEVICES])]

        self.assertNotIn(page.NAV_PARENT, parents)

    def test_devices_needs_the_feature_that_manages_them(self) -> None:
        self.assertNotIn("devices", _rail([install_identity.LIBRARY]))
        self.assertIn("devices", _rail([install_identity.DEVICES]))


class SystemIndexTests(unittest.TestCase):
    """What System offers, which is identity plus whatever the features can answer."""

    def test_identity_leads_and_is_not_feature_derived(self) -> None:
        for features in ([], [install_identity.LIBRARY], install_identity.FEATURES):
            with self.subTest(features=features):
                self.assertEqual(_pages(features)[0], settings_page.IDENTITY)

    def test_a_page_belonging_to_a_feature_goes_with_it(self) -> None:
        held = _pages([install_identity.DEVICES])

        self.assertNotIn("media_kinds", held)
        self.assertNotIn("displays", held)
        self.assertIn("mobile", held)

    def test_pages_belonging_to_no_feature_are_always_offered(self) -> None:
        held = _pages([install_identity.DEVICES])

        self.assertIn("general", held)
        self.assertIn("network", held)


class AddressTests(unittest.TestCase):
    """A page of System has to survive being written down and read back."""

    def test_the_page_is_named_in_the_address(self) -> None:
        address = parse_qs(deeplink.query({"view": "system",
                                           "settings_page": "network"}))

        self.assertEqual(address["settings"], ["network"])

    def test_a_page_name_is_noise_anywhere_else(self) -> None:
        address = parse_qs(deeplink.query({"view": "games",
                                           "settings_page": "network"}))

        self.assertNotIn("settings", address)


class TroubleTests(unittest.TestCase):
    """A configuration error has to lead from the nav down to the field that fixes it."""

    def _unmet(self, section: str, key: str, state: str = path_checks.MISSING):
        return feature_checks.Unmet(feature=install_identity.FRONTEND, section=section,
                                    key=key, state=state, reason="Nothing is there.")

    def test_a_requirement_is_keyed_by_the_page_that_holds_it(self) -> None:
        held = settings_page.pages_in_trouble([self._unmet("general", "vpx_bin_path")])

        self.assertEqual(list(held), ["general"])

    def test_a_setting_on_no_page_is_dropped_rather_than_counted(self) -> None:
        """A badge that leads nowhere is worse than no badge."""
        with self.assertLogs("vpinfe.console.settings", level="WARNING"):
            held = settings_page.pages_in_trouble([self._unmet("nowhere", "thing")])

        self.assertEqual(held, {})

    def test_the_disk_answers_until_a_feature_says_otherwise(self) -> None:
        checks = [{"section": "general", "key": "vpx_bin_path", "state": path_checks.OK,
                   "reason": ""}]
        marks = settings_page.field_marks([self._unmet("general", "vpx_bin_path")],
                                          checks)

        self.assertEqual(marks[("general", "vpx_bin_path")]["reason"],
                         "Nothing is there.")

    def test_blank_where_blank_is_not_allowed_draws_something(self) -> None:
        """An optional path left empty draws nothing, and this is not one of those."""
        marks = settings_page.field_marks(
            [self._unmet("general", "vpx_bin_path", path_checks.UNSET)], [])

        self.assertEqual(marks[("general", "vpx_bin_path")]["state"], panel.REQUIRED)
        self.assertIn(panel.REQUIRED, panel._VALUE_STATES)
