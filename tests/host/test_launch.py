"""The one launch path, which the wheel, the Remote page and the API all take.

The behavior pinned here used to be split across two implementations that
disagreed - most visibly, only one of them recorded that a table had been played.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import types
import unittest
from unittest import mock

from common import events
from common.host import commands, launch, launch_state, table_commands


class _FakePopen:
    def __init__(self, lines=(), returncode=0):
        self.stdout = list(lines)
        self.waited = False
        # What the program exited with. A real Popen always has one, and a command set
        # to run after the table is told it.
        self.returncode = returncode

    def wait(self):
        self.waited = True
        return self.returncode


def _game(name="Example"):
    return types.SimpleNamespace(
        fullPathVPXfile=f"/games/{name}/{name}.vpx",
        fullPathGame=f"/games/{name}",
        gameDirName=name,
        meta_config={},
    )


def _launcher(bin_path: str = "/opt/vpx"):
    from common.games.launchers import Launcher

    return Launcher(launcher_id="l1", app="vpx", display_name="Visual Pinball X",
                    settings={"bin_path": bin_path})


class LaunchTests(unittest.TestCase):
    def setUp(self) -> None:
        events.clear()
        launch_state.clear()
        self.addCleanup(events.clear)
        self.addCleanup(launch_state.clear)

    def _run(self, popen=None, game=None, **overrides):
        """Launch with every collaborator stubbed, so only the orchestration runs.

        Nobody is signed in as a guest, and that needs no stub: with no extension
        answering, the seam says so on its own - which is also what an install without
        that extension looks like.
        """
        popen = popen or (lambda cmd, **kwargs: _FakePopen())
        patches = {
            "_binary_of": lambda launcher, asked_for: "/opt/vpx",
            "_plan": lambda table, binary, launcher: (
                ["/opt/vpx", "-play", "x.vpx"], "Startup done"),
            "parse_launch_env_overrides": lambda raw: {},
            "delete_vpinball_log_on_start_if_configured": lambda *a, **k: None,
        }
        patches.update(overrides)

        with mock.patch.object(launch, "game_play_service") as play, \
                mock.patch.object(launch, "_launcher_for",
                                  lambda game, vpx_path: (_launcher(), "")), \
                mock.patch.multiple(launch, **patches):
            launch.launch_game(game or _game(), types.SimpleNamespace(config={}),
                                source=launch_state.SOURCE_API, popen=popen)
        return play


class LifecycleTests(LaunchTests):
    def test_the_lifecycle_events_go_out_in_order(self) -> None:
        seen = []
        for name in (events.TABLE_LAUNCHING, events.TABLE_LAUNCHED, events.TABLE_EXITED):
            events.subscribe(name, lambda _n=name, **_: seen.append(_n))

        self._run(popen=lambda cmd, **k: _FakePopen(["Startup done\n"]))

        self.assertEqual(seen, ["table.launching", "table.launched", "table.exited"])

    def test_a_persons_own_commands_run_outside_everything_else(self) -> None:
        """"Before the table" has to mean before all of it, hooks included. Anywhere
        further in and what it means shifts as our own sequence changes."""
        seen = []
        for name in (events.TABLE_LAUNCHING, events.TABLE_EXITED):
            events.subscribe(name, lambda _n=name, **_: seen.append(_n))

        def before(game, table, launcher, ini_config):
            seen.append("pre")
            return table_commands.Around(ran=True)

        with mock.patch.object(table_commands, "before", before), \
                mock.patch.object(table_commands, "after",
                                  lambda around, **k: seen.append("post")):
            self._run(popen=lambda cmd, **k: _FakePopen(["Startup done\n"]))

        self.assertEqual(seen, ["pre", "table.launching", "table.exited", "post"])

    def test_a_command_that_was_set_to_stop_the_launch_stops_it(self) -> None:
        """And it stops it before anything is announced, so there is nothing to undo."""
        seen = []
        events.subscribe(events.TABLE_LAUNCHING, lambda **_: seen.append("launching"))

        with mock.patch.object(table_commands, "before",
                               side_effect=commands.CommandRefusedError("no share")):
            with self.assertRaises(launch.LaunchUnavailableError) as raised:
                self._run()

        self.assertIn("no share", str(raised.exception))
        self.assertEqual(seen, [])

    def test_a_game_that_never_starts_reports_no_launched(self) -> None:
        """table.launched means the table is up, not that a process exists."""
        seen = []
        for name in (events.TABLE_LAUNCHING, events.TABLE_LAUNCHED, events.TABLE_EXITED):
            events.subscribe(name, lambda _n=name, **_: seen.append(_n))

        self._run(popen=lambda cmd, **k: _FakePopen(["some other output\n"]))

        self.assertEqual(seen, ["table.launching", "table.exited"])

    def test_exited_still_fires_when_the_launch_blows_up(self) -> None:
        """Whoever heard launching has to hear exited, or the frontend never gets
        its input back."""
        seen = []
        events.subscribe(events.TABLE_EXITED, lambda **_: seen.append("exited"))

        def boom(cmd, **kwargs):
            raise RuntimeError("popen failed")

        with self.assertRaises(RuntimeError):
            self._run(popen=boom)

        self.assertEqual(seen, ["exited"])

    def test_a_hook_that_refuses_stops_the_launch_before_anything_starts(self) -> None:
        """Releasing the peripherals is a hook. If it fails, VPX must not start."""
        started = []
        events.hook(events.TABLE_LAUNCHING, lambda **_: (_ for _ in ()).throw(
            RuntimeError("device busy")))

        with self.assertRaises(RuntimeError):
            self._run(popen=lambda cmd, **k: started.append(cmd) or _FakePopen())

        self.assertEqual(started, [], "nothing was launched")
        self.assertFalse(launch_state.current().launching)

    def test_the_launch_is_announced_and_then_cleared(self) -> None:
        during = []
        events.subscribe(events.TABLE_LAUNCHED,
                         lambda **_: during.append(launch_state.current().as_dict()))

        self._run(popen=lambda cmd, **k: _FakePopen(["Startup done\n"]))

        self.assertEqual(during, [{"launching": True, "game_name": "Example",
                                   "source": "api"}])
        self.assertFalse(launch_state.current().launching)


class PlayDataTests(LaunchTests):
    """The gap that made consolidating worth doing: only the wheel used to do this."""

    def test_a_launch_from_any_source_is_recorded_as_a_play(self) -> None:
        play = self._run()

        play.increment_start_count.assert_called_once()

    def test_runtime_and_score_are_recorded_when_the_game_exits(self) -> None:
        play = self._run()

        play.add_play_time.assert_called_once()
        play.update_score_from_nvram.assert_called_once()
        play.delete_nvram_if_configured.assert_called_once()

    def test_the_table_that_was_launched_is_the_one_credited(self) -> None:
        """A folder can hold several tables, and the API can launch any of them."""
        game = _game()
        game.fullPathVPXfile = "/games/Example/Example (VR).vpx"

        play = self._run(game=game)

        self.assertEqual(play.increment_start_count.call_args.args[1], "Example (VR).vpx")
        self.assertEqual(play.add_play_time.call_args.args[2], "Example (VR).vpx")

    def test_the_record_is_announced_after_it_is_written(self) -> None:
        """Anything that shows play data reads it on this, not on `exited` - the
        runtime and the score are written after the exit goes out."""
        seen = []
        events.subscribe(events.TABLE_EXITED, lambda **_: seen.append("exited"))
        events.subscribe(events.TABLE_PLAY_RECORDED,
                         lambda **_: seen.append("recorded"))

        self._run()

        self.assertEqual(seen, ["exited", "recorded"])

    def test_a_game_that_never_started_records_nothing_to_announce(self) -> None:
        seen = []
        events.subscribe(events.TABLE_PLAY_RECORDED, lambda **_: seen.append("recorded"))

        def boom(cmd, **kwargs):
            raise RuntimeError("popen failed")

        with self.assertRaises(RuntimeError):
            self._run(popen=boom)

        self.assertEqual(seen, [])


class RefusalTests(LaunchTests):
    def _check(self, game=None, table=None, launcher_exists=True, launcher=True):
        found = _launcher("/opt/vpx" if launcher_exists else "/nope/vpx") \
            if launcher else None
        with mock.patch.object(launch, "_launcher_for",
                               lambda game, vpx_path: (found, "")), \
                mock.patch.object(launch, "resolve_launcher_path",
                                  lambda value: types.SimpleNamespace(
                                      exists=lambda: launcher_exists)):
            return launch.check_launchable(game or _game(),
                                           types.SimpleNamespace(config={}), table)

    def test_no_launcher_configured_is_refused_with_a_reason(self) -> None:
        """An install with none at all. The sentence has to point at where one is made,
        because there is nothing on this machine to correct."""
        with self.assertRaises(launch.LaunchUnavailableError) as caught:
            self._check(launcher=False)

        self.assertIn("System", str(caught.exception))

    def test_a_launcher_that_is_not_there_is_refused(self) -> None:
        with self.assertRaises(launch.LaunchUnavailableError) as caught:
            self._check(launcher_exists=False)

        self.assertIn("Visual Pinball X", str(caught.exception),
                      "the refusal names the launcher, not a config key")

    def test_a_second_launch_is_refused_while_one_is_running(self) -> None:
        """Two VPX processes would fight over the same hardware."""
        launch_state.set_launching("Example", source=launch_state.SOURCE_FRONTEND)

        with self.assertRaises(launch.LaunchBusyError):
            self._check()

    def test_a_table_the_game_does_not_have_is_refused(self) -> None:
        """Named files are checked against the folder, so this cannot reach outside it."""
        with mock.patch.object(launch.os.path, "isdir", return_value=True), \
                mock.patch.object(launch.os, "listdir", return_value=["Example.vpx"]), \
                mock.patch.object(launch.os.path, "isfile", return_value=True):
            with self.assertRaises(launch.UnknownTableError):
                self._check(table="../../etc/passwd")

    def test_a_table_the_game_does_have_is_accepted(self) -> None:
        with mock.patch.object(launch.os.path, "isdir", return_value=True), \
                mock.patch.object(launch.os, "listdir", return_value=["Other.vpx"]), \
                mock.patch.object(launch.os.path, "isfile", return_value=True):
            resolved = self._check(table="Other.vpx")

        self.assertTrue(resolved.endswith("Other.vpx"))

    def test_the_default_is_the_game_s_own_file(self) -> None:
        self.assertEqual(self._check(), "/games/Example/Example.vpx")


if __name__ == "__main__":
    unittest.main()


def _keyed_game(app="generic", key="mm"):
    """A game whose only entry has no file at all - a ROM its emulator looks up, a
    Pinball FX table id. The folder holds the record and the media and nothing else."""
    return types.SimpleNamespace(
        fullPathVPXfile="",
        fullPathGame="/games/Medieval Madness",
        gameDirName="Medieval Madness",
        meta_config={"tables": {"t9": {"id": "t9", "app": app, "key": key}}},
    )


class KeyedEntryTests(LaunchTests):
    """An entry with no file. Nothing about a key says whose it is, so the entry names
    its app - and that is what picks the launcher, in place of a suffix that is not
    there."""

    def _run_keyed(self, popen=None, table=None):
        found = _launcher("/opt/fx")
        found = found.__class__(launcher_id="l2", app="generic",
                                display_name="Generic", settings={"bin_path": "/opt/fx"})
        with mock.patch.object(launch.launchers, "get_launcher_store",
                               return_value=types.SimpleNamespace(
                                   launchers=lambda: [found],
                                   mappings=lambda: {},
                                   mapped=lambda _id: "")), \
                mock.patch.object(launch, "resolve_launcher_path",
                                  lambda value: types.SimpleNamespace(
                                      exists=lambda: True, __str__=lambda s: "/opt/fx")):
            return launch.check_launchable(_keyed_game(),
                                           types.SimpleNamespace(config={}), table)

    def test_a_game_with_no_file_is_still_launchable(self) -> None:
        """The one thing that must not happen: a folder holding only a keyed entry
        reading as a game nothing can play."""
        self.assertEqual(self._run_keyed(), "generic:mm")

    def test_it_can_be_named_by_the_key_its_app_knows_it_by(self) -> None:
        self.assertEqual(self._run_keyed(table="generic:mm"), "generic:mm")

    def test_a_key_this_game_does_not_have_is_refused(self) -> None:
        with self.assertRaises(launch.UnknownTableError):
            self._run_keyed(table="generic:nosuchrom")

    def test_the_launcher_comes_from_the_app_the_entry_declares(self) -> None:
        """Not from a suffix. There is no filename to take one off."""
        found = _launcher().__class__(launcher_id="l2", app="generic",
                                      display_name="Generic",
                                      settings={"bin_path": "/opt/fx"})
        with mock.patch.object(launch.launchers, "get_launcher_store",
                               return_value=types.SimpleNamespace(
                                   launchers=lambda: [found],
                                   mappings=lambda: {},
                                   mapped=lambda _id: "")):
            launcher, _asked = launch._launcher_for(
                "t9", {"app": "generic", "key": "mm"})

        self.assertIs(launcher, found)

    def test_the_command_is_built_from_the_key_and_not_a_path(self) -> None:
        entry = launch.apps.Entry(entry_id="t9", key="mm",
                                  game_dir="/games/Medieval Madness")
        found = _launcher().__class__(launcher_id="l2", app="generic",
                                      display_name="Generic",
                                      settings={"bin_path": "/opt/fx", "args": ""})

        cmd, marker = launch._plan(entry, "/opt/fx", found)

        self.assertEqual(cmd, ["/opt/fx", "mm"])
        self.assertEqual(marker, "", "a generic program cannot say when it is up")


class ReferencedEntryTests(LaunchTests):
    """A table that lives somewhere else - a .vpx on a share, or one file shared by
    several games. The record and the media are here; the file is not."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.elsewhere = os.path.join(self.tmp.name, "shared", "afm.vpx")
        os.makedirs(os.path.dirname(self.elsewhere))
        pathlib.Path(self.elsewhere).touch()
        self.game_dir = os.path.join(self.tmp.name, "games", "AFM")
        os.makedirs(self.game_dir)

    def _game_with(self, reference: str):
        return types.SimpleNamespace(
            fullPathVPXfile="", fullPathGame=self.game_dir, gameDirName="AFM",
            meta_config={"tables": {"r1": {"id": "r1", "path": reference}}})

    def _check(self, game, table=None):
        found = _launcher()
        with mock.patch.object(launch, "_launcher_for",
                               lambda table_id, entry: (found, "")), \
                mock.patch.object(launch, "resolve_launcher_path",
                                  lambda value: types.SimpleNamespace(
                                      exists=lambda: True)):
            return launch.check_launchable(game, types.SimpleNamespace(config={}), table)

    def test_an_absolute_reference_launches_what_it_points_at(self) -> None:
        self.assertEqual(self._check(self._game_with(self.elsewhere)), self.elsewhere)

    def test_a_relative_one_is_anchored_on_the_game_folder(self) -> None:
        """Which is what lets a library be moved or shared as one piece."""
        got = self._check(self._game_with("../../shared/afm.vpx"))

        self.assertEqual(got, os.path.normpath(self.elsewhere))

    def test_it_can_be_named_by_the_path_the_record_holds(self) -> None:
        self.assertEqual(self._check(self._game_with(self.elsewhere), self.elsewhere),
                         self.elsewhere)

    def test_a_reference_to_nothing_is_refused_as_unreachable(self) -> None:
        """Not as missing. Nothing here is lost - the usual cause is a share that has
        not mounted, and offering to forget the entry would be the wrong answer."""
        with self.assertRaises(launch.ReferenceUnreachableError) as caught:
            self._check(self._game_with("/nowhere/at/all.vpx"))

        self.assertIn("not reachable", str(caught.exception))

    def test_and_that_refusal_is_still_a_launch_refusal(self) -> None:
        """So every caller that already handles one keeps working."""
        self.assertTrue(issubclass(launch.ReferenceUnreachableError,
                                   launch.LaunchUnavailableError))

    def test_the_file_it_points_at_says_which_app_plays_it(self) -> None:
        """A reference names a file, so it answers the same way a table in the folder
        does - there is no `app` on the record and none is needed."""
        self.assertEqual(launch._app_of({"path": self.elsewhere}), "vpx")

    def test_the_command_is_built_from_the_resolved_path(self) -> None:
        entry = launch.apps.Entry(entry_id="r1", table=self.elsewhere,
                                  game_dir=self.game_dir)
        found = _launcher().__class__(launcher_id="l3", app="generic",
                                      display_name="Generic",
                                      settings={"bin_path": "/opt/x", "args": ""})

        cmd, _marker = launch._plan(entry, "/opt/x", found)

        self.assertEqual(cmd, ["/opt/x", self.elsewhere])
