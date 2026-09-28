"""VPinPlay's account on each player: chosen free, claimed deliberately, its card both
ways, the owner's account made from the old settings, and the settings that are left.

Driven through core's routes over the real extension, the way the Console and the phone
ask. `patch.object` on `requests` stands in for VPinPlay itself - nothing here reaches the
real service, and a call that is not stubbed for a test fails it.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from configparser import ConfigParser
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from starlette.testclient import TestClient

import httpapi
from common import extensions, players, tokens
from common.extensions import accounts, catalogs, contributions, host, store
from common.i18n import t
from extensions.vpinplay import client as vpinplay_client
from extensions.vpinplay import sync
from httpapi import events as event_stream
from tests.extensions.test_cards import KEY, _2x_card

NAME = "vpinplay"
MINTED = re.compile(r"^[A-Za-z0-9]{64}$")


def _ini(initials: str = "OWN") -> ConfigParser:
    parser = ConfigParser()
    parser.add_section("vpinplay")
    parser.set("vpinplay", "initials", initials)
    return parser


def _answer(status_code: int, body: dict) -> MagicMock:
    response = MagicMock(status_code=status_code, ok=200 <= status_code < 400)
    response.json.return_value = body
    response.raise_for_status.side_effect = (
        None if response.ok else requests.HTTPError(response=response))
    return response


class VPinPlayCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = store.ExtensionStore(self.root / "extensions.json")
        self.registry = host.Registry(self.store)
        extensions.set_registry(self.registry)
        self.addCleanup(extensions.set_registry, host.Registry())
        self.addCleanup(self.registry.clear)
        players.reset_for_tests(self.root / "players.json")
        self.addCleanup(players.reset_for_tests)
        accounts.reset_for_tests()
        self.addCleanup(accounts.reset_for_tests)
        for cleared in (contributions.clear, catalogs.clear):
            self.addCleanup(cleared)
        self.addCleanup(tokens.forget, NAME)
        self.addCleanup(event_stream.reset)
        for owner, method in ((vpinplay_client.requests, "get"), (sync.requests, "post")):
            outward = patch.object(owner, method,
                                   side_effect=AssertionError("VPinPlay was contacted"))
            outward.start()
            self.addCleanup(outward.stop)

    def make_owner(self, initials: str = "OWN") -> str:
        owner = players.get_roster().ensure_owner(_ini(initials))
        assert owner is not None
        return owner.player_id

    def load(self) -> None:
        record = self.registry.load(host.BUNDLED_DIR / NAME)
        self.assertEqual(record.state, host.LOADED, record.reason)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def ok(self, response, status: int = 200) -> dict:
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def account(self, player_id: str) -> dict:
        return self.ok(self.client.get(f"/players/{player_id}/accounts/{NAME}"))

    def fill(self, player_id: str, **values: str) -> dict:
        return self.ok(self.client.put(f"/players/{player_id}/accounts/{NAME}",
                                       json={"values": values}))

    def held(self, player_id: str) -> dict[str, str]:
        return accounts.values(NAME, player_id, self.store)

    def act(self, player_id: str, act: str):
        return self.client.post(f"/players/{player_id}/accounts/{NAME}/acts/{act}")

    def available(self, candidate: str, **get_kwargs: object):
        """The Console's own route to it: straight through to the extension, the way its
        settings and community pages are asked."""
        with patch.object(vpinplay_client.requests, "get", **get_kwargs):
            return self.client.get(f"/ext/{NAME}/available", params={"candidate": candidate})

    def claim(self, player_id: str, *, get_kwargs: object = None, post_kwargs: object = None):
        patches = [patch.object(vpinplay_client.requests, "get", **(get_kwargs or {
            "return_value": _answer(200, {"available": True})}))]
        if post_kwargs is not None:
            patches.append(patch.object(sync.requests, "post", **post_kwargs))
        else:
            patches.append(patch.object(sync.requests, "post",
                                        return_value=_answer(200, {"status": "ok"})))
        for one in patches:
            one.start()
            self.addCleanup(one.stop)
        return self.act(player_id, "claim")


class TheAccount(VPinPlayCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.make_owner()
        self.load()

    def test_every_player_is_offered_one(self) -> None:
        found = self.ok(self.client.get(f"/players/{self.owner}/accounts"))["accounts"]

        self.assertEqual([(one["extension"], one["label"]) for one in found],
                         [(NAME, "VPinPlay")])

    def test_an_empty_account_has_no_id_and_is_not_claimed(self) -> None:
        found = self.account(self.owner)

        self.assertEqual((found["fields"], found["user_id"], found["claimed"],
                          found["page"], found["card"], found["share"]),
                         ([], "", False, "", False, False))
        self.assertEqual((found["status"], found["acts"], found["waiting"],
                          found["waiting_count"]), ("", [], False, 0))

    def test_share_leaves_its_words_to_core(self) -> None:
        self.assertEqual(self.account(self.owner)["share_help"], "")

    def test_the_declaration_carries_a_check_route_and_the_consent_lines(self) -> None:
        found = self.ok(self.client.get("/extensions"))["extensions"]
        account = next(one for one in found if one["name"] == NAME)["account"]

        self.assertEqual(account["check"], "/available")
        self.assertEqual(len(account["consent"]), 3)
        self.assertEqual(self.account(self.owner)["check"], "/available")

    def test_choosing_saves_the_id_alone_no_key_is_made(self) -> None:
        found = self.fill(self.owner, user_id=" Jordan ")

        self.assertEqual(self.held(self.owner), {"user_id": "jordan"})
        self.assertEqual((found["user_id"], found["claimed"], found["page"]),
                         ("jordan", False, ""))

    def test_the_id_is_stored_as_vpinplay_will_keep_it_lower_case(self) -> None:
        self.fill(self.owner, user_id="Jordan")

        self.assertEqual(self.held(self.owner)["user_id"], "jordan")

    def test_changing_the_chosen_id_is_free_while_unclaimed(self) -> None:
        self.fill(self.owner, user_id="jordan")

        self.fill(self.owner, user_id="jordan2")

        self.assertEqual(self.held(self.owner), {"user_id": "jordan2"})

    def test_a_key_written_with_the_id_is_the_one_held(self) -> None:
        """What a card carries into an account: both values at once, already claimed."""
        found = self.fill(self.owner, user_id="jordan", key=KEY)

        self.assertEqual(self.held(self.owner), {"user_id": "jordan", "key": KEY})
        self.assertTrue(found["claimed"])

    def test_clearing_the_id_keeps_a_key_already_held(self) -> None:
        self.fill(self.owner, user_id="jordan", key=KEY)

        self.fill(self.owner, user_id="")

        self.assertEqual(self.held(self.owner), {"key": KEY})

    def test_the_key_is_never_answered(self) -> None:
        answers = [self.fill(self.owner, user_id="jordan", key=KEY), self.account(self.owner),
                   self.ok(self.client.get(f"/ext/{NAME}/accounts/{self.owner}"))]

        self.assertNotIn(KEY, json.dumps(answers))

    def test_a_guests_account_is_held_in_memory(self) -> None:
        guest = players.get_roster().add_guest("ABC").player_id

        self.fill(guest, user_id="visitor")

        self.assertEqual(self.held(guest)["user_id"], "visitor")
        self.assertNotIn("visitor", json.dumps(self.store.accounts(NAME)))

    def test_a_claimed_account_reads_a_page_and_offers_your_page_through_it(self) -> None:
        self.fill(self.owner, user_id="jordan", key=KEY)

        found = self.account(self.owner)

        self.assertEqual(found["page"],
                         "https://www.vpinplay.com/players.html?userid=jordan")

    def test_only_a_claimed_account_with_something_waiting_offers_send_now(self) -> None:
        self.fill(self.owner, user_id="jordan")
        unclaimed = self.account(self.owner)["acts"]

        self.fill(self.owner, key=KEY)
        claimed_idle = self.account(self.owner)["acts"]

        self.assertEqual((unclaimed, claimed_idle), ([], []))


class TheAvailabilityCheck(VPinPlayCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.make_owner()
        self.load()

    def test_a_free_id_is_available(self) -> None:
        found = self.ok(self.available(
            "jordan", return_value=_answer(200, {"available": True})))

        self.assertEqual(found, {"available": True})

    def test_a_held_id_is_not(self) -> None:
        found = self.ok(self.available(
            "jordan", return_value=_answer(200, {"available": False})))

        self.assertEqual(found, {"available": False})

    def test_the_candidate_is_asked_for_lower_cased(self) -> None:
        with patch.object(vpinplay_client.requests, "get",
                          return_value=_answer(200, {"available": True})) as get:
            self.client.get(f"/ext/{NAME}/available", params={"candidate": "Jordan"})

        # Split across two literals: joined on one line this reads as a home directory
        # under /Users/, and it is VPinPlay's own REST shape instead.
        self.assertEqual(get.call_args.args[0],
                         "https://api.vpinplay.com:8888/api/v1/users/jordan"
                         "/available")

    def test_unreachable_is_refused_not_read_as_taken(self) -> None:
        response = self.available("jordan", side_effect=requests.ConnectionError("down"))

        self.assertEqual(response.status_code, 503)


class TheClaim(VPinPlayCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.make_owner()
        self.load()

    def test_claiming_checks_again_mints_a_key_and_registers_with_an_empty_send(self) -> None:
        self.fill(self.owner, user_id="jordan")

        with patch.object(vpinplay_client.requests, "get",
                          return_value=_answer(200, {"available": True})), \
             patch.object(sync.requests, "post",
                         return_value=_answer(200, {"status": "ok"})) as post:
            found = self.ok(self.act(self.owner, "claim"))

        self.assertTrue(found["claimed"])
        self.assertRegex(self.held(self.owner)["key"], MINTED)
        sent = post.call_args.kwargs["json"]
        self.assertEqual((sent["client"]["userId"], sent["client"]["initials"],
                          sent["tables"]), ("jordan", "OWN", []))

    def test_claiming_with_no_id_chosen_is_refused(self) -> None:
        response = self.act(self.owner, "claim")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.held(self.owner), {})

    def test_claiming_an_already_claimed_account_is_refused(self) -> None:
        self.fill(self.owner, user_id="jordan", key=KEY)

        response = self.act(self.owner, "claim")

        self.assertEqual(response.status_code, 400)

    def test_claiming_without_initials_is_refused(self) -> None:
        kept = players.get_roster().add_player("Jordan").player_id
        self.fill(kept, user_id="jordan")

        response = self.act(kept, "claim")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.held(kept), {"user_id": "jordan"})

    def test_a_taken_id_is_refused_and_no_key_is_made(self) -> None:
        self.fill(self.owner, user_id="jordan")

        response = self.claim(self.owner, get_kwargs={
            "return_value": _answer(200, {"available": False})})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.held(self.owner), {"user_id": "jordan"})

    def test_unreachable_while_claiming_is_refused_and_no_key_is_made(self) -> None:
        self.fill(self.owner, user_id="jordan")

        response = self.claim(self.owner,
                              get_kwargs={"side_effect": requests.ConnectionError("down")})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.held(self.owner), {"user_id": "jordan"})

    def test_a_refused_registration_is_refused_and_no_key_survives(self) -> None:
        self.fill(self.owner, user_id="jordan")

        response = self.claim(self.owner, post_kwargs={
            "return_value": _answer(200, {"status": "error"})})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.held(self.owner), {"user_id": "jordan"})


class TheDisconnect(VPinPlayCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.make_owner()
        self.load()

    def test_disconnecting_forgets_the_id_and_key(self) -> None:
        self.fill(self.owner, user_id="jordan", key=KEY)

        found = self.ok(self.act(self.owner, "disconnect"))

        self.assertEqual(self.held(self.owner), {})
        self.assertFalse(found["claimed"])

    def test_disconnecting_an_unclaimed_choice_forgets_it_too(self) -> None:
        self.fill(self.owner, user_id="jordan")

        self.act(self.owner, "disconnect")

        self.assertEqual(self.held(self.owner), {})


class TheActs(VPinPlayCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.make_owner()
        self.load()
        self.fill(self.owner, user_id="some one")
        self.claim(self.owner)

    def test_send_now_sends_nothing_and_says_so(self) -> None:
        said = self.ok(self.act(self.owner, "send_now"))

        self.assertEqual(said, {"message": "Nothing waiting to send"})

    def test_an_act_with_no_claimed_account_is_refused(self) -> None:
        guest = players.get_roster().add_guest("ABC").player_id

        self.assertEqual(self.act(guest, "send_now").status_code, 404)

    def test_an_act_it_does_not_have_is_refused(self) -> None:
        response = self.act(self.owner, "dance")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["message"], "VPinPlay has no act called dance")


class TheCard(VPinPlayCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.make_owner()
        self.load()

    def card_of(self, player_id: str):
        response = self.client.get(f"/players/{player_id}/accounts/{NAME}/card")
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def join(self, card: str, status: int = 201) -> dict:
        return self.ok(self.client.post("/players/guests/card", json={"card": card}), status)

    def read_card(self, card: object):
        return self.client.post(f"/ext/{NAME}/accounts/cards", json={"card": card})

    def refusal(self, **card: object) -> str:
        response = self.read_card({"type": "vpinplay_identity", "version": 1,
                                   "userId": "jordan", "initials": "ABC",
                                   "machineId": KEY, **card})
        self.assertEqual(response.status_code, 400, response.text)
        return response.json()["error"]["message"]

    def test_a_card_is_the_file_2x_saved_for_the_same_account(self) -> None:
        self.fill(self.owner, user_id="jordan", key=KEY)

        response = self.card_of(self.owner)

        self.assertEqual(response.text, _2x_card("jordan", "OWN", KEY)[1])
        self.assertEqual(response.headers["content-disposition"],
                         'attachment; filename="vpinplay-jordan.svg"')

    def test_a_card_made_from_an_account_reads_back_into_the_same_values(self) -> None:
        self.fill(self.owner, user_id="jordan", key=KEY)

        guest = self.join(self.card_of(self.owner).text)

        self.assertEqual((guest["name"], guest["initials"], guest["up"]),
                         ("jordan", "OWN", True))
        self.assertEqual(accounts.values(NAME, guest["id"]), self.held(self.owner))

    def test_a_2x_card_file_joins_as_a_guest_who_shares(self) -> None:
        _said, saved = _2x_card("visitor", "abc", KEY)

        guest = self.join(saved)

        self.assertEqual(guest["initials"], "ABC")
        self.assertEqual(accounts.values(NAME, guest["id"]),
                         {"user_id": "visitor", "key": KEY})
        self.assertTrue(self.account(guest["id"])["share"])

    def test_the_card_text_on_its_own_joins(self) -> None:
        said, _saved = _2x_card("visitor", "ab", KEY)

        guest = self.join(said)

        self.assertEqual((guest["initials"], accounts.values(NAME, guest["id"])["key"]),
                         ("AB", KEY))

    def test_a_card_read_answers_the_account_its_initials_and_a_name(self) -> None:
        said = self.ok(self.read_card(json.loads(_2x_card("visitor", "ab", KEY)[0])))

        self.assertEqual(said, {"name": "visitor", "initials": "AB",
                                "values": {"user_id": "visitor", "key": KEY}})

    def test_another_type_is_refused_in_2xs_words(self) -> None:
        self.assertEqual(self.refusal(type="other_card"),
                         "Unsupported QR payload type: other_card")
        self.assertEqual(self.refusal(type=""), "Unsupported QR payload type: missing")

    def test_another_version_is_refused_in_2xs_words(self) -> None:
        self.assertEqual(self.refusal(version=2), "Unsupported QR payload version: 2")
        self.assertEqual(self.refusal(version="one"), "QR payload version is invalid")

    def test_a_card_missing_what_2x_required_is_refused_in_its_words(self) -> None:
        self.assertEqual(self.refusal(userId=""), "QR payload is missing userId")
        self.assertEqual(self.refusal(initials=" "), "QR payload is missing initials")
        self.assertEqual(self.refusal(initials="ABCD"),
                         "QR payload initials must be 3 characters or fewer")
        self.assertEqual(self.refusal(machineId=""), "QR payload is missing machineId")

    def test_a_refused_card_joins_nobody(self) -> None:
        response = self.client.post("/players/guests/card", json={"card": json.dumps(
            {"type": "vpinplay_identity", "version": 2, "userId": "v", "initials": "ABC",
             "machineId": KEY})})

        self.assertEqual(response.status_code, 400)
        self.assertEqual([one.player_id for one in players.get_roster().players()],
                         [self.owner])


class TheOwnersAccount(VPinPlayCase):
    """Made once from the extension's own settings, where a user id is set."""

    def settings(self, **values: str) -> None:
        for key, value in values.items():
            self.store.set_setting(NAME, key, value)

    def test_it_is_made_from_the_user_id_and_machine_id(self) -> None:
        self.settings(user_id="jordan", machine_id=KEY, initials="XYZ")
        owner = self.make_owner()

        self.load()

        self.assertEqual(self.held(owner), {"user_id": "jordan", "key": KEY})
        self.assertEqual(players.get_roster().player_state(owner)["initials"], "OWN")

    def test_without_a_user_id_nothing_is_made(self) -> None:
        self.settings(machine_id=KEY)
        owner = self.make_owner()

        self.load()

        self.assertEqual((self.held(owner), self.store.accounts(NAME)), ({}, {}))
        self.assertNotIn("owner_account_made", self.store.settings(NAME))

    def test_it_is_made_once(self) -> None:
        self.settings(user_id="jordan", machine_id=KEY)
        owner = self.make_owner()
        self.load()
        self.store.set_account(NAME, owner, {})
        self.registry.clear()

        self.load()

        self.assertEqual(self.held(owner), {})

    def test_an_owner_made_after_the_extension_loads_gets_it(self) -> None:
        """A first start: core makes the owner after the extensions have loaded."""
        self.settings(user_id="jordan", machine_id=KEY)
        self.load()

        owner = self.make_owner()

        self.assertEqual(self.held(owner), {"user_id": "jordan", "key": KEY})

    def test_an_owner_already_holding_one_keeps_it(self) -> None:
        self.settings(user_id="jordan", machine_id=KEY)
        owner = self.make_owner()
        self.store.set_account(NAME, owner, {"user_id": "theirs", "key": "k" * 64})

        self.load()

        self.assertEqual(self.held(owner), {"user_id": "theirs", "key": "k" * 64})


class TheSettings(VPinPlayCase):
    def setUp(self) -> None:
        super().setUp()
        self.make_owner()

    def test_the_settings_page_is_the_server_alone(self) -> None:
        self.load()

        found = self.ok(self.client.get(f"/ext/{NAME}/settings"))

        self.assertEqual([one["key"] for one in found["fields"]], ["endpoint"])
        self.assertEqual(found["fields"][0]["label"], "Server")
        self.assertNotIn("help", found)

    def test_a_setting_that_left_is_not_written(self) -> None:
        self.load()

        written = self.ok(self.client.put(f"/ext/{NAME}/settings", json={"values": {
            "endpoint": "https://mine.example", "user_id": "jordan",
            "sync_on_exit": True}}))

        self.assertEqual([one["value"] for one in written["fields"]],
                         ["https://mine.example"])
        held = self.store.settings(NAME)
        self.assertEqual(held["endpoint"], "https://mine.example")
        self.assertNotIn("user_id", held)
        self.assertNotIn("sync_on_exit", held)

    def test_the_values_that_left_are_still_held(self) -> None:
        self.store.set_setting(NAME, "sync_on_exit", "true")
        self.store.set_setting(NAME, "initials", "XYZ")

        self.load()

        held = self.store.settings(NAME)
        self.assertEqual((held["sync_on_exit"], held["initials"]), ("true", "XYZ"))

    def test_the_extension_reads_the_players(self) -> None:
        manifest = json.loads((host.BUNDLED_DIR / NAME / "extension.json").read_text("utf-8"))

        self.assertIn("players:read", manifest["scopes"])
        self.assertEqual(t(f"ext.{NAME}.account.consent.plays"),
                         "the games they play from now on, when and how long")


if __name__ == "__main__":
    unittest.main()
