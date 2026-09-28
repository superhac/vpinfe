"""What a player other than the owner has done with each game.

Each test has a roster and a records directory of its own. A new `PlayerRecords` on the
same directory is what a restart looks like: a kept player's record comes back, a
guest's does not.
"""

from __future__ import annotations

import json
import unittest
from configparser import ConfigParser
from pathlib import Path
from tempfile import TemporaryDirectory

from common import players, service_errors
from common.games.player_records import PlayerRecords, best_of
from common.i18n import t

AT = "2026-09-28T20:00:00Z"
LATER = "2026-09-28T21:00:00Z"


def _entry(initials: str, score: int | None, section: str = "HIGH SCORES",
           rank: int | None = 1, **extra) -> dict:
    return {"section": section, "rank": rank, "initials": initials, "score": score,
            "value_prefix": None, "value_suffix": None, "value_format": None,
            "extra_lines": [], "multiline": False, **extra}


class _RecordsCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "player_records"
        players.reset_for_tests(Path(tmp.name) / "players.json")
        self.addCleanup(players.reset_for_tests)
        self.roster = players.get_roster()
        owner = self.roster.ensure_owner(ConfigParser())
        assert owner is not None
        self.owner = owner
        self.kept = self.roster.add_player("Jordan", "ABC")
        self.guest = self.roster.add_guest("GST")
        self.records = PlayerRecords(self.root)

    def _file(self, player: players.Player) -> dict:
        return json.loads((self.root / f"{player.player_id}.json").read_text("utf-8"))

    def _restart(self) -> PlayerRecords:
        self.records = PlayerRecords(self.root)
        return self.records


class KeptPlayerTests(_RecordsCase):
    def test_a_game_counts_its_start_and_its_time(self) -> None:
        self.records.count_start(self.kept, "g1", AT)
        self.records.add_time(self.kept, "g1", 90.4)
        self.records.count_start(self.kept, "g1", LATER)
        self.records.add_time(self.kept, "g1", 30)

        self.assertEqual(self.records.game(self.kept, "g1"),
                         {"play_count": 2, "play_time_seconds": 120,
                          "last_played": LATER, "best_score": None, "rating": 0})

    def test_it_is_filed_under_their_id_and_survives_a_restart(self) -> None:
        self.records.count_start(self.kept, "g1", AT)
        self.records.set_rating(self.kept, "g1", 4)

        on_disk = self._file(self.kept)
        self.assertEqual((on_disk["schema"], on_disk["player"]), (1, self.kept.player_id))
        self.assertEqual(self._restart().game(self.kept, "g1")["rating"], 4)
        self.assertEqual(self.records.game(self.kept, "g1")["play_count"], 1)

    def test_removing_the_player_removes_the_file(self) -> None:
        self.records.count_start(self.kept, "g1", AT)

        self.records.forget(self.kept.player_id)

        self.assertFalse((self.root / f"{self.kept.player_id}.json").exists())
        self.assertEqual(self.records.games(self.kept), {})

    def test_a_game_that_ends_after_its_player_left_does_not_write_them_back(self) -> None:
        self.records.count_start(self.kept, "g1", AT)
        self.roster.remove(self.kept.player_id)
        self.records.forget(self.kept.player_id)

        with self.assertRaises(service_errors.NotFoundError):
            self.records.add_time(self.kept, "g1", 60)

        self.assertFalse((self.root / f"{self.kept.player_id}.json").exists())

    def test_an_id_that_is_not_a_file_name_is_refused_rather_than_followed(self) -> None:
        roster_file = self.roster.path
        held = json.loads(roster_file.read_text(encoding="utf-8"))
        held["players"].append({"id": "../outside", "name": "", "initials": "XYZ",
                                "owner": False})
        roster_file.write_text(json.dumps(held), encoding="utf-8")
        edited = self.roster.player("../outside")

        with self.assertRaises(service_errors.RefusedError):
            self.records.set_rating(edited, "g1", 3)

        self.assertFalse((self.root.parent / "outside.json").exists())

    def test_what_a_newer_build_filed_is_carried_through(self) -> None:
        self.root.mkdir(parents=True)
        (self.root / f"{self.kept.player_id}.json").write_text(json.dumps(
            {"schema": 2, "player": self.kept.player_id, "badges": ["first"],
             "games": {"g1": {"play_count": 1, "streak": 3}}}), encoding="utf-8")

        self.records.add_time(self.kept, "g1", 10)

        on_disk = self._file(self.kept)
        self.assertEqual((on_disk["schema"], on_disk["badges"]), (2, ["first"]))
        self.assertEqual(on_disk["games"]["g1"]["streak"], 3)
        self.assertEqual(on_disk["games"]["g1"]["play_count"], 1)


class GuestTests(_RecordsCase):
    def test_a_guest_s_record_is_the_same_shape_and_never_written(self) -> None:
        self.records.count_start(self.guest, "g1", AT)
        self.records.add_time(self.guest, "g1", 60)

        self.assertEqual(self.records.game(self.guest, "g1")["play_count"], 1)
        self.assertFalse(self.root.exists())

    def test_it_is_gone_once_they_sign_out(self) -> None:
        self.records.set_rating(self.guest, "g1", 5)

        self.records.forget(self.guest.player_id)

        self.assertEqual(self.records.games(self.guest), {})

    def test_it_is_gone_once_vpinfe_closes(self) -> None:
        self.records.set_rating(self.guest, "g1", 5)

        self.assertEqual(self._restart().games(self.guest), {})


class OwnerTests(_RecordsCase):
    def test_the_owner_s_record_is_the_library_s_and_is_refused_here(self) -> None:
        for write in (lambda: self.records.set_rating(self.owner, "g1", 3),
                      lambda: self.records.count_start(self.owner, "g1", AT),
                      lambda: self.records.games(self.owner)):
            with self.subTest(), self.assertRaises(service_errors.RefusedError) as refused:
                write()
            self.assertEqual(str(refused.exception),
                             t("error.players.owner_record_is_the_library"))

        self.assertFalse(self.root.exists())


class RatingTests(_RecordsCase):
    def test_a_rating_is_held_to_the_library_s_scale(self) -> None:
        self.assertEqual(self.records.set_rating(self.kept, "g1", 9), 5)
        self.assertEqual(self.records.set_rating(self.kept, "g1", "x"), 0)

    def test_taking_back_the_only_thing_said_about_a_game_leaves_nothing(self) -> None:
        self.records.set_rating(self.kept, "g1", 4)

        self.records.set_rating(self.kept, "g1", 0)

        self.assertEqual(self.records.games(self.kept), {})


class BestScoreTests(_RecordsCase):
    def test_the_highest_number_is_kept_with_where_and_when(self) -> None:
        self.records.offer_scores(self.kept, "g1", "rom1",
                                  [_entry("ABC", 200, rank=3), _entry("ABC", 500)], AT)

        best = self.records.game(self.kept, "g1")["best_score"]
        self.assertEqual((best["score"], best["rom"], best["scored_at"]), (500, "rom1", AT))

    def test_a_lower_score_later_leaves_the_best_alone(self) -> None:
        self.records.offer_scores(self.kept, "g1", "rom1", [_entry("ABC", 500)], AT)
        self.records.offer_scores(self.kept, "g1", "rom1", [_entry("ABC", 300)], LATER)

        self.assertEqual(self.records.game(self.kept, "g1")["best_score"]["scored_at"], AT)

    def test_an_equal_score_later_does_not_replace_the_first(self) -> None:
        held = _entry("ABC", 500, scored_at=AT)

        self.assertIs(best_of(held, [_entry("ABC", 500, scored_at=LATER)]), held)

    def test_an_entry_holding_no_number_is_kept_only_until_one_does(self) -> None:
        lap = _entry("ABC", None, section="FASTEST LAP", extra_lines=["0:42"])

        held = best_of(None, [lap])
        self.assertIs(held, lap)
        self.assertIs(best_of(held, [lap]), lap)
        self.assertEqual(best_of(held, [_entry("ABC", 10)])["score"], 10)
        self.assertEqual(best_of(_entry("ABC", 10), [lap])["score"], 10)


class ViewTests(_RecordsCase):
    def test_most_recently_played_first_then_the_games_only_rated(self) -> None:
        self.records.set_rating(self.kept, "rated", 3)
        self.records.count_start(self.kept, "older", AT)
        self.records.count_start(self.kept, "newer", LATER)
        self.records.offer_scores(self.kept, "newer", "rom1", [_entry("ABC", 1234)], LATER)

        view = self.records.view(self.kept)

        self.assertEqual(view["player"], self.kept.player_id)
        self.assertEqual([game["game_id"] for game in view["games"]],
                         ["newer", "older", "rated"])
        self.assertEqual(view["games"][0]["best_score"],
                         {"rom": "rom1", "section": "HIGH SCORES", "scored_at": LATER,
                          "rank": 1, "initials": "ABC", "score": 1234, "prefix": "",
                          "suffix": "", "text": "1,234"})


if __name__ == "__main__":
    unittest.main()
