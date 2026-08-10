"""One view, however many windows are showing it.

A cabinet opens three windows onto one library. They were three independent copies that
happened to agree - each re-read the library, re-sorted it, rebuilt its own entry list
and serialized its own payload. Only the controller window takes input, so only one of
them could ever change what they were all deriving.

What is asserted here is that they now share it: one derivation, one payload, and a
change made through any window visible from all of them.
"""

from __future__ import annotations

import configparser
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from frontend import game_state
from frontend import view as frontend_view
from frontend.api import API

NAMES = ["Bravo", "Alpha", "Charlie"]


def _game(title, created=0):
    return SimpleNamespace(
        meta_config={"Info": {"Title": title}, "User": {}},
        gameDirName=title, fullPathGame=f"/g/{title}",
        fullPathVPXfile=f"/g/{title}/{title}.vpx", creation_time=created,
        pupPackExists=False, altColorExists=False, altSoundExists=False)


def _ini():
    parser = configparser.ConfigParser()
    parser.add_section("general")
    parser.set("general", "startup_collection", "")
    return SimpleNamespace(config=parser, save=lambda: None)


class SharedViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.games = [_game(name, index) for index, name in enumerate(NAMES)]
        patcher = patch("frontend.api.ensure_games_loaded", return_value=self.games)
        patcher.start()
        self.addCleanup(patcher.stop)
        also = patch("frontend.view.ensure_games_loaded", return_value=self.games)
        also.start()
        self.addCleanup(also.stop)
        refresh = patch("frontend.game_state.ensure_games_loaded", return_value=self.games)
        refresh.start()
        self.addCleanup(refresh.stop)

        ini = _ini()
        self.view = frontend_view.View(ini, games=self.games)
        self.windows = {name: API(ini, window_name=name, view=self.view)
                        for name in ("playfield", "backglass", "scoreview")}

    def _counted_builds(self):
        """Count how many times the payload is actually serialized."""
        builds = []
        real = game_state.games_json

        def counting(*args, **kwargs):
            builds.append(1)
            return real(*args, **kwargs)

        return builds, patch.object(game_state, "games_json", counting)

    def test_every_window_steps_through_the_same_entries(self) -> None:
        playfield, backglass = self.windows["playfield"], self.windows["backglass"]

        self.assertIs(playfield.entries, backglass.entries)

    def test_the_payload_is_built_once_for_all_of_them(self) -> None:
        """Three windows asking at startup was three serializations of one answer."""
        builds, counting = self._counted_builds()

        with counting:
            payloads = [window.get_games() for window in self.windows.values()]

        self.assertEqual(len(builds), 1)
        self.assertEqual(len(set(payloads)), 1, "and they all got the same one")

    def test_a_change_from_one_window_is_what_the_others_see(self) -> None:
        """The controller sorts; the display windows are showing that sort, not a copy
        of it that happens to match."""
        before = self.windows["playfield"].get_games()

        self.windows["playfield"].apply_sort("Newest", "Descending")
        after = self.windows["playfield"].get_games()

        self.assertNotEqual(after, before)
        self.assertEqual(self.windows["backglass"].get_games(), after)
        self.assertEqual(self.windows["scoreview"].get_games(), after)

    def test_the_others_pay_nothing_to_see_it(self) -> None:
        self.windows["playfield"].apply_sort("Newest", "Descending")
        self.windows["playfield"].get_games()

        builds, counting = self._counted_builds()
        with counting:
            self.windows["backglass"].get_games()
            self.windows["scoreview"].get_games()

        self.assertEqual(builds, [])

    def test_a_stale_library_is_re_derived_once_not_once_per_window(self) -> None:
        """All three ask after the same GameDataChange, and the second and third were
        rebuilding what the first had just rebuilt."""
        for window in self.windows.values():
            window.get_games()

        self.view.mark_stale()
        refreshes = []
        with patch.object(game_state, "refresh_view",
                          side_effect=lambda api: refreshes.append(1)):
            for window in self.windows.values():
                window.get_games()

        self.assertEqual(len(refreshes), 1)

    def test_a_window_built_without_one_gets_its_own(self) -> None:
        """A gamepad diagnostic or a test builds an API on its own; it must not reach
        into a view meant for somebody else's windows."""
        solo = API(_ini(), window_name="gamepad")

        self.assertIsNot(solo.view, self.view)

    def test_a_bare_instance_still_works(self) -> None:
        """`API.__new__(API)` is how paging and input mapping are tested - no library
        behind it, and no view handed in."""
        bare = API.__new__(API)
        bare._iniConfig = _ini()
        bare.filteredGames = self.games

        self.assertEqual(len(bare.entries), len(self.games))


class ViewConcurrencyTests(unittest.TestCase):
    """One shared view makes two windows' calls genuinely concurrent, where three
    separate copies were accidentally safe."""

    def test_sorting_while_another_window_reads_does_not_tear(self) -> None:
        games = [_game(name, index) for index, name in enumerate(NAMES * 20)]
        with patch("frontend.view.ensure_games_loaded", return_value=games):
            view = frontend_view.View(_ini(), games=games)

        errors = []

        def sorter():
            for _ in range(40):
                try:
                    with view.lock:
                        game_state.apply_sort(view.filtered_games, "Newest", "Descending")
                        view.rebuild_entries()
                except Exception as exc:      # noqa: BLE001 - the assertion is the report
                    errors.append(exc)

        def reader():
            for _ in range(40):
                try:
                    self.assertEqual(len(view.entries), len(games))
                except Exception as exc:      # noqa: BLE001
                    errors.append(exc)

        threads = [threading.Thread(target=sorter), threading.Thread(target=reader)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
