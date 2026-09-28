"""The registry: which devices an install has been told about.

Data only. There is no routing, no aggregation and no picking one to launch on - all
three need decisions across devices that nothing has made. What a registry buys today is
attribution: an event carries the `install_id` it happened on, and this turns that id
into a name someone recognizes.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

import httpapi
from common import device_client
from common import device_registry as registry_module
from common.i18n import t
from tests.support.library import TempTree

try:
    from starlette.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None

CAB = {"device_id": "Aaaa111111", "display_name": "basement cab",
       "features": ["library", "frontend"]}
DESK = {"device_id": "Bbbb222222", "display_name": "desktop", "features": ["device"]}
PHONE = {"device_id": "Pppp444444", "display_name": "iPhone",
         "kind": "vpx_mobile", "address": "192.168.1.50"}


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
class DeviceRegistryApiTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        registry = registry_module.DeviceRegistry(self.root / "devices.json")
        patcher = patch.object(registry_module, "get_device_registry", lambda: registry)
        patcher.start()
        self.addCleanup(patcher.stop)
        also = patch("common.device_ops.get_device_registry", lambda: registry)
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
        self.assertEqual(body["features"], CAB["features"])
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
        """A device behind a router does not know how it is reached, so a body that
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
        """A closed set, checked at the boundary. console switches on this to decide what
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

    def test_a_mobile_device_is_added_without_an_id_and_gets_one(self) -> None:
        """The phone is not the caller - a person is registering it - so it cannot offer
        an id and one is minted here."""
        body = self.client.put("/devices", json={"kind": "vpx_mobile",
                                                 "display_name": "iPad",
                                                 "address": "192.168.1.60"}).json()

        self.assertTrue(body["device_id"], "an id was minted")
        self.assertEqual(body["address"], "192.168.1.60", "declared, not observed")
        self.assertEqual(self.client.get("/devices").json()["count"], 1)

    def test_two_mobile_devices_coexist(self) -> None:
        """An iPhone and an iPad at once. The singular [mobile] key is what made this
        impossible, and an id derived from an address would have collapsed them the
        moment DHCP handed one the other's."""
        first = self.client.put("/devices", json={"kind": "vpx_mobile", "display_name": "iPhone",
                                                  "address": "192.168.1.50"}).json()
        second = self.client.put("/devices", json={"kind": "vpx_mobile", "display_name": "iPad",
                                                   "address": "192.168.1.60"}).json()

        self.assertNotEqual(first["device_id"], second["device_id"])
        self.assertEqual(self.client.get("/devices").json()["count"], 2)

    def test_a_mobile_device_keeps_its_id_when_its_address_changes(self) -> None:
        added = self.client.put("/devices", json={"kind": "vpx_mobile", "display_name": "iPhone",
                                                  "address": "192.168.1.50"}).json()

        moved = self.client.put("/devices", json={"device_id": added["device_id"],
                                                  "kind": "vpx_mobile",
                                                  "address": "192.168.1.77"}).json()

        self.assertEqual(moved["device_id"], added["device_id"])
        self.assertEqual(moved["address"], "192.168.1.77")
        self.assertEqual(self.client.get("/devices").json()["count"], 1, "one phone")

    def test_a_mobile_device_needs_an_address(self) -> None:
        """Its address is the only way to reach it, and nothing else will supply one."""
        response = self.client.put("/devices", json={"kind": "vpx_mobile", "display_name": "iPad"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/devices").json()["count"], 0)

    def test_an_install_still_cannot_omit_its_id(self) -> None:
        """Minting is for devices that cannot identify themselves. An install can."""
        response = self.client.put("/devices", json={"display_name": "cab"})

        self.assertEqual(response.status_code, 400)

    def test_the_registry_is_linked_from_discovery(self) -> None:
        """So an integrator finds it by asking rather than by reading this file."""
        links = self.client.get("/").json()["links"]

        self.assertEqual(links["devices"], "/api/v1/devices")

    def test_an_install_says_which_port_it_answers_on(self) -> None:
        """The socket says where a request came from, never what that machine listens
        on, so this is the only way the other half of an address arrives."""
        self.client.put("/devices", json={**CAB, "port": 8001})

        device = self.client.get(f"/devices/{CAB['device_id']}").json()
        self.assertEqual(device["port"], 8001)

    def test_a_device_that_says_no_port_is_recorded_without_one(self) -> None:
        """Every entry written before installs sent one. Half an address is not an
        address, and 0 is what says so."""
        self.client.put("/devices", json=CAB)

        device = self.client.get(f"/devices/{CAB['device_id']}").json()
        self.assertEqual(device["port"], 0)

    def test_probing_reports_a_state_for_every_device(self) -> None:
        """Including the ones it cannot dial: a listing that silently drops those is a
        listing that says a device is fine because nothing asked it."""
        self.client.put("/devices", json=CAB)
        self.client.put("/devices", json=DESK)

        probes = self.client.post("/devices/probe").json()["probes"]

        self.assertEqual({p["device_id"] for p in probes},
                         {CAB["device_id"], DESK["device_id"]})

    def test_a_device_with_no_port_cannot_be_asked_rather_than_being_down(self) -> None:
        """Two different facts. Switching the machine on does not fix this one."""
        self.client.put("/devices", json=CAB)

        probe = self.client.post("/devices/probe").json()["probes"][0]

        self.assertEqual(probe["state"], "unaskable")
        self.assertIn("port", probe["reason"])

    def test_a_device_that_does_not_answer_is_unreachable(self) -> None:
        # Port 9 discards whatever it is sent, so nothing answers on it.
        self.client.put("/devices", json={**CAB, "port": 9})

        probe = self.client.post("/devices/probe").json()["probes"][0]

        self.assertEqual(probe["state"], "unreachable")
        self.assertEqual(probe["reason"], t(probe["reason_key"]))
        self.assertNotIn("HTTPConnectionPool", probe["reason"])

    def test_one_device_can_be_asked_on_its_own(self) -> None:
        """So a page can show each answer as it comes, rather than all of them when the
        slowest has timed out."""
        self.client.put("/devices", json={**CAB, "port": 9})
        self.client.put("/devices", json=DESK)

        response = self.client.post(f"/devices/{CAB['device_id']}/probe")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device_id"], CAB["device_id"])
        self.assertEqual(response.json()["state"], "unreachable")

    def test_asking_one_it_does_not_know_is_a_404(self) -> None:
        response = self.client.post("/devices/Zzzz999999/probe")

        self.assertEqual(response.status_code, 404)

    def test_a_device_that_never_answered_has_no_reachable_time_from_a_probe(self) -> None:
        """It has one from announcing - that is the push half - but a failed probe must
        not advance it, or the value stops meaning anything."""
        self.client.put("/devices", json={**CAB, "port": 9})
        announced = self.client.get(f"/devices/{CAB['device_id']}").json()["last_reachable"]

        self.client.post("/devices/probe")

        after = self.client.get(f"/devices/{CAB['device_id']}").json()["last_reachable"]
        self.assertEqual(after, announced)

    def test_announcing_again_without_a_port_keeps_the_one_it_gave(self) -> None:
        """A device is the same device however many times it reconnects, and an
        announcement that omits a field is not the device withdrawing it."""
        self.client.put("/devices", json={**CAB, "port": 8001})
        self.client.put("/devices", json=CAB)

        device = self.client.get(f"/devices/{CAB['device_id']}").json()
        self.assertEqual(device["port"], 8001)


class _Answering:
    """A device that answers its probe, running `features`, with `report` for what its
    browser plays - or raising it, where it is an exception."""

    def __init__(self, features: list[str], report: dict | Exception) -> None:
        self.features = features
        self.report = report
        self.asked = 0

    def probe(self) -> dict:
        return {"state": device_client.ANSWERING, "what": "VPinFE 3.0.0", "reason": "",
                "features": self.features}

    def frontend_browser(self) -> dict:
        self.asked += 1
        if isinstance(self.report, Exception):
            raise self.report
        return self.report


NO_H264 = {"state": "no_h264", "browser": "Chromium 145.0.7632.0",
           "formats": {"h264": False, "vp9": True, "hevc": None}}


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
class ProbeAsksTheBrowserTests(TempTree):
    """The probe asks an answering frontend device what its browser plays, and the
    registry keeps the answer for when it is switched off."""

    def setUp(self) -> None:
        super().setUp()
        registry = registry_module.DeviceRegistry(self.root / "devices.json")
        self.enterContext(patch.object(registry_module, "get_device_registry",
                                       lambda: registry))
        self.enterContext(patch("common.device_ops.get_device_registry", lambda: registry))
        self.device = _Answering(["library", "frontend"], NO_H264)
        self.enterContext(patch.object(device_client, "for_device",
                                       side_effect=lambda *_: self.device))
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        self.client.put("/devices", json={**CAB, "port": 8001})

    def _probed(self) -> dict:
        return self.client.post(f"/devices/{CAB['device_id']}/probe").json()

    def _held(self) -> dict | None:
        return self.client.get(f"/devices/{CAB['device_id']}").json()["browser"]

    def test_what_it_plays_comes_back_with_the_probe_and_is_kept(self) -> None:
        probed = self._probed()["browser"]

        self.assertEqual((probed["state"], probed["name"], probed["formats"]),
                         ("no_h264", "Chromium 145.0.7632.0",
                          {"h264": False, "vp9": True, "hevc": None}))
        self.assertTrue(probed["checked_at"])
        self.assertEqual(self._held(), probed)

    def test_a_device_switched_off_keeps_the_last_answer(self) -> None:
        kept = self._probed()["browser"]
        self.device = _Failing(requests.ConnectionError("off"))  # type: ignore[assignment]

        self._probed()

        self.assertEqual(self._held(), kept)

    def test_one_too_old_to_say_keeps_what_was_held(self) -> None:
        kept = self._probed()["browser"]
        self.device = _Answering(["frontend"],
                                 device_client.TooOldError(t(device_client.TOO_OLD)))

        self.assertEqual(self._probed()["browser"], kept)
        self.assertEqual(self._held(), kept)

    def test_one_that_no_longer_runs_the_frontend_has_it_cleared(self) -> None:
        self._probed()
        self.device = _Answering(["library"], NO_H264)

        probed = self._probed()

        self.assertIsNone(probed["browser"])
        self.assertIsNone(self._held())
        self.assertEqual(self.device.asked, 0)

    def test_this_install_is_not_asked_by_its_own_probe(self) -> None:
        kept = self._probed()["browser"]
        self.device = device_client.LocalDevice()  # type: ignore[assignment]

        self.assertEqual(self._probed()["browser"], kept)


class _Failing:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def probe(self) -> dict:
        raise self.exc


class ProbeReasonTests(unittest.TestCase):
    """What failed, said as what a person can do something about."""

    def _reason(self, exc: Exception) -> str:
        found = device_client.probe(_Failing(exc))  # type: ignore[arg-type]
        self.assertEqual(found["state"], device_client.UNREACHABLE)
        self.assertEqual(found["reason"], t(found["reason_key"]))
        return str(found["reason_key"])

    def test_a_machine_with_nothing_on_its_port_is_told_apart(self) -> None:
        try:
            requests.get("http://127.0.0.1:1/api/v1", timeout=1)
        except requests.ConnectionError as exc:
            self.assertEqual(self._reason(exc), "device.reason.refused")
        else:  # pragma: no cover
            self.skipTest("something answers on port 1 here")

    def test_no_answer_in_time(self) -> None:
        self.assertEqual(self._reason(requests.ConnectTimeout("slow")),
                         "device.reason.timed_out")

    def test_an_answer_that_cannot_be_read(self) -> None:
        self.assertEqual(self._reason(requests.HTTPError("500")),
                         "device.reason.unreadable")
        self.assertEqual(self._reason(ValueError("Invalid JSON")),
                         "device.reason.unreadable")

    def test_anything_else_could_not_be_reached(self) -> None:
        self.assertEqual(self._reason(requests.ConnectionError("no route")),
                         "device.reason.unreachable")


if __name__ == "__main__":
    unittest.main()
