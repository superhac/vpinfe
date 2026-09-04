"""What an install hears on the network, and what it makes of it.

The network itself is not exercised here - two processes on one machine finding each
other is a thing to watch happen, not to assert in a unit test. What is asserted is the
reading: an announcement carries identity, and anything on a LAN can send one, so a
record that does not identify itself is not a peer.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpapi
from common import device_registry as registry_module
from common import discovery, install_identity
from httpapi import instance
from tests.support.library import TempTree

try:
    from starlette.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None


class _Announcement:
    """What zeroconf hands back for one resolved service."""

    def __init__(self, properties: dict, addresses=("192.168.1.20",), port=8001):
        self.properties = properties
        self.port = port
        self._addresses = list(addresses)

    def parsed_addresses(self):
        return self._addresses


def _said(**overrides) -> dict:
    said = {b"id": b"Aaaa111111", b"name": b"basement cab",
            b"features": b"library,frontend", b"version": b"3.0.0"}
    said.update(overrides)
    return said


class ReadingAnAnnouncementTests(unittest.TestCase):
    def test_identity_comes_back_whole(self) -> None:
        peer = discovery._as_peer(_Announcement(_said()))

        self.assertEqual(peer.install_id, "Aaaa111111")
        self.assertEqual(peer.display_name, "basement cab")
        self.assertEqual(peer.features, ("library", "frontend"))
        self.assertEqual(peer.url, "http://192.168.1.20:8001")

    def test_a_record_with_no_identity_is_not_a_peer(self) -> None:
        """Anything on the network can announce a service of this type. What makes one
        of ours is the id every other surface keys on."""
        self.assertIsNone(discovery._as_peer(_Announcement(_said(id=b""))))

    def test_a_record_that_resolved_to_no_address_is_not_a_peer(self) -> None:
        """There is nothing to ask, so there is nothing to offer."""
        self.assertIsNone(discovery._as_peer(_Announcement(_said(), addresses=())))

    def test_no_features_is_read_as_none_rather_than_as_one_blank(self) -> None:
        peer = discovery._as_peer(_Announcement(_said(features=b"")))

        self.assertEqual(peer.features, ())

    def test_this_machine_has_an_address_to_announce(self) -> None:
        self.assertTrue(discovery._routable_address())


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
class DiscoveredRouteTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def test_nothing_heard_is_an_empty_list_rather_than_an_error(self) -> None:
        with patch.object(discovery, "peers", lambda: []):
            body = self.client.get("/devices/discovered").json()

        self.assertEqual(body, {"count": 0, "installs": []})

    def test_what_was_heard_is_offered_with_a_url_to_reach_it(self) -> None:
        peer = discovery.Peer(install_id="Aaaa111111", display_name="basement cab",
                              features=("library",), address="192.168.1.20", port=8001)
        with patch.object(discovery, "peers", lambda: [peer]):
            body = self.client.get("/devices/discovered").json()

        self.assertEqual(body["count"], 1)
        self.assertEqual(body["installs"][0]["url"], "http://192.168.1.20:8001")
        self.assertEqual(body["installs"][0]["features"], ["library"])

    def test_the_word_is_not_read_as_a_device_id(self) -> None:
        """`/devices/{device_id}` would match it, so the order of the two matters."""
        with patch.object(discovery, "peers", lambda: []):
            self.assertEqual(self.client.get("/devices/discovered").status_code, 200)


class RecordingWhatWasHeardTests(TempTree):
    """What an install does with a peer depends on what it is for."""

    def setUp(self) -> None:
        super().setUp()
        self.registry = registry_module.DeviceRegistry(self.root / "devices.json")
        patcher = patch.object(registry_module, "get_device_registry",
                               lambda: self.registry)
        patcher.start()
        self.addCleanup(patcher.stop)
        also = patch("httpapi.instance.get_device_registry", lambda: self.registry)
        also.start()
        self.addCleanup(also.stop)

    def _peer(self):
        return discovery.Peer(install_id="Aaaa111111", display_name="basement cab",
                              features=("library",), address="192.168.1.20", port=8001)

    def _with_features(self, *names):
        return patch.object(install_identity, "features", lambda _config: list(names))

    def test_an_install_that_manages_devices_files_what_it_heard(self) -> None:
        with self._with_features(install_identity.DEVICES):
            instance._heard_from(self._peer())

        held = self.registry.get("Aaaa111111")
        self.assertEqual(held.display_name, "basement cab")
        self.assertEqual(held.address, "192.168.1.20")
        self.assertEqual(held.port, 8001)

    def test_an_install_that_does_not_keeps_no_list(self) -> None:
        """Announcing is to everybody; what to do with it is each install's own."""
        with self._with_features(install_identity.FRONTEND):
            instance._heard_from(self._peer())

        self.assertEqual(self.registry.devices(), [])


if __name__ == "__main__":
    unittest.main()
