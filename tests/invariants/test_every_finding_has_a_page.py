"""A requirement finding sends someone to a page, and that page is in their rail."""

from __future__ import annotations

import itertools
import unittest
from configparser import ConfigParser

from common import feature_checks, install_identity
from console import page


def _findings(on: list[str]) -> list[feature_checks.Unmet]:
    return feature_checks.unmet(ConfigParser(), features=on, launcher=None, locations=[])


class EveryFindingHasAPageTests(unittest.TestCase):
    def test_every_page_a_finding_names_is_in_that_device_s_rail(self) -> None:
        switchable = list(install_identity.FEATURES)
        for size in range(len(switchable) + 1):
            for chosen in itertools.combinations(switchable, size):
                on = [install_identity.CORE, *chosen]
                rail = {key for _parent, items in page.nav_for(on) for key, *_rest in items}
                with self.subTest(features=chosen):
                    self.assertEqual({one.where for one in _findings(on)} - rail, set())

    def test_every_page_a_finding_names_is_one_the_rail_marks(self) -> None:
        wheres = {one.where for one in _findings(list(install_identity.FEATURES))}

        self.assertLessEqual(wheres, set(feature_checks.WHERES))

    def test_a_frontend_only_device_is_among_the_cases_it_checks(self) -> None:
        """Nothing configured gives it a finding about its library folders."""
        wheres = {one.where for one in _findings([install_identity.FRONTEND])}

        self.assertIn(feature_checks.WHERE_LOCATIONS, wheres)


if __name__ == "__main__":
    unittest.main()
