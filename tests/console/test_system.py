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
        """The bootstrap case: features are switched on from in here, so what System
        holds is the only rail an install for nothing has."""
        for features in (["nonsense"], [install_identity.CORE]):
            with self.subTest(features=features):
                self.assertEqual(_rail(features), ["extensions", "settings",
                                                   "metrics", "logs", "about"])

    def test_a_frontend_only_install_opens_on_what_it_has(self) -> None:
        """Launchers, because that is the first real place such an install holds. It has
        no library, so there are no Games to open on, and Extensions is never a front
        door."""
        self.assertEqual(page.landing_for(_rail([install_identity.FRONTEND])),
                         "launchers")

    def test_extensions_is_not_a_front_door(self) -> None:
        """It leads the rail of an install with no library, and it is not defined enough
        yet to be the first thing anybody sees. Settings is the floor."""
        self.assertEqual(page.landing_for(_rail([install_identity.CORE])), "settings")
        self.assertEqual(page.landing_for(_rail(install_identity.DEFAULT_FEATURES)),
                         "games")

    def test_reporting_nothing_is_not_the_same_as_being_for_nothing(self) -> None:
        """An install that is for nothing still reports `core`, so an empty list is a
        machine that has not answered - and the rail assumes the ordinary install
        rather than hiding sections it may well have."""
        self.assertIn("games", _rail([]))
        self.assertNotIn("games", _rail([install_identity.CORE]))

    def test_system_is_a_container(self) -> None:
        """It collapsed into its first child while `build_system` drew the index
        directly. Records are places; configuration is a setting."""
        under_system = [items for parent, items in page.nav_for(install_identity.FEATURES)
                        if parent == page.NAV_SYSTEM]

        self.assertEqual([key for key, *_rest in under_system[0]],
                         ["settings", "metrics", "logs", "about"])

    def test_what_the_frontend_owns_has_a_container_of_its_own(self) -> None:
        """The rule Library and this one make together: a feature with more than one
        subject gets a container. Launchers sat under System and never fitted - System's
        three are configuration and records, and a launcher is neither."""
        under_frontend = [items for parent, items
                          in page.nav_for(install_identity.FEATURES)
                          if parent == page.NAV_FRONTEND]

        self.assertEqual([key for key, *_rest in under_frontend[0]],
                         ["launchers", "themes"])

    def test_launchers_goes_with_the_feature_that_launches(self) -> None:
        """An install that curates a library and never starts a game has nothing to run
        a table with and no reason to be offered one - and with nothing left under it,
        the container goes too."""
        self.assertNotIn("launchers", _rail([install_identity.LIBRARY]))
        self.assertNotIn(page.NAV_FRONTEND,
                         [parent for parent, _items
                          in page.nav_for([install_identity.LIBRARY])])
        self.assertIn("launchers", _rail([install_identity.FRONTEND]))

    def test_overview_has_to_be_asked_for(self) -> None:
        """It is a rollup of the other three rather than something an install does, so
        the default set and the fallback both leave it out."""
        self.assertNotIn(install_identity.OVERVIEW,
                         install_identity.DEFAULT_FEATURES)
        self.assertNotIn("overview", _rail(install_identity.DEFAULT_FEATURES))
        self.assertIn("overview", _rail(install_identity.FEATURES))

    def test_core_is_never_one_of_the_switchable_features(self) -> None:
        """Synthesized on every read and never stored, so it is not in the set a person
        chooses from and cannot be edited out of a list."""
        self.assertNotIn(install_identity.CORE, install_identity.FEATURES)
        self.assertNotIn(install_identity.CORE, install_identity.DEFAULT_FEATURES)

    def test_a_typo_does_not_switch_overview_on(self) -> None:
        """An unreadable setting falls back to the defaults, which is why a feature that
        has to be asked for must not be one of them."""
        import configparser

        config = configparser.ConfigParser()
        config.add_section("install")
        config.set("install", "features", "libary, frontnd")

        self.assertNotIn(install_identity.OVERVIEW,
                         install_identity.features(config))

    def test_no_library_takes_the_library_sections_with_it(self) -> None:
        rail = _rail([install_identity.FRONTEND])

        self.assertNotIn("games", rail)
        self.assertNotIn("collections", rail)
        self.assertIn("settings", rail)

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

    def test_the_install_wide_pages_are_always_offered(self) -> None:
        """They name `core`, which is how a page says it is here on every install
        rather than leaving that to an empty string a reader has to know about."""
        held = _pages([install_identity.DEVICES])

        self.assertIn("general", held)
        self.assertIn("network", held)
        self.assertIn("logging", held)

    def test_every_page_names_a_feature(self) -> None:
        """`core` where it belongs to the install as a whole. An unnamed one would be
        filtered out rather than always offered, which is the failure worth pinning."""
        for group, pages in settings_page.DEVICE_INDEX:
            for page_item in pages:
                with self.subTest(group=group, page=page_item[0]):
                    self.assertIn(page_item[4],
                                  {install_identity.CORE, *install_identity.FEATURES})

    def test_identity_survives_an_install_that_is_for_nothing(self) -> None:
        """The whole point of `core`: the screen that switches a feature back on is the
        one screen an install with everything off still has."""
        self.assertEqual(_pages([install_identity.CORE]),
                         [settings_page.IDENTITY, "general", "network", "logging",
                          "vpinplay"])


class AddressTests(unittest.TestCase):
    """A page of System has to survive being written down and read back."""

    def test_the_page_is_named_in_the_address(self) -> None:
        address = parse_qs(deeplink.query({"view": "settings",
                                           "settings_page": "network"}))

        self.assertEqual(address["page"], ["network"])

    def test_a_page_name_is_noise_anywhere_else(self) -> None:
        address = parse_qs(deeplink.query({"view": "games",
                                           "settings_page": "network"}))

        self.assertNotIn("page", address)


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


class TheInstallYouAreSittingAtReportsItsOwnUpdate(unittest.TestCase):
    """A caller asks every device whether a newer build is published, and gets the local
    client back for the one it is running in.

    That client does not offer the call - it is this process, and asking it to reach the
    network for a version it already knows would be the install phoning itself. So the
    call raised, the caller logged that a device could not be asked, and every machine on
    the network reported correctly except the one in front of you. Silent, because a
    device that cannot be reached is an ordinary thing.
    """

    def test_the_local_device_is_asked_through_this_install_s_own_api(self) -> None:
        from console import devices as devices_page

        ask = devices_page.update_checker(True, object())

        self.assertIsNotNone(ask)
        self.assertEqual(getattr(ask, "__name__", ""), "update_check")

    def test_another_machine_is_still_asked_directly(self) -> None:
        from console import devices as devices_page

        class Remote:
            def update_check(self):
                return {"update_available": True}

        client = Remote()
        ask = devices_page.update_checker(False, client)

        self.assertEqual(ask(), {"update_available": True})

    def test_a_device_that_cannot_be_asked_answers_with_nothing(self) -> None:
        """A phone speaks a different protocol entirely and has no such call."""
        from console import devices as devices_page

        self.assertIsNone(devices_page.update_checker(False, object()))
