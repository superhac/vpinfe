"""2.x's VPinPlay profiles over core's guests: the three theme methods, and the Manager
UI's Multi page.

A join goes over this install's own API; here that request is answered by the same app in
the test client, with the real VPinPlay extension reading the card.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

from common import players
from common.extensions import accounts, temporary_profiles
from frontend.api import API
from managerui.services import vpinplay_runtime_service
from tests.extensions.test_cards import KEY, _2x_card
from tests.extensions.test_vpinplay_accounts import NAME, VPinPlayCase

NOBODY = {"active": False, "profile": None, "active_games": 0, "profiles": [],
          "activeProfileKey": ""}


class ProfilesCase(VPinPlayCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.make_owner()
        self.load()
        here = patch.object(temporary_profiles.requests, "post", self._here)
        here.start()
        self.addCleanup(here.stop)
        self.api = API.__new__(API)
        self.api.ws_bridge = MagicMock()

    def _here(self, url: str, json: dict, timeout: int) -> SimpleNamespace:
        """This install's own API, answered in-process."""
        root = "http://127.0.0.1:"
        self.assertTrue(url.startswith(root), url)
        answered = self.client.post(url.split("/api/v1", 1)[1], json=json)
        return SimpleNamespace(ok=answered.is_success, status_code=answered.status_code,
                               json=answered.json)

    def card(self, user_id: str = "visitor", initials: str = "vis") -> dict:
        return json.loads(_2x_card(user_id, initials, KEY)[0])

    def told(self) -> list[dict]:
        return [call.args[0] for call in
                self.api.ws_bridge.send_event_all_with_iframe.call_args_list]


class TheThemeMethods(ProfilesCase):
    def test_nobody_is_a_profile_until_a_card_joins(self) -> None:
        players.get_roster().add_guest("GST")

        self.assertEqual(self.api.get_temporary_vpinplay_profile(), NOBODY)

    def test_a_card_joins_a_guest_who_is_up_and_shares(self) -> None:
        said = self.api.set_temporary_vpinplay_profile(self.card())

        (guest,) = [one for one in players.get_roster().players() if one.guest]
        self.assertEqual(said["profile"]["profileKey"], guest.player_id)
        self.assertEqual((said["active"], said["profile"]["userId"],
                          said["profile"]["initials"], said["activeProfileKey"]),
                         (True, "visitor", "VIS", guest.player_id))
        self.assertEqual([one.player_id for one in players.get_roster().up()],
                         [guest.player_id])
        self.assertTrue(players.get_roster().sharing(guest.player_id, NAME))
        self.assertEqual(self.api.get_temporary_vpinplay_profile(), said)

    def test_the_change_is_told_to_every_window(self) -> None:
        said = self.api.set_temporary_vpinplay_profile(self.card())

        self.assertEqual(self.told(), [{"type": "VPinPlayAlternateProfileChanged",
                                        "profile": said}])

    def test_the_key_a_card_carries_is_never_answered(self) -> None:
        said = self.api.set_temporary_vpinplay_profile(self.card())

        self.assertNotIn(KEY, json.dumps(said))
        self.assertEqual(said["profile"]["machineId"], "")

    def test_a_refused_card_leaves_the_guests_as_they_were(self) -> None:
        self.api.set_temporary_vpinplay_profile(self.card())
        before = self.api.get_temporary_vpinplay_profile()

        said = self.api.set_temporary_vpinplay_profile({**self.card("other"), "version": 2})

        self.assertEqual(said, before)

    def test_clearing_signs_every_guest_out_with_what_they_held(self) -> None:
        self.api.set_temporary_vpinplay_profile(self.card())
        players.get_roster().add_guest("GST")
        (visitor,) = [one.player_id for one in players.get_roster().players()
                      if one.guest and one.initials == "VIS"]

        said = self.api.clear_temporary_vpinplay_profile()

        self.assertEqual(said, NOBODY)
        self.assertEqual([one.player_id for one in players.get_roster().players()],
                         [self.owner])
        self.assertEqual(accounts.values(NAME, visitor), {})
        self.assertEqual(self.told()[-1], {"type": "VPinPlayAlternateProfileChanged",
                                           "profile": NOBODY})


class TheMultiPage(ProfilesCase):
    def upload(self, user_id: str = "visitor", initials: str = "vis") -> dict:
        saved = _2x_card(user_id, initials, KEY)[1]
        return vpinplay_runtime_service.activate_profile_from_upload(
            f"vpinplay-{user_id}.svg", saved.encode("utf-8"))

    def test_an_uploaded_card_file_is_the_active_profile(self) -> None:
        said = self.upload()

        self.assertEqual((said["profile"]["userId"], said["profile"]["initials"]),
                         ("visitor", "VIS"))

    def test_several_are_held_and_one_is_chosen(self) -> None:
        first = self.upload("visitor", "vis")["activeProfileKey"]
        second = self.upload("another", "ano")["activeProfileKey"]

        said = vpinplay_runtime_service.set_current_profile(first)

        self.assertEqual([one["userId"] for one in said["profiles"]],
                         ["another", "visitor"])
        self.assertEqual(said["activeProfileKey"], first)
        self.assertNotEqual(first, second)

    def test_removing_the_current_one_signs_that_guest_out(self) -> None:
        first = self.upload("visitor", "vis")["activeProfileKey"]
        second = self.upload("another", "ano")["activeProfileKey"]

        said = vpinplay_runtime_service.clear_profile_by_key(second)

        self.assertEqual([one["profileKey"] for one in said["profiles"]], [first])
        self.assertIsNone(players.get_roster().get(second))
        self.assertEqual(vpinplay_runtime_service.clear_profile_by_key(second), said)

    def test_clear_all_signs_every_guest_out(self) -> None:
        self.upload()

        self.assertEqual(vpinplay_runtime_service.clear_profile(), NOBODY)

    def test_a_file_that_is_no_card_is_refused_in_core_s_words(self) -> None:
        with self.assertRaises(ValueError) as refused:
            vpinplay_runtime_service.activate_profile_from_upload("x.svg", b"<svg></svg>")

        self.assertEqual(str(refused.exception), "This holds no card VPinFE can read")


class NotAnswering(unittest.TestCase):
    def test_an_install_that_cannot_be_reached_says_why(self) -> None:
        with patch.object(temporary_profiles.requests, "post",
                          side_effect=requests.ConnectionError("refused")), \
                self.assertRaises(temporary_profiles.service_errors.RefusedError):
            temporary_profiles.join("{}")


if __name__ == "__main__":
    unittest.main()
