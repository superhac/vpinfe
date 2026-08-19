"""The roster: which players a hub has been told about.

Data only. There is no routing, no aggregation and no picking one to launch on - all
three need decisions across players that nothing has made. What a roster buys today is
attribution: an event carries the `install_id` it happened on, and this turns that id
into a name someone recognizes.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpapi
from common import roster as roster_module
from tests.support.library import TempTree

try:
    from starlette.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None

CAB = {"install_id": "Aaaa111111", "display_name": "basement cab",
       "roles": ["hub", "device"]}
DESK = {"install_id": "Bbbb222222", "display_name": "desktop", "roles": ["device"]}


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
class PlayerRosterTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        roster = roster_module.Roster(self.root / "devices.json")
        patcher = patch.object(roster_module, "get_roster", lambda: roster)
        patcher.start()
        self.addCleanup(patcher.stop)
        also = patch("httpapi.players.get_roster", lambda: roster)
        also.start()
        self.addCleanup(also.stop)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def test_a_hub_knows_nobody_until_someone_says_hello(self) -> None:
        body = self.client.get("/devices").json()

        self.assertEqual(body, {"count": 0, "devices": []})

    def test_announcing_records_what_the_player_said(self) -> None:
        response = self.client.put("/devices", json=CAB)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["install_id"], CAB["install_id"])
        self.assertEqual(body["display_name"], CAB["display_name"])
        self.assertEqual(body["roles"], CAB["roles"])
        self.assertTrue(body["first_seen"])
        self.assertEqual(body["links"]["self"], "/api/v1/devices/Aaaa111111")

    def test_announcing_twice_is_one_player_heard_from_twice(self) -> None:
        """A player restarting must not become a second entry."""
        first = self.client.put("/devices", json=CAB).json()
        self.client.put("/devices", json=CAB | {"display_name": "renamed"})

        listed = self.client.get("/devices").json()
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["devices"][0]["display_name"], "renamed",
                         "the install owns its name; the roster is a copy")
        self.assertEqual(listed["devices"][0]["first_seen"], first["first_seen"],
                         "it is the same player, however many times it reconnects")

    def test_two_players_are_two_entries(self) -> None:
        self.client.put("/devices", json=CAB)
        self.client.put("/devices", json=DESK)

        listed = self.client.get("/devices").json()

        self.assertEqual(listed["count"], 2)
        self.assertEqual({p["install_id"] for p in listed["devices"]},
                         {CAB["install_id"], DESK["install_id"]})

    def test_the_address_is_observed_rather_than_claimed(self) -> None:
        """A player behind a router does not know how the hub reaches it, so a body that
        said would be a claim. The socket is the only party that knows."""
        body = self.client.put("/devices", json=CAB | {"address": "10.0.0.99"}).json()

        self.assertNotEqual(body["address"], "10.0.0.99")

    def test_a_player_with_no_id_is_refused(self) -> None:
        """An install with no id is not an identity, and a roster keyed on "" is a
        roster of one."""
        response = self.client.put("/devices", json={"install_id": "  "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/devices").json()["count"], 0)

    def test_one_player_answers_for_itself(self) -> None:
        self.client.put("/devices", json=CAB)

        body = self.client.get(f"/devices/{CAB['install_id']}").json()

        self.assertEqual(body["display_name"], CAB["display_name"])

    def test_an_unknown_player_is_a_404(self) -> None:
        self.assertEqual(self.client.get("/devices/Nope111111").status_code, 404)

    def test_forgetting_a_player_removes_it(self) -> None:
        self.client.put("/devices", json=CAB)

        self.assertEqual(self.client.delete(f"/devices/{CAB['install_id']}").status_code,
                         204)
        self.assertEqual(self.client.get("/devices").json()["count"], 0)

    def test_forgetting_one_that_was_never_there_is_a_404(self) -> None:
        self.assertEqual(self.client.delete("/devices/Nope111111").status_code, 404)

    def test_the_roster_is_linked_from_discovery(self) -> None:
        """So an integrator finds it by asking rather than by reading this file."""
        links = self.client.get("/").json()["links"]

        self.assertEqual(links["devices"], "/api/v1/devices")


if __name__ == "__main__":
    unittest.main()
