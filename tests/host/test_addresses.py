"""The addresses this machine offers somebody standing somewhere else."""

from __future__ import annotations

import unittest
from unittest import mock

from common.host import addresses


class UsableTests(unittest.TestCase):
    def test_an_address_something_else_can_dial(self) -> None:
        self.assertTrue(addresses.usable_ipv4("192.168.1.20"))
        self.assertTrue(addresses.usable_ipv4("10.0.0.4"))

    def test_loopback_is_not_an_address_for_anybody_else(self) -> None:
        self.assertFalse(addresses.usable_ipv4("127.0.0.1"))

    def test_a_failed_lease_is_not_an_answer(self) -> None:
        """169.254 means the machine never got an address. Offering it reads as one."""
        self.assertFalse(addresses.usable_ipv4("169.254.13.9"))

    def test_nothing_and_nonsense_are_not_addresses(self) -> None:
        self.assertFalse(addresses.usable_ipv4(""))
        self.assertFalse(addresses.usable_ipv4("cbmacbookmax"))
        self.assertFalse(addresses.usable_ipv4("::1"))


class OrderTests(unittest.TestCase):
    """Which one goes in front of a person, and which one never does."""

    def test_the_routed_address_leads(self) -> None:
        with mock.patch.object(addresses, "primary_ipv4", return_value="192.168.1.20"), \
                mock.patch.object(addresses, "_hostname", return_value="cab"), \
                mock.patch.object(addresses, "_resolved", return_value=["192.168.1.20"]):
            self.assertEqual(addresses.hosts(), ["192.168.1.20", "cab", "localhost"])

    def test_loopback_is_last_and_never_offered_first(self) -> None:
        """It is the one address certain to be listening and certain not to work from
        anywhere else, so a list that led with it would lead with the wrong answer."""
        with mock.patch.object(addresses, "hosts",
                               return_value=["192.168.1.20", "localhost"]):
            self.assertEqual(addresses.best(8001, "/remote"),
                             "http://192.168.1.20:8001/remote")

    def test_loopback_is_still_offered_when_it_is_all_there_is(self) -> None:
        """A machine with no network still has a Console on it, and an address that
        works there beats no address at all."""
        with mock.patch.object(addresses, "hosts", return_value=["localhost"]):
            self.assertEqual(addresses.best(8001, "/remote"),
                             "http://localhost:8001/remote")

    def test_nothing_to_offer_says_nothing(self) -> None:
        with mock.patch.object(addresses, "hosts", return_value=[]):
            self.assertEqual(addresses.best(8001), "")

    def test_a_name_that_does_not_resolve_does_not_take_the_list_with_it(self) -> None:
        """A machine whose own name does not resolve is common - it is what a fresh
        container does - and the routed address is still worth having."""
        with mock.patch.object(addresses, "primary_ipv4", return_value="10.0.0.4"), \
                mock.patch.object(addresses, "_hostname", return_value="cab"), \
                mock.patch.object(addresses, "_resolved", return_value=[]):
            self.assertEqual(addresses.hosts(), ["10.0.0.4", "cab", "localhost"])

    def test_the_same_address_twice_is_listed_once(self) -> None:
        """The routed address is usually also what the hostname resolves to."""
        with mock.patch.object(addresses, "primary_ipv4", return_value="10.0.0.4"), \
                mock.patch.object(addresses, "_hostname", return_value="cab"), \
                mock.patch.object(addresses, "_resolved", return_value=["10.0.0.4"]):
            self.assertEqual(addresses.hosts().count("10.0.0.4"), 1)
