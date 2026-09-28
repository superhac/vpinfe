"""Frontend › Players: what each row and the panel say, which acts a player is offered, and
where the page sits and is addressed."""

from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import patch

import requests

from common import install_identity
from common.i18n import t
from console import deeplink, page, players, workbench
from console.api import ApiClient

OWNER = {"id": "p-own", "name": "", "initials": "OWN", "owner": True, "guest": False,
         "up": True, "shares_initials_with": []}


def _player(player_id: str, **more: Any) -> dict[str, Any]:
    return {"id": player_id, "name": "", "initials": "", "owner": False, "guest": False,
            "up": False, "shares_initials_with": [], **more}


class TheRows(unittest.TestCase):
    def test_a_household_of_one_shows_no_up(self) -> None:
        self.assertEqual([row["up"] for row in players.rows([OWNER])], [False])

    def test_up_is_marked_once_someone_else_plays_here(self) -> None:
        made = players.rows([OWNER, _player("p-jor", name="Jordan", initials="ABC")])
        self.assertEqual([row["up"] for row in made], [True, False])

    def test_chips_mark_the_owner_and_guests_and_nobody_else(self) -> None:
        made = players.rows([OWNER, _player("p-jor", name="Jordan"),
                             _player("p-vis", initials="XYZ", guest=True)])
        self.assertEqual([row["kind"] for row in made],
                         [players.OWNER, "", players.GUEST])

    def test_a_name_falls_back_to_initials_and_then_says_there_is_none(self) -> None:
        self.assertEqual([players.shown_name(one) for one in (
            _player("a", name=" Jordan "), _player("b", initials="XYZ"), _player("c"))],
            ["Jordan", "XYZ", t("console.players.no_name")])

    def test_shared_initials_name_the_other_player_on_both_rows(self) -> None:
        kept = _player("p-jor", name="Jordan", initials="XYZ",
                       shares_initials_with=["p-vis"])
        guest = _player("p-vis", initials="XYZ", guest=True, up=True,
                        shares_initials_with=["p-jor"])
        made = players.rows([OWNER, kept, guest])
        self.assertEqual([row["shared"] for row in made], [
            "", t("console.players.same_initials_as", player="XYZ"),
            t("console.players.same_initials_as", player="Jordan")])

    def test_several_sharing_are_all_named(self) -> None:
        one = _player("a", initials="XYZ", shares_initials_with=["b", "c"])
        said = players.same_initials(one, [one, _player("b", name="Sam", initials="XYZ"),
                                           _player("c", initials="XYZ")])
        self.assertIn("Sam", said)
        self.assertIn("XYZ", said)

    def test_a_guest_row_counts_the_games_played_this_session(self) -> None:
        guest = _player("p-vis", initials="XYZ", guest=True, up=True)
        kept = _player("p-jor", name="Jordan")
        made = players.rows([OWNER, kept, guest], {"p-vis": 3, "p-jor": 5})
        self.assertEqual([row["session"] for row in made],
                         ["", "", t("console.players.games_this_session", count=3)])

    def test_a_guest_with_no_games_yet_says_nothing(self) -> None:
        guest = _player("p-vis", initials="XYZ", guest=True)
        self.assertEqual(players.rows([OWNER, guest], {"p-vis": 0})[1]["session"], "")

    def test_games_played_adds_every_game_s_plays(self) -> None:
        self.assertEqual(players.games_played([{"play_count": 2}, {"play_count": 1},
                                               {"rating": 4}]), 3)


class WhatCanBeDone(unittest.TestCase):
    def acts(self, player: dict[str, Any]) -> list:
        return players.acts(object(), {}, player, lambda: None)  # type: ignore[arg-type]

    def test_the_owner_s_remove_is_offered_and_refused_with_why(self) -> None:
        (verb,) = self.acts(OWNER)
        self.assertEqual((verb.label, verb.run, verb.danger, verb.hint),
                         (t("word.remove"), None, True,
                          t("error.players.owner_not_removable")))

    def test_a_kept_player_can_be_removed(self) -> None:
        (verb,) = self.acts(_player("p-jor", name="Jordan"))
        self.assertEqual(verb.label, t("word.remove"))
        self.assertIsNotNone(verb.run)

    def test_a_guest_signs_out(self) -> None:
        (verb,) = self.acts(_player("p-vis", guest=True))
        self.assertEqual((verb.label, verb.danger), (t("console.players.sign_out"), True))

    def test_removing_says_what_goes_and_offers_the_card_where_there_is_one(self) -> None:
        self.assertEqual(players.removal_detail(None), [t("console.players.remove_detail")])
        self.assertEqual(players.removal_detail({"extension": "vpinplay",
                                                 "label": "VPinPlay"}),
                         [t("console.players.remove_detail"),
                          t("console.players.remove_card_detail", service="VPinPlay")])


class ThePanel(unittest.TestCase):
    def test_the_header_says_what_the_player_is(self) -> None:
        self.assertEqual([players.kind_word(one) for one in (
            OWNER, _player("a"), _player("b", guest=True))],
            [t("console.players.owner"), t("console.players.player"),
             t("console.players.guest")])

    def test_a_player_s_rail_lands_on_details(self) -> None:
        self.assertEqual(workbench.chosen_section({}, "player"), "player_details")

    def test_the_owner_has_no_plays_section(self) -> None:
        plays = next(one for one in workbench.sections_for("player")
                     if one.key == "player_plays")
        assert plays.shown is not None
        self.assertEqual([plays.shown({"player": one}) for one in (
            OWNER, _player("a"), _player("b", guest=True))], [False, True, True])

    def test_an_account_is_a_section_named_for_its_service(self) -> None:
        key, label, _build = players.account_section(
            {"extension": "vpinplay", "label": "VPinPlay"})
        self.assertEqual((key, label({})), ("player_account_vpinplay", "VPinPlay"))

    def test_share_says_what_the_extension_says_it_does(self) -> None:
        self.assertEqual(players.share_help({"extension": "vpinplay", "label": "VPinPlay",
                                             "share_help": "Makes it public"}),
                         "Makes it public")

    def test_share_says_core_s_words_where_the_extension_says_none(self) -> None:
        self.assertEqual(players.share_help({"extension": "site", "label": "Site"}),
                         t("console.players.share.help", service="Site"))

    def test_a_card_is_saved_as_an_svg_named_for_the_service_and_the_user_id(self) -> None:
        self.assertEqual([players.card_filename(account) for account in (
            {"extension": "vpinplay", "user_id": "player-one"},
            {"extension": "vpinplay", "user_id": ""})],
            ["vpinplay-player-one.svg", "vpinplay-card.svg"])


class ThePlays(unittest.TestCase):
    def test_count_time_and_when_then_the_best_score(self) -> None:
        said = players.played_line({"play_count": 3, "play_time_seconds": 1500,
                                    "last_played": "2026-09-01T20:00:00+00:00",
                                    "best_score": {"score": 1234560, "text": "1,234,560",
                                                   "prefix": "", "suffix": ""}})
        self.assertTrue(said.startswith("3 plays · 25 min · "))
        self.assertTrue(said.endswith(" · Best 1,234,560"))

    def test_a_score_made_without_being_up_stands_alone(self) -> None:
        self.assertEqual(players.played_line({"play_count": 0, "best_score": {
            "score": 500, "text": "500", "prefix": "", "suffix": ""}}), "Best 500")

    def test_a_game_only_rated_is_not_a_play(self) -> None:
        self.assertEqual(players.played_line({"play_count": 0, "rating": 4,
                                              "best_score": None}), "")


class WhereItSits(unittest.TestCase):
    def test_players_leads_the_frontend(self) -> None:
        groups = dict(page.nav_for(install_identity.FEATURES))
        self.assertEqual([key for key, *_rest in groups[page.NAV_FRONTEND]][0], "players")

    def test_an_install_without_the_frontend_has_no_players(self) -> None:
        keys = [key for _parent, items in page.nav_for([install_identity.LIBRARY])
                for key, *_rest in items]
        self.assertNotIn("players", keys)

    def test_the_address_names_the_player_on_players_only(self) -> None:
        state = {"view": "players", "player": "p-jor", "launcher": "l-1"}
        self.assertEqual(deeplink.query(state), "view=players&player=p-jor")
        self.assertEqual(deeplink.query({**state, "view": "games"}), "view=games")

    def test_an_address_names_the_player_to_open(self) -> None:
        state: dict[str, Any] = {"view": "games"}
        deeplink.apply(state, {"view": "players", "player": " p-jor "},
                       views=["games", "players"], sections=[])
        self.assertEqual((state["view"], state["player"]), ("players", "p-jor"))

    def test_leaving_the_page_drops_the_player(self) -> None:
        state = {"view": "players", "player": "p-jor"}
        with patch.object(page.remembered, "put"):
            page.leave_for(state, "games")
        self.assertIsNone(state["player"])


class TheClient(unittest.TestCase):
    """Each call goes to the route that does it, with the id made safe for a path."""

    def asked(self, call: Any) -> tuple[str, str, Any]:
        seen: list[tuple[str, str, Any]] = []

        def answer(_session: Any, method: str, url: str, **kwargs: Any) -> Any:
            seen.append((method, url.split("/api/v1", 1)[1], kwargs.get("json")))
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps({"players": [], "accounts": [], "games": []}) \
                .encode()
            return response

        with patch.object(requests.Session, "request", answer):
            call(ApiClient("http://127.0.0.1:1"))
        return seen[0]

    def test_each_route(self) -> None:
        cases = [
            (lambda c: c.add_player("Jordan", "ABC"),
             ("POST", "/players", {"name": "Jordan", "initials": "ABC"})),
            (lambda c: c.add_guest("XYZ"), ("POST", "/players/guests", {"initials": "XYZ"})),
            (lambda c: c.add_guest_from_card("{}"),
             ("POST", "/players/guests/card", {"card": "{}"})),
            (lambda c: c.change_player("a/b", initials="XYZ"),
             ("PATCH", "/players/a%2Fb", {"initials": "XYZ"})),
            (lambda c: c.remove_player("p-1"), ("DELETE", "/players/p-1", None)),
            (lambda c: c.set_player_up("p-1", True), ("PUT", "/players/p-1/up", {"up": True})),
            (lambda c: c.put_account("p-1", "vpinplay", {"user_id": "u"}),
             ("PUT", "/players/p-1/accounts/vpinplay", {"values": {"user_id": "u"}})),
            (lambda c: c.put_share("p-1", "vpinplay", False),
             ("PUT", "/players/p-1/accounts/vpinplay/share", {"share": False})),
            (lambda c: c.use_card("p-1", "vpinplay", "{}"),
             ("POST", "/players/p-1/accounts/vpinplay/card", {"card": "{}"})),
            (lambda c: c.account_act("p-1", "vpinplay", "claim"),
             ("POST", "/players/p-1/accounts/vpinplay/acts/claim", {})),
            (lambda c: c.player_card("p-1", "vpinplay"),
             ("GET", "/players/p-1/accounts/vpinplay/card", None)),
            (lambda c: c.account_available("vpinplay", "/available", "jordan"),
             ("GET", "/ext/vpinplay/available?candidate=jordan", None)),
        ]
        for call, wanted in cases:
            with self.subTest(wanted[1]):
                self.assertEqual(self.asked(call), wanted)


if __name__ == "__main__":
    unittest.main()
