"""Which client answers for a device, and what a remote one refuses to guess at.

The resolver is the whole seam: every caller asks `for_device` and then talks to what
it gets back, so a wrong answer here is a hub asking the wrong machine.
"""

from __future__ import annotations

import unittest

from common import device_client, lifecycle

LOCAL = "Aaaa111111"
CAB = {"device_id": "Bbbb222222", "address": "192.168.1.50", "port": 8001}


class ResolverTests(unittest.TestCase):
    def test_this_install_is_the_local_device(self) -> None:
        client = device_client.for_device({"device_id": LOCAL}, LOCAL)

        self.assertIsInstance(client, device_client.LocalDevice)

    def test_another_install_with_an_address_is_reached_over_it(self) -> None:
        client = device_client.for_device(CAB, LOCAL)

        self.assertIsInstance(client, device_client.RemoteDevice)
        self.assertEqual(client.base_url, "http://192.168.1.50:8001")

    def test_a_device_that_never_said_its_port_cannot_be_dialled(self) -> None:
        """Every entry written before installs announced one. Half an address is not an
        address, and a client built on it would time out rather than say so."""
        client = device_client.for_device({**CAB, "port": 0}, LOCAL)

        self.assertIsNone(client)

    def test_a_device_with_no_address_cannot_be_dialled(self) -> None:
        client = device_client.for_device({**CAB, "address": ""}, LOCAL)

        self.assertIsNone(client)

    def test_without_knowing_which_install_is_ours_nothing_is_assumed_local(self) -> None:
        """A hub that has not identified itself must not answer for a device on the
        grounds that it cannot tell them apart."""
        client = device_client.for_device(CAB, None)

        self.assertIsInstance(client, device_client.RemoteDevice)

    def test_a_url_keeps_one_slash(self) -> None:
        self.assertEqual(device_client.RemoteDevice("http://x:1/")._url("/update"),
                         "http://x:1/api/v1/update")


class RemoteRefusalTests(unittest.TestCase):
    """What a hub cannot learn by asking. Raising beats an empty list: "no screens" and
    "not a thing this device can be asked" are different facts."""

    def setUp(self) -> None:
        self.device = device_client.RemoteDevice("http://192.168.1.50:8001")

    def test_screens_are_not_something_a_hub_can_enumerate(self) -> None:
        with self.assertRaises(device_client.NotThisDeviceError):
            self.device.displays()

    def test_the_browser_is_not_something_a_hub_can_read(self) -> None:
        with self.assertRaises(device_client.NotThisDeviceError):
            self.device.browser_path()

    def test_input_bindings_are_not_something_a_hub_can_read(self) -> None:
        with self.assertRaises(device_client.NotThisDeviceError):
            self.device.bindings(None)

    def test_a_lifecycle_action_with_no_route_is_refused(self) -> None:
        """Stopping a table has one; quitting another machine's app does not, and
        pretending otherwise would fail as a timeout instead of as a sentence."""
        with self.assertRaises(device_client.NotThisDeviceError):
            self.device.request(lifecycle.APP, lifecycle.STOP)

    def test_a_remote_device_never_asks_the_person_to_confirm(self) -> None:
        """The confirm belongs on the surface that asked, which is not that machine."""
        self.assertFalse(self.device.wants_confirmation(lifecycle.APP))


if __name__ == "__main__":
    unittest.main()
