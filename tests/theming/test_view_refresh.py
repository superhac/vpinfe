"""Re-deriving the wheel's view after something changed the library underneath it.

A view is a membership and an order over game objects, and all three go stale from
outside: a finished session moves a game up a LastRun wheel and into Last Played, and a
Manager UI edit replaces the game object rather than mutating the one the view holds.
Rebuilding only the payload leaves every one of those showing what it showed at boot.
"""

from __future__ import annotations

import types
import unittest
from unittest import mock

from frontend import game_state


def _game(name, last_run=0):
    return types.SimpleNamespace(
        gameDirName=name,
        fullPathGame=f"/games/{name}",
        meta_config={"Info": {"Title": name}, "User": {"LastRun": last_run}},
    )


class _View:
    """Just the part `refresh_view` reaches for: where the library comes from. A player's
    is a hub, so asking the view is what keeps the two answers from diverging."""

    def __init__(self, games):
        self.all_games = list(games)

    def reload(self):
        return self.all_games


class _Api:
    """The parts of the frontend API a view is derived from."""

    def __init__(self, games, sort="Alpha", order="Ascending", collection=None):
        self.view = _View(games)
        self.allGames = list(games)
        self.filteredGames = list(games)
        self.current_filters = game_state.default_filter_state()
        self.current_collection = collection
        self.current_sort = sort
        self.current_order = order
        self.rebuilds = 0

    def _rebuild_entries(self):
        self.rebuilds += 1


class ViewRefreshTests(unittest.TestCase):
    def _refresh(self, api, library):
        # The view is what reads the library now, so that is what a test stands up:
        # `refresh_view` asks it rather than loading a second time behind its back.
        api.view.all_games = list(library)
        game_state.refresh_view(api)

    def test_the_view_picks_up_the_replacement_game_object(self):
        """refresh_game swaps the object out. A view holding the old one never sees the
        edit, however many times it rebuilds its payload."""
        stale = _game("Alpha")
        api = _Api([stale])
        fresh = _game("Alpha")

        self._refresh(api, [fresh])

        self.assertIs(api.allGames[0], fresh)
        self.assertIs(api.filteredGames[0], fresh)

    def test_a_play_axis_reorders_the_wheel(self):
        library = [_game("Alpha", last_run=10), _game("Bravo", last_run=20)]
        api = _Api(library, sort="LastRun", order="Descending")

        self._refresh(api, library)
        self.assertEqual([g.gameDirName for g in api.filteredGames], ["Bravo", "Alpha"])

        # Alpha was just played, which is the whole point of refreshing.
        library[0].meta_config["User"]["LastRun"] = 30
        self._refresh(api, library)

        self.assertEqual([g.gameDirName for g in api.filteredGames], ["Alpha", "Bravo"])

    def test_collection_membership_is_re_resolved(self):
        """Last Played gains the game at launch, and a view of it has to notice."""
        library = [_game("Alpha"), _game("Bravo")]
        api = _Api([library[0]], collection="Last Played")

        with mock.patch.object(game_state, "filter_games_by_collection",
                               return_value=(list(library), None)):
            self._refresh(api, library)

        self.assertEqual([g.gameDirName for g in api.filteredGames], ["Alpha", "Bravo"])

    def test_a_collection_does_not_reimpose_its_own_sort(self):
        """Choosing a collection applies its sort once. Sorting differently afterwards is
        the player's choice and outlives a refresh."""
        library = [_game("Alpha"), _game("Bravo")]
        api = _Api(library, sort="Alpha", order="Descending", collection="Favorites")

        with mock.patch.object(game_state, "filter_games_by_collection",
                               return_value=(list(library), {"sort_by": "LastRun",
                                                             "order_by": "Ascending"})):
            self._refresh(api, library)

        self.assertEqual(api.current_sort, "Alpha")
        self.assertEqual(api.current_order, "Descending")
        self.assertEqual([g.gameDirName for g in api.filteredGames], ["Bravo", "Alpha"])

    def test_the_filters_the_player_set_still_apply(self):
        library = [_game("Alpha"), _game("Bravo")]
        api = _Api(library)
        api.current_filters["letter"] = "B"

        self._refresh(api, library)

        self.assertEqual([g.gameDirName for g in api.filteredGames], ["Bravo"])

    def test_the_entries_are_rebuilt(self):
        """The entry list caches the table dict out of the meta, so a refresh that left
        it alone would keep reporting the old counters at contract 2."""
        api = _Api([_game("Alpha")])

        self._refresh(api, [_game("Alpha")])

        self.assertEqual(api.rebuilds, 1)


if __name__ == "__main__":
    unittest.main()
