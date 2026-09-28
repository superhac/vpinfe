"""A player's account with an extension, over core's routes, driven through the sample
fixture: read, written, acted on, shared, carded, and never answering with a secret."""

from __future__ import annotations

import json
import tempfile
import unittest
from configparser import ConfigParser
from pathlib import Path

from fastapi import FastAPI
from starlette.testclient import TestClient

import httpapi
from common import extensions, players, service_errors
from common.extensions import accounts, cards, host, store
from common.extensions.context import ContractError, ExtensionPlayers, ExtensionUI
from common.games import player_records
from common.i18n import t
from httpapi import events as event_stream

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "extensions"
TOKEN = "tok-" + "Zq9" * 20


def _owner_config() -> ConfigParser:
    parser = ConfigParser()
    parser.add_section("vpinplay")
    parser.set("vpinplay", "initials", "OWN")
    return parser


class AccountsCase(unittest.TestCase):
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
        owner = players.get_roster().ensure_owner(_owner_config())
        assert owner is not None
        self.owner = owner.player_id
        self.registry.load_from(FIXTURES)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        self.addCleanup(event_stream.reset)

    def ok(self, response, status: int = 200) -> dict:
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def account(self, player_id: str) -> dict:
        return self.ok(self.client.get(f"/players/{player_id}/accounts/sample"))

    def fill(self, player_id: str, **values: str) -> dict:
        return self.ok(self.client.put(f"/players/{player_id}/accounts/sample",
                                       json={"values": values}))

    def file(self) -> dict:
        path = self.root / "extension_settings" / "sample.json"
        return json.loads(path.read_text("utf-8")) if path.exists() else {}

    def secrets_answered(self, answer: object) -> list[str]:
        """Every place the token appears in an answer, as text."""
        return [TOKEN] * json.dumps(answer).count(TOKEN)


class ReadingAccounts(AccountsCase):
    def test_a_player_is_offered_an_account_with_each_extension_that_holds_them(self) -> None:
        found = self.ok(self.client.get(f"/players/{self.owner}/accounts"))["accounts"]

        self.assertEqual([one["extension"] for one in found], ["sample"])
        self.assertEqual((found[0]["label"], found[0]["status"], found[0]["acts"]),
                         ("Sample", "No handle",
                          [{"key": "ping", "label": "Ping", "description": ""}]))

    def test_an_empty_account_says_its_secret_is_not_set(self) -> None:
        token = next(one for one in self.account(self.owner)["fields"]
                     if one["key"] == "token")

        self.assertEqual(token, {"key": "token", "label": "Token", "type": "secret",
                                 "set": False})

    def test_the_listing_names_what_an_extension_offers(self) -> None:
        listed = self.ok(self.client.get("/extensions"))["extensions"]

        self.assertEqual(next(one for one in listed if one["name"] == "sample")["account"],
                         {"base": "/accounts", "label": "Sample", "cards": ["sample_card"],
                          "marker": "sample"})

    def test_an_extension_that_holds_no_accounts_is_a_404(self) -> None:
        response = self.client.get(f"/players/{self.owner}/accounts/bystander")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["message"],
                         t("error.players.no_accounts_in", extension="bystander"))

    def test_a_player_nobody_has_is_a_404(self) -> None:
        self.assertEqual(self.client.get("/players/Nobody0000/accounts").status_code, 404)

    def test_an_extension_switched_off_offers_no_account(self) -> None:
        self.registry.switch("sample", False)

        found = self.ok(self.client.get(f"/players/{self.owner}/accounts"))["accounts"]

        self.assertEqual(found, [])


class WritingAccounts(AccountsCase):
    def test_values_written_are_read_back_and_kept_in_the_extensions_own_file(self) -> None:
        answered = self.fill(self.owner, handle="own-handle", token=TOKEN)

        self.assertEqual(answered["status"], "Ready")
        self.assertEqual(self.file()["accounts"][self.owner],
                         {"handle": "own-handle", "token": TOKEN})

    def test_accounts_are_not_read_as_settings(self) -> None:
        self.fill(self.owner, handle="own-handle")

        self.assertNotIn("accounts", self.store.settings("sample"))

    def test_a_guests_account_is_held_in_memory_and_never_written(self) -> None:
        guest = players.get_roster().add_guest("ABC").player_id

        self.fill(guest, handle="their-handle", token=TOKEN)

        self.assertEqual(self.account(guest)["status"], "Ready")
        self.assertNotIn(TOKEN, json.dumps(self.file()))

    def test_an_act_answers_what_came_of_it(self) -> None:
        self.fill(self.owner, handle="own-handle")

        said = self.ok(self.client.post(f"/players/{self.owner}/accounts/sample/acts/ping"))

        self.assertEqual(said, {"message": "Pinged own-handle"})

    def test_an_act_the_extension_does_not_have_is_its_404(self) -> None:
        response = self.client.post(f"/players/{self.owner}/accounts/sample/acts/dance")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["message"], "No such act")

    def test_removing_a_player_forgets_their_accounts(self) -> None:
        kept = players.get_roster().add_player("Jordan", "JOR").player_id
        self.fill(kept, handle="their-handle", token=TOKEN)

        self.assertEqual(self.client.delete(f"/players/{kept}").status_code, 204)

        self.assertNotIn(kept, self.file().get("accounts", {}))

    def test_a_guest_signing_out_takes_their_account_with_them(self) -> None:
        guest = players.get_roster().add_guest("ABC").player_id
        self.fill(guest, handle="their-handle", token=TOKEN)

        self.client.delete(f"/players/{guest}")

        self.assertEqual(accounts.holders("sample", self.store), [])


class UnderTheMount(AccountsCase):
    """Served the way the app serves it, under /api/v1, where the extension's route is
    asked for at a path of its own under that prefix."""

    def test_an_account_is_asked_for_under_the_prefix(self) -> None:
        outer = FastAPI()
        outer.mount(httpapi.API_PREFIX, httpapi.create_api_app())
        client = TestClient(outer, raise_server_exceptions=False)
        where = f"{httpapi.API_PREFIX}/players/{self.owner}/accounts/sample"

        written = client.put(where, json={"values": {"handle": "h", "token": TOKEN}})
        read = client.get(where)

        self.assertEqual((written.status_code, read.status_code), (200, 200), read.text)
        self.assertEqual((read.json()["status"], self.secrets_answered(read.json())),
                         ("Ready", []))


class Sharing(AccountsCase):
    def test_an_account_does_not_share_until_somebody_says_so(self) -> None:
        self.assertFalse(self.account(self.owner)["share"])

    def test_share_is_kept_per_player_in_the_roster(self) -> None:
        said = self.ok(self.client.put(f"/players/{self.owner}/accounts/sample/share",
                                       json={"share": True}))

        self.assertTrue(said["share"])
        saved = json.loads((self.root / "players.json").read_text("utf-8"))
        self.assertEqual(saved["players"][0]["share"], {"sample": True})

    def test_share_goes_off_again(self) -> None:
        where = f"/players/{self.owner}/accounts/sample/share"
        self.client.put(where, json={"share": True})

        self.assertFalse(self.ok(self.client.put(where, json={"share": False}))["share"])


class Cards(AccountsCase):
    def card_of(self, player_id: str) -> str:
        response = self.client.get(f"/players/{player_id}/accounts/sample/card")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "image/svg+xml")
        return response.text

    def join(self, card: str, status: int = 201) -> dict:
        return self.ok(self.client.post("/players/guests/card", json={"card": card}), status)

    def test_a_card_is_the_accounts_text_drawn_under_the_extensions_name(self) -> None:
        self.fill(self.owner, handle="own-handle", token=TOKEN)

        drawn = self.card_of(self.owner)

        self.assertIn("<!--SAMPLE_PAYLOAD:", drawn)
        self.assertEqual(cards.read(drawn), {"type": "sample_card", "version": 1,
                                             "handle": "own-handle", "token": TOKEN,
                                             "initials": "OWN"})

    def test_a_card_is_saved_under_the_name_the_extension_gives(self) -> None:
        self.fill(self.owner, handle="own handle", token=TOKEN)

        response = self.client.get(f"/players/{self.owner}/accounts/sample/card")

        self.assertEqual(response.headers["content-disposition"],
                         'attachment; filename="sample-own_handle.svg"')

    def test_an_account_with_nothing_to_card_says_so(self) -> None:
        response = self.client.get(f"/players/{self.owner}/accounts/sample/card")

        self.assertEqual(response.status_code, 404)

    def test_a_card_made_here_joins_as_a_guest_holding_that_account(self) -> None:
        self.fill(self.owner, handle="own-handle", token=TOKEN)
        drawn = self.card_of(self.owner)

        guest = self.join(drawn)

        self.assertEqual((guest["guest"], guest["up"], guest["initials"]),
                         (True, True, "OWN"))
        self.assertEqual(accounts.values("sample", guest["id"]),
                         {"handle": "own-handle", "token": TOKEN})
        self.assertEqual(cards.read(self.card_of(guest["id"])), cards.read(drawn))

    def test_a_guest_who_joins_with_a_card_shares(self) -> None:
        guest = self.join(json.dumps({"type": "sample_card", "version": 1,
                                      "handle": "h", "token": TOKEN, "initials": "ABC"}))

        self.assertTrue(self.account(guest["id"])["share"])

    def test_a_cards_initials_are_taken_as_they_are(self) -> None:
        guest = self.join(json.dumps({"type": "sample_card", "version": 1, "handle": "h",
                                      "token": TOKEN, "initials": "ab"}))

        self.assertEqual(guest["initials"], "AB")

    def test_initials_longer_than_three_are_refused(self) -> None:
        response = self.client.post("/players/guests/card", json={"card": json.dumps(
            {"type": "sample_card", "version": 1, "handle": "h", "token": TOKEN,
             "initials": "ABCD"})})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["message"],
                         t("error.players.card_initials"))

    def test_the_same_card_again_puts_that_guest_up_rather_than_adding_another(self) -> None:
        card = json.dumps({"type": "sample_card", "version": 1, "handle": "h",
                           "token": TOKEN, "initials": "ABC"})
        first = self.join(card)["id"]
        players.get_roster().set_who_is_up([self.owner])

        again = self.join(card)

        self.assertEqual(again["id"], first)
        self.assertEqual([one.player_id for one in players.get_roster().up()], [first])
        self.assertEqual(len([one for one in players.get_roster().players() if one.guest]), 1)

    def test_a_card_nothing_here_reads_is_refused(self) -> None:
        response = self.client.post("/players/guests/card",
                                    json={"card": '{"type": "elsewhere_card"}'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["message"],
                         t("error.players.card_unclaimed"))

    def test_a_card_the_extension_will_not_read_is_its_refusal(self) -> None:
        response = self.client.post("/players/guests/card", json={
            "card": '{"type": "sample_card", "version": 9}'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["message"], "Not a card this reads")

    def test_a_file_that_is_not_a_card_is_refused(self) -> None:
        response = self.client.post("/players/guests/card", json={"card": "<svg></svg>"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["message"],
                         t("error.players.card_unreadable"))


class SecretsNeverLeave(AccountsCase):
    """Accepted on a write, answered as set or not set, by every route."""

    def test_no_account_route_answers_with_a_secret(self) -> None:
        answers = [
            self.fill(self.owner, handle="own-handle", token=TOKEN),
            self.account(self.owner),
            self.ok(self.client.get(f"/players/{self.owner}/accounts")),
            self.ok(self.client.put(f"/players/{self.owner}/accounts/sample/share",
                                    json={"share": True})),
            self.ok(self.client.post(f"/players/{self.owner}/accounts/sample/acts/ping")),
            self.ok(self.client.get(f"/ext/sample/accounts/{self.owner}")),
            self.ok(self.client.put(f"/ext/sample/accounts/{self.owner}",
                                    json={"values": {}})),
        ]

        self.assertEqual([one for answer in answers for one in self.secrets_answered(answer)],
                         [])

    def test_a_secret_reads_back_as_set(self) -> None:
        self.fill(self.owner, token=TOKEN)

        token = next(one for one in self.account(self.owner)["fields"]
                     if one["key"] == "token")

        self.assertEqual((token["set"], "value" in token), (True, False))

    def test_a_secret_setting_is_never_answered_either(self) -> None:
        written = self.ok(self.client.put("/ext/sample/settings",
                                          json={"values": {"token": TOKEN}}))
        read = self.ok(self.client.get("/ext/sample/settings"))

        self.assertEqual(self.secrets_answered([written, read]), [])
        self.assertEqual(self.store.settings("sample")["token"], TOKEN)
        self.assertEqual(next(one for one in read["fields"] if one["key"] == "token")["set"],
                         True)


class TheDeclaration(unittest.TestCase):
    def setUp(self) -> None:
        self.ui = ExtensionUI("site", allowed=True)

    def test_an_account_is_recorded_as_data(self) -> None:
        self.ui.account("/accounts", cards=["site_card"])

        self.assertEqual(self.ui.account_offered, {"base": "/accounts", "label": "",
                                                   "cards": ["site_card"],
                                                   "marker": "site"})

    def test_an_account_needs_ui_mount(self) -> None:
        with self.assertRaises(ContractError):
            ExtensionUI("site", allowed=False).account("/accounts")

    def test_a_player_holds_one_account_with_an_extension(self) -> None:
        self.ui.account("/accounts")

        with self.assertRaises(ContractError):
            self.ui.account("/others")

    def test_a_marker_that_is_not_a_plain_name_is_refused(self) -> None:
        """It becomes part of a comment and two element ids in the card."""
        with self.assertRaises(ContractError):
            self.ui.account("/accounts", marker="x--><script")

    def test_a_card_with_no_kind_is_refused(self) -> None:
        with self.assertRaises(ContractError):
            self.ui.account("/accounts", cards=[""])


class WhatAnExtensionSees(AccountsCase):
    def players_of(self, *scopes: str) -> ExtensionPlayers:
        return ExtensionPlayers("sample", scopes, self.store)

    def test_the_roster_needs_players_read(self) -> None:
        with self.assertRaises(ContractError):
            self.players_of().roster()

    def test_the_roster_is_the_rows_players_changed_carries(self) -> None:
        guest = players.get_roster().add_guest("ABC").player_id
        seen = self.players_of("players:read")

        self.assertEqual(seen.roster(), players.get_roster().state()["players"])
        self.assertEqual([one["id"] for one in seen.up()], [guest])
        self.assertEqual(seen.get(guest)["initials"], "ABC")

    def test_a_player_s_record_of_a_game_needs_players_read(self) -> None:
        with self.assertRaises(ContractError):
            self.players_of().record(self.owner, "g1")

    def test_a_player_s_record_of_a_game_is_their_own(self) -> None:
        records = self.records()
        kept = players.get_roster().add_player("Jordan", "ABC")
        records.count_start(kept, "g1", "2026-09-28T20:00:00Z")
        records.set_rating(kept, "g1", 4)

        found = self.players_of("players:read").record(kept.player_id, "g1")

        self.assertEqual((found["play_count"], found["rating"], found["last_played"]),
                         (1, 4, "2026-09-28T20:00:00Z"))
        self.assertEqual(found, records.shown(kept, "g1"))

    def test_the_owner_s_record_is_the_library_s_and_nobody_s_is_nothing(self) -> None:
        self.records()
        seen = self.players_of("players:read")

        self.assertIsNone(seen.record(self.owner, "g1"))
        self.assertIsNone(seen.record("Nobody0000", "g1"))

    def records(self) -> player_records.PlayerRecords:
        player_records.reset_for_tests(self.root / "player_records")
        self.addCleanup(player_records.reset_for_tests)
        return player_records.get_records()

    def test_its_own_accounts_need_nothing_declared(self) -> None:
        seen = self.players_of()
        seen.set_account(self.owner, {"handle": "h"})

        self.assertEqual((seen.account(self.owner), seen.holders(), seen.sharing(self.owner)),
                         ({"handle": "h"}, [self.owner], False))

    def test_an_account_for_somebody_nobody_has_is_refused(self) -> None:
        with self.assertRaises(service_errors.NotFoundError):
            self.players_of().set_account("Nobody0000", {"handle": "h"})


class TheStore(AccountsCase):
    def test_accounts_is_not_a_name_a_setting_can_take(self) -> None:
        self.store.set_account("sample", self.owner, {"handle": "h"})
        with self.assertLogs("vpinfe.common.extensions.store", level="ERROR"):
            self.store.set_setting("sample", "accounts", "flattened")

        self.assertEqual(self.store.accounts("sample"), {self.owner: {"handle": "h"}})

    def test_forgetting_a_player_reaches_every_extension_holding_them(self) -> None:
        for name in ("sample", "bystander"):
            self.store.set_account(name, self.owner, {"handle": "h"})
        self.store.set_account("sample", "Other00000", {"handle": "o"})

        self.assertEqual(self.store.forget_holder(self.owner), ["bystander", "sample"])
        self.assertEqual((self.store.accounts("sample"), self.store.accounts("bystander")),
                         ({"Other00000": {"handle": "o"}}, {}))


if __name__ == "__main__":
    unittest.main()
