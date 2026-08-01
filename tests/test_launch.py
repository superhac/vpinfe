"""The one launch path, which the wheel, the Remote page and the API all take.

The behaviour pinned here used to be split across two implementations that
disagreed - most visibly, only one of them recorded that a table had been played.
"""

from __future__ import annotations

import types
import unittest
from unittest import mock

from common import events
from common.host import launch, launch_state


class _FakePopen:
    def __init__(self, lines=()):
        self.stdout = list(lines)
        self.waited = False

    def wait(self):
        self.waited = True
        return 0


def _game(name="Example"):
    return types.SimpleNamespace(
        fullPathVPXfile=f"/tables/{name}/{name}.vpx",
        fullPathTable=f"/tables/{name}",
        tableDirName=name,
        metaConfig={},
    )


def _settings():
    return types.SimpleNamespace(
        vpx_bin_path="/opt/vpx",
        global_ini_override="",
        global_game_ini_override_enabled=False,
        global_game_ini_override_mask="",
        vpx_launch_env="",
    )


class LaunchTests(unittest.TestCase):
    def setUp(self) -> None:
        events.clear()
        launch_state.clear()
        self.addCleanup(events.clear)
        self.addCleanup(launch_state.clear)

    def _run(self, popen=None, game=None, **overrides):
        """Launch with every collaborator stubbed, so only the orchestration runs."""
        popen = popen or (lambda cmd, **kwargs: _FakePopen())
        launcher = types.SimpleNamespace(exists=lambda: True)
        patches = {
            "get_effective_launcher": lambda binpath, meta: (launcher, "vpxbinpath", None),
            "build_vpx_launch_command": lambda **kwargs: ["/opt/vpx", "-play", "x.vpx"],
            "parse_launch_env_overrides": lambda raw: {},
            "resolve_launch_tableini_override": lambda *a, **k: "",
            "get_plugin_profile_from_meta": lambda meta: "",
            "resolve_launch_plugin_profile": lambda profile: "",
            "delete_vpinball_log_on_start_if_configured": lambda settings: None,
            "get_active_profile": lambda: None,
        }
        patches.update(overrides)

        with mock.patch.object(launch, "SettingsConfig") as settings_cls, \
                mock.patch.object(launch, "game_play_service") as play, \
                mock.patch.multiple(launch, **patches):
            settings_cls.from_config.return_value = _settings()
            launch.launch_table(game or _game(), types.SimpleNamespace(config={}),
                                source=launch_state.SOURCE_API, popen=popen)
        return play


class LifecycleTests(LaunchTests):
    def test_the_lifecycle_events_go_out_in_order(self) -> None:
        seen = []
        for name in (events.GAME_LAUNCHING, events.GAME_LAUNCHED, events.GAME_EXITED):
            events.subscribe(name, lambda _n=name, **_: seen.append(_n))

        self._run(popen=lambda cmd, **k: _FakePopen(["Startup done\n"]))

        self.assertEqual(seen, ["table.launching", "table.launched", "table.exited"])

    def test_a_game_that_never_starts_reports_no_launched(self) -> None:
        """table.launched means the table is up, not that a process exists."""
        seen = []
        for name in (events.GAME_LAUNCHING, events.GAME_LAUNCHED, events.GAME_EXITED):
            events.subscribe(name, lambda _n=name, **_: seen.append(_n))

        self._run(popen=lambda cmd, **k: _FakePopen(["some other output\n"]))

        self.assertEqual(seen, ["table.launching", "table.exited"])

    def test_exited_still_fires_when_the_launch_blows_up(self) -> None:
        """Whoever heard launching has to hear exited, or the frontend never gets
        its input back."""
        seen = []
        events.subscribe(events.GAME_EXITED, lambda **_: seen.append("exited"))

        def boom(cmd, **kwargs):
            raise RuntimeError("popen failed")

        with self.assertRaises(RuntimeError):
            self._run(popen=boom)

        self.assertEqual(seen, ["exited"])

    def test_a_hook_that_refuses_stops_the_launch_before_anything_starts(self) -> None:
        """Releasing the peripherals is a hook. If it fails, VPX must not start."""
        started = []
        events.hook(events.GAME_LAUNCHING, lambda **_: (_ for _ in ()).throw(
            RuntimeError("device busy")))

        with self.assertRaises(RuntimeError):
            self._run(popen=lambda cmd, **k: started.append(cmd) or _FakePopen())

        self.assertEqual(started, [], "nothing was launched")
        self.assertFalse(launch_state.current().launching)

    def test_the_launch_is_announced_and_then_cleared(self) -> None:
        during = []
        events.subscribe(events.GAME_LAUNCHED,
                         lambda **_: during.append(launch_state.current().as_dict()))

        self._run(popen=lambda cmd, **k: _FakePopen(["Startup done\n"]))

        self.assertEqual(during, [{"launching": True, "table_name": "Example",
                                   "source": "api"}])
        self.assertFalse(launch_state.current().launching)


class PlayDataTests(LaunchTests):
    """The gap that made consolidating worth doing: only the wheel used to do this."""

    def test_a_launch_from_any_source_is_recorded_as_a_play(self) -> None:
        play = self._run()

        play.track_game_play.assert_called_once()
        play.increment_start_count.assert_called_once()

    def test_runtime_and_score_are_recorded_when_the_game_exits(self) -> None:
        play = self._run()

        play.add_runtime_minutes.assert_called_once()
        play.update_score_from_nvram.assert_called_once()
        play.delete_nvram_if_configured.assert_called_once()

    def test_the_game_file_that_was_launched_is_the_one_credited(self) -> None:
        """A folder can hold several game files, and the API can launch any of them."""
        game = _game()
        game.fullPathVPXfile = "/tables/Example/Example (VR).vpx"

        play = self._run(game=game)

        self.assertEqual(play.increment_start_count.call_args.args[1], "Example (VR).vpx")
        self.assertEqual(play.add_runtime_minutes.call_args.args[2], "Example (VR).vpx")


class RefusalTests(LaunchTests):
    def _check(self, game=None, game_file=None, launcher_exists=True, launcher=True):
        found = types.SimpleNamespace(exists=lambda: launcher_exists) if launcher else None
        with mock.patch.object(launch, "SettingsConfig") as settings_cls, \
                mock.patch.object(launch, "get_effective_launcher",
                                  lambda binpath, meta: (found, "vpxbinpath", None)):
            settings_cls.from_config.return_value = _settings()
            return launch.check_launchable(game or _game(),
                                           types.SimpleNamespace(config={}), game_file)

    def test_no_launcher_configured_is_refused_with_a_reason(self) -> None:
        with self.assertRaises(launch.LaunchUnavailableError) as caught:
            self._check(launcher=False)

        self.assertIn("vpxbinpath", str(caught.exception))

    def test_a_launcher_that_is_not_there_is_refused(self) -> None:
        with self.assertRaises(launch.LaunchUnavailableError):
            self._check(launcher_exists=False)

    def test_a_second_launch_is_refused_while_one_is_running(self) -> None:
        """Two VPX processes would fight over the same hardware."""
        launch_state.set_launching("Example", source=launch_state.SOURCE_FRONTEND)

        with self.assertRaises(launch.LaunchBusyError):
            self._check()

    def test_a_game_file_the_game_does_not_have_is_refused(self) -> None:
        """Named files are checked against the folder, so this cannot reach outside it."""
        with mock.patch.object(launch.os.path, "isdir", return_value=True), \
                mock.patch.object(launch.os, "listdir", return_value=["Example.vpx"]), \
                mock.patch.object(launch.os.path, "isfile", return_value=True):
            with self.assertRaises(launch.UnknownGameFileError):
                self._check(game_file="../../etc/passwd")

    def test_a_game_file_the_game_does_have_is_accepted(self) -> None:
        with mock.patch.object(launch.os.path, "isdir", return_value=True), \
                mock.patch.object(launch.os, "listdir", return_value=["Other.vpx"]), \
                mock.patch.object(launch.os.path, "isfile", return_value=True):
            resolved = self._check(game_file="Other.vpx")

        self.assertTrue(resolved.endswith("Other.vpx"))

    def test_the_default_is_the_game_s_own_file(self) -> None:
        self.assertEqual(self._check(), "/tables/Example/Example.vpx")


if __name__ == "__main__":
    unittest.main()
