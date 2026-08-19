"""The registry: which devices a hub has been told about.

Data only. There is no routing, no aggregation and no picking one to launch on - all
three need decisions across devices that nothing has made. What a registry buys today is
attribution: an event carries the `install_id` it happened on, and this turns that id
into a name someone recognizes.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpapi
from common import device_registry as registry_module
from tests.support.library import TempTree

try:
    from starlette.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None

CAB = {"device_id": "Aaaa111111", "display_name": "basement cab",
       "roles": ["hub", "device"]}
DESK = {"device_id": "Bbbb222222", "display_name": "desktop", "roles": ["device"]}
PHONE = {"device_id": "Pppp444444", "display_name": "iPhone", "kind": "vpx_mobile"}


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
class DeviceRegistryApiTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        registry = registry_module.DeviceRegistry(self.root / "devices.json")
        patcher = patch.object(registry_module, "get_device_registry", lambda: registry)
        patcher.start()
        self.addCleanup(patcher.stop)
        also = patch("httpapi.devices.get_device_registry", lambda: registry)
        also.start()
        self.addCleanup(also.stop)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def test_a_hub_knows_nobody_until_someone_says_hello(self) -> None:
        body = self.client.get("/devices").json()

        self.assertEqual(body, {"count": 0, "devices": []})

    def test_announcing_records_what_the_device_said(self) -> None:
        response = self.client.put("/devices", json=CAB)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["device_id"], CAB["device_id"])
        self.assertEqual(body["display_name"], CAB["display_name"])
        self.assertEqual(body["roles"], CAB["roles"])
        self.assertTrue(body["first_seen"])
        self.assertEqual(body["links"]["self"], "/api/v1/devices/Aaaa111111")

    def test_announcing_twice_is_one_device_heard_from_twice(self) -> None:
        """A device restarting must not become a second entry."""
        first = self.client.put("/devices", json=CAB).json()
        self.client.put("/devices", json=CAB | {"display_name": "renamed"})

        listed = self.client.get("/devices").json()
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["devices"][0]["display_name"], "renamed",
                         "the install owns its name; the registry is a copy")
        self.assertEqual(listed["devices"][0]["first_seen"], first["first_seen"],
                         "it is the same device, however many times it reconnects")

    def test_two_devices_are_two_entries(self) -> None:
        self.client.put("/devices", json=CAB)
        self.client.put("/devices", json=DESK)

        listed = self.client.get("/devices").json()

        self.assertEqual(listed["count"], 2)
        self.assertEqual({p["device_id"] for p in listed["devices"]},
                         {CAB["device_id"], DESK["device_id"]})

    def test_the_address_is_observed_rather_than_claimed(self) -> None:
        """A device behind a router does not know how the hub reaches it, so a body that
        said would be a claim. The socket is the only party that knows."""
        body = self.client.put("/devices", json=CAB | {"address": "10.0.0.99"}).json()

        self.assertNotEqual(body["address"], "10.0.0.99")

    def test_a_device_with_no_id_is_refused(self) -> None:
        """An install with no id is not an identity, and a registry keyed on "" is a
        registry of one."""
        response = self.client.put("/devices", json={"device_id": "  "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/devices").json()["count"], 0)

    def test_one_device_answers_for_itself(self) -> None:
        self.client.put("/devices", json=CAB)

        body = self.client.get(f"/devices/{CAB['device_id']}").json()

        self.assertEqual(body["display_name"], CAB["display_name"])

    def test_an_unknown_device_is_a_404(self) -> None:
        self.assertEqual(self.client.get("/devices/Nope111111").status_code, 404)

    def test_forgetting_a_device_removes_it(self) -> None:
        self.client.put("/devices", json=CAB)

        self.assertEqual(self.client.delete(f"/devices/{CAB['device_id']}").status_code,
                         204)
        self.assertEqual(self.client.get("/devices").json()["count"], 0)

    def test_forgetting_one_that_was_never_there_is_a_404(self) -> None:
        self.assertEqual(self.client.delete("/devices/Nope111111").status_code, 404)

    def test_an_unknown_kind_is_refused(self) -> None:
        """A closed set, checked at the boundary. hubui switches on this to decide what
        it can do with an entry, so a kind it has never heard of is worse stored than
        rejected - it would reach a screen as a device nothing knows how to talk to."""
        response = self.client.put("/devices", json=CAB | {"kind": "toaster"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/devices").json()["count"], 0,
                         "refused means not stored, not stored-then-complained-about")

    def test_a_kind_round_trips(self) -> None:
        body = self.client.put("/devices", json=PHONE).json()

        self.assertEqual(body["kind"], "vpx_mobile")
        self.assertEqual(self.client.get(f"/devices/{PHONE['device_id']}").json()["kind"],
                         "vpx_mobile")

    def test_an_announcement_with_no_kind_is_a_vpinfe_install(self) -> None:
        """Every device that can announce itself today is one, so the default is the
        one a caller written before kind existed would have meant."""
        body = self.client.put("/devices", json={"device_id": "Cccc333333"}).json()

        self.assertEqual(body["kind"], "vpinfe")

    def test_the_registry_is_linked_from_discovery(self) -> None:
        """So an integrator finds it by asking rather than by reading this file."""
        links = self.client.get("/").json()["links"]

        self.assertEqual(links["devices"], "/api/v1/devices")


if __name__ == "__main__":
    unittest.main()
