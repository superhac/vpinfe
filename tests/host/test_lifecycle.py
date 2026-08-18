"""Asking to start, stop or restart something: who gets asked, and what happens then."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from common import events, lifecycle
from frontend import lifecycle_host


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        lifecycle.reset_for_tests()
        self.addCleanup(lifecycle.reset_for_tests)
        self.done = []
        for scope, action in (
            (lifecycle.FRONTEND, lifecycle.START),
            (lifecycle.FRONTEND, lifecycle.STOP),
            (lifecycle.FRONTEND, lifecycle.RESTART),
            (lifecycle.APP, lifecycle.STOP),
            (lifecycle.APP, lifecycle.RESTART),
            (lifecycle.SYSTEM, lifecycle.STOP),
            (lifecycle.SYSTEM, lifecycle.RESTART),
        ):
            lifecycle.register_performer(
                scope, action, lambda request: self.done.append(request.pair))

    def _at(self, surface, address="window-1"):
        return lifecycle.Origin(surface, address)

    def test_an_unconfigured_install_never_asks(self) -> None:
        """The default is what VPinFE has always done: quit means quit."""
        asked = []
        lifecycle.register_confirmer(
            lifecycle.SURFACE_FRONTEND, lambda request: asked.append(request) or True)

        self.assertTrue(lifecycle.request(
            lifecycle.APP, lifecycle.STOP, origin=self._at(lifecycle.SURFACE_FRONTEND)))
        self.assertEqual(asked, [])
        self.assertEqual(self.done, [(lifecycle.APP, lifecycle.STOP)])

    def test_saying_no_stops_it(self) -> None:
        lifecycle.register_confirmer(lifecycle.SURFACE_FRONTEND, lambda _request: False)

        self.assertFalse(lifecycle.request(
            lifecycle.SYSTEM, lifecycle.STOP, origin=self._at(lifecycle.SURFACE_FRONTEND),
            confirm_scopes=["system"]))
        self.assertEqual(self.done, [])

    def test_only_the_configured_scopes_are_asked_about(self) -> None:
        """"Ask before touching the machine" must not start asking before quitting."""
        lifecycle.register_confirmer(lifecycle.SURFACE_FRONTEND, lambda _request: False)

        self.assertTrue(lifecycle.request(
            lifecycle.APP, lifecycle.STOP, origin=self._at(lifecycle.SURFACE_FRONTEND),
            confirm_scopes=["system"]))
        self.assertEqual(self.done, [(lifecycle.APP, lifecycle.STOP)])

    def test_the_question_goes_to_the_surface_that_asked(self) -> None:
        """The whole point of an addressed origin: a confirm follows the request home."""
        asked = []
        lifecycle.register_confirmer(
            lifecycle.SURFACE_FRONTEND, lambda _r: asked.append("frontend") or True)
        lifecycle.register_confirmer(
            lifecycle.SURFACE_MANAGER_UI, lambda _r: asked.append("manager_ui") or True)

        lifecycle.request(lifecycle.SYSTEM, lifecycle.RESTART,
                          origin=self._at(lifecycle.SURFACE_MANAGER_UI, "client-7"),
                          confirm_scopes=["system"])

        self.assertEqual(asked, ["manager_ui"], "the wrong surface was asked")

    def test_a_signal_has_nobody_to_ask_and_is_not_blocked_by_the_setting(self) -> None:
        """A SIGTERM that waits on a dialog is a process that will not die."""
        lifecycle.register_confirmer(lifecycle.SURFACE_FRONTEND, lambda _request: False)

        self.assertTrue(lifecycle.request(
            lifecycle.APP, lifecycle.STOP,
            origin=lifecycle.Origin(lifecycle.SURFACE_SIGNAL),
            confirm_scopes=["app", "system", "frontend"]))
        self.assertEqual(self.done, [(lifecycle.APP, lifecycle.STOP)])

    def test_a_surface_that_cannot_answer_denies(self) -> None:
        """The window went away mid-request, so the person is not there either."""
        def gone(_request):
            raise ConnectionError("the window is closed")

        lifecycle.register_confirmer(lifecycle.SURFACE_FRONTEND, gone)

        self.assertFalse(lifecycle.request(
            lifecycle.SYSTEM, lifecycle.STOP, origin=self._at(lifecycle.SURFACE_FRONTEND),
            confirm_scopes=["system"]))
        self.assertEqual(self.done, [])

    def test_every_surface_is_told_and_none_of_them_can_veto(self) -> None:
        told = []
        lifecycle.register_notifier(lambda request: told.append(request.describe()))
        lifecycle.register_notifier(lambda _request: (_ for _ in ()).throw(RuntimeError))
        lifecycle.register_notifier(lambda request: told.append(request.scope))

        self.assertTrue(lifecycle.request(
            lifecycle.SYSTEM, lifecycle.STOP,
            origin=self._at(lifecycle.SURFACE_FRONTEND)))
        # The broken one sits between the other two, so both running proves it neither
        # stopped the announcement nor stopped the action.
        self.assertEqual(told, ["Power off this machine", "system"])
        self.assertEqual(self.done, [(lifecycle.SYSTEM, lifecycle.STOP)])

    def test_nobody_is_told_about_something_that_was_declined(self) -> None:
        told = []
        lifecycle.register_notifier(told.append)
        lifecycle.register_confirmer(lifecycle.SURFACE_FRONTEND, lambda _request: False)

        lifecycle.request(lifecycle.SYSTEM, lifecycle.STOP,
                          origin=self._at(lifecycle.SURFACE_FRONTEND),
                          confirm_scopes=["system"])

        self.assertEqual(told, [])

    def test_a_build_that_cannot_do_it_says_so_rather_than_half_doing_it(self) -> None:
        lifecycle.reset_for_tests()
        self.assertFalse(lifecycle.request(
            lifecycle.FRONTEND, lifecycle.START,
            origin=self._at(lifecycle.SURFACE_MANAGER_UI)))

    def test_actions_that_are_not_things_are_refused(self) -> None:
        """`start` the machine and `start` VPinFE have nothing to act on: the process is
        already running and the machine is already on."""
        for scope, action in ((lifecycle.SYSTEM, lifecycle.START),
                              (lifecycle.APP, lifecycle.START),
                              ("everything", lifecycle.STOP)):
            with self.subTest(scope=scope, action=action):
                with self.assertRaises(ValueError):
                    lifecycle.request(scope, action,
                                      origin=self._at(lifecycle.SURFACE_FRONTEND))

    def test_every_request_is_described_in_words_a_person_uses(self) -> None:
        """This is read off a confirm dialog by someone deciding whether they meant it.

        Built from the scope and the action it said "stop the app" - naming an internal
        scope - and "restart the system", which reads as restarting VPinFE on the machine
        rather than rebooting the machine.
        """
        expected = {
            (lifecycle.FRONTEND, lifecycle.START): "Open the frontend windows",
            (lifecycle.FRONTEND, lifecycle.STOP): "Close the frontend windows",
            (lifecycle.FRONTEND, lifecycle.RESTART): "Reopen the frontend windows",
            (lifecycle.APP, lifecycle.STOP): "Quit VPinFE",
            (lifecycle.APP, lifecycle.RESTART): "Restart VPinFE",
            (lifecycle.SYSTEM, lifecycle.STOP): "Power off this machine",
            (lifecycle.SYSTEM, lifecycle.RESTART): "Reboot this machine",
        }
        for (scope, action), wording in expected.items():
            with self.subTest(scope=scope, action=action):
                request = lifecycle.Request(scope, action,
                                            self._at(lifecycle.SURFACE_FRONTEND))
                self.assertEqual(request.describe(), wording)

    def test_the_wording_covers_every_pair_the_build_allows(self) -> None:
        """A new pair with no wording falls back to the template that produced
        "stop the app", and nobody would notice until it was on screen."""
        described = {pair for pair in lifecycle._ALLOWED
                     if lifecycle.Request(*pair, self._at(lifecycle.SURFACE_FRONTEND))
                     .describe() != f"{pair[1]} the {pair[0]}"}

        self.assertEqual(described, lifecycle._ALLOWED)


    def test_the_performer_reaches_for_the_real_thing(self) -> None:
        """The shape of the mistake that shut a Mac down, made safe.

        install() registers a system-stop performer that calls system_actions for real.
        What went wrong was a test invoking it, so this never does: it patches the
        function first and asserts it was called. Assert on the call, do not make it.
        """
        lifecycle.reset_for_tests()
        self.addCleanup(lifecycle.reset_for_tests)
        with mock.patch("common.host.system_actions.shutdown_system") as power_off:
            lifecycle_host.install(
                config_store=None,
                config_dir=Path("."),
                frontend_browser=SimpleNamespace(terminate_all=lambda: None),
                shutdown_event=SimpleNamespace(set=lambda: None),
            )
            lifecycle.request(lifecycle.SYSTEM, lifecycle.STOP,
                              origin=lifecycle.Origin(lifecycle.SURFACE_SIGNAL))

        power_off.assert_called_once_with()

class NoticeTests(unittest.TestCase):
    """Every listening surface that did not start it gets told."""

    def setUp(self) -> None:
        lifecycle.reset_for_tests()
        events.clear()
        self.addCleanup(events.clear)
        self.addCleanup(lifecycle.reset_for_tests)
        lifecycle_host._config_store = None
        lifecycle_host._bridge = None

    def _install(self, bridge):
        """Wire the real notice path, with the power performers stubbed out.

        install() registers performers that really do power this machine off. A test
        that asks for a system stop and means only to watch the notice will shut the
        developer's machine down without a prompt - the confirm hook is off by default,
        so nothing stands between the request and osascript. It has happened.

        Patched for the whole test, not just install(), because the performers are
        closures that call system_actions at request time.
        """
        for name in ("shutdown_system", "reboot_system"):
            patcher = mock.patch(f"common.host.system_actions.{name}")
            self.addCleanup(patcher.stop)
            setattr(self, f"fake_{name}", patcher.start())

        lifecycle_host.install(
            config_store=None,
            config_dir=Path("."),
            frontend_browser=SimpleNamespace(terminate_all=lambda: None),
            shutdown_event=SimpleNamespace(set=lambda: None),
            ws_bridge=bridge,
        )

    def test_the_windows_are_told_when_the_manager_ui_asked(self) -> None:
        bridge = _Bridge()
        self._install(bridge)

        lifecycle.request(lifecycle.SYSTEM, lifecycle.STOP,
                          origin=lifecycle.Origin(lifecycle.SURFACE_MANAGER_UI, "client-1"))

        self.assertEqual(len(bridge.sent), 1)
        message, excluded = bridge.sent[0]
        self.assertEqual(message["type"], "LifecycleActing")
        self.assertEqual(message["description"], "Power off this machine")
        self.assertEqual(message["origin"], lifecycle.SURFACE_MANAGER_UI)
        self.assertIsNone(excluded, "no window asked, so no window is left out")

    def test_the_window_that_asked_is_not_told(self) -> None:
        """It already has the answer on screen; a second copy talks over it."""
        bridge = _Bridge()
        self._install(bridge)

        lifecycle.request(lifecycle.APP, lifecycle.STOP,
                          origin=lifecycle.Origin(lifecycle.SURFACE_FRONTEND, "table"))

        self.assertEqual(bridge.sent[0][1], "table")

    def test_a_declined_request_tells_nobody(self) -> None:
        bridge = _Bridge()
        self._install(bridge)
        lifecycle.register_confirmer(lifecycle.SURFACE_FRONTEND, lambda _request: False)

        lifecycle.request(lifecycle.SYSTEM, lifecycle.STOP,
                          origin=lifecycle.Origin(lifecycle.SURFACE_FRONTEND, "table"),
                          confirm_scopes=["system"])

        self.assertEqual(bridge.sent, [])

    def test_a_signal_still_tells_the_windows(self) -> None:
        """Nobody could be asked, but the screens should still say what is happening."""
        bridge = _Bridge()
        self._install(bridge)

        lifecycle.request(lifecycle.APP, lifecycle.STOP,
                          origin=lifecycle.Origin(lifecycle.SURFACE_SIGNAL))

        self.assertEqual(len(bridge.sent), 1)
        self.assertIsNone(bridge.sent[0][1])

    def test_installing_twice_does_not_say_it_twice(self) -> None:
        bridge = _Bridge()
        self._install(bridge)
        self._install(bridge)

        lifecycle.request(lifecycle.APP, lifecycle.STOP,
                          origin=lifecycle.Origin(lifecycle.SURFACE_SIGNAL))

        self.assertEqual(len(bridge.sent), 1, bridge.sent)


class _Bridge:
    """Records what would have gone to the windows."""

    def __init__(self) -> None:
        self.sent = []

    def send_event_all(self, message, exclude=None) -> None:
        self.sent.append((message, exclude))


if __name__ == "__main__":
    unittest.main()
