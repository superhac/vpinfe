"""Which client answers for a device, and what a remote one refuses to guess at.

The resolver is the whole seam: every caller asks `for_device` and then talks to what
it gets back, so a wrong answer here is one install asking the wrong machine.
"""

from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from common import device_client, http_client, lifecycle

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
        """An install that has not identified itself must not answer for a device on the
        grounds that it cannot tell them apart."""
        client = device_client.for_device(CAB, None)

        self.assertIsInstance(client, device_client.RemoteDevice)

    def test_a_url_keeps_one_slash(self) -> None:
        self.assertEqual(device_client.RemoteDevice("http://x:1/")._url("/update"),
                         "http://x:1/api/v1/update")


class RemoteRefusalTests(unittest.TestCase):
    """What cannot be learned by asking. Raising beats an empty list: "no screens" and
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

    def test_something_that_is_not_a_lifecycle_action_is_refused(self) -> None:
        """Refused here rather than dialled: an unknown pair would fail as a timeout on
        a machine that was never going to answer for it, instead of as a sentence."""
        with self.assertRaises(device_client.NotThisDeviceError):
            self.device.request("toaster", "toast")

    def test_every_pair_the_vocabulary_has_is_routed(self) -> None:
        """Quitting another machine's app had no route at all until the actions route
        existed, so the fleet surface could offer exactly one verb."""
        for scope, action in lifecycle.offered():
            with self.subTest(pair=(scope, action)):
                with patch.object(http_client, "post_json",
                                  return_value={"performed": True, "stopped": True}):
                    self.assertTrue(self.device.request(scope, action))

    def test_a_route_an_older_install_lacks_is_said_in_words(self) -> None:
        """It answers everything it knows about and 404s the rest, which is not a
        failure - and a person should not be shown an HTTP status and a URL for it."""
        import requests

        gone = requests.HTTPError("nope")
        gone.response = types.SimpleNamespace(status_code=404)
        with patch.object(http_client, "get_json", side_effect=gone):
            with self.assertRaises(device_client.TooOldError):
                self.device.actions()
            with self.assertRaises(device_client.TooOldError):
                self.device.logs()

    def test_a_real_failure_is_still_a_real_failure(self) -> None:
        """Only a missing route is translated. A machine that broke while answering has
        something worth reading in its own error."""
        import requests

        broke = requests.HTTPError("server fell over")
        broke.response = types.SimpleNamespace(status_code=500)
        with patch.object(http_client, "get_json", side_effect=broke):
            with self.assertRaises(requests.HTTPError):
                self.device.actions()

    def test_a_remote_device_never_asks_the_person_to_confirm(self) -> None:
        """The confirm belongs on the surface that asked, which is not that machine."""
        self.assertFalse(self.device.wants_confirmation(lifecycle.APP))


if __name__ == "__main__":
    unittest.main()
