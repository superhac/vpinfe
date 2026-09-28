"""Pressing a key into a running table: which way this device presses, and what each
way is run with. Nothing here types into this machine."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

# pynput is no longer imported at module scope - see `test_imports_without_pynput` below.
# Quartz still is, on macOS only, and PyObjC does not survive being stubbed out, so it is
# imported plainly and the suite skips where the platform will not have it at all.
try:
    from common.host.key_simulator import KeySimulator
except Exception as exc:                    # no display, or no PyObjC
    KeySimulator = None
    IMPORT_ERROR: Exception | None = exc
else:
    IMPORT_ERROR = None


class HeadlessImportTests(unittest.TestCase):
    """The module imports where pynput cannot: a headless runner, a container, a server
    install. Not skipped on macOS, since nothing may touch pynput at import anywhere; the
    import is stubbed rather than the module, so the real module is what is tested.
    """

    def _import_with_pynput_missing(self, platform: str):
        import builtins

        real_import = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name.startswith("pynput"):
                raise ImportError("this platform is not supported")
            return real_import(name, *args, **kwargs)

        saved = {name: module for name, module in sys.modules.items()
                 if name.startswith(("pynput", "common.host.key_simulator"))}
        real_platform = sys.platform
        try:
            for name in saved:
                del sys.modules[name]
            builtins.__import__ = refuse
            sys.platform = platform
            return importlib.import_module("common.host.key_simulator")
        finally:
            builtins.__import__ = real_import
            sys.platform = real_platform
            sys.modules.pop("common.host.key_simulator", None)
            sys.modules.update(saved)

    def test_imports_without_pynput(self) -> None:
        """A headless Linux runner, which is what CI is."""
        module = self._import_with_pynput_missing("linux")

        self.assertTrue(hasattr(module, "KeySimulator"))

    def test_the_key_map_is_not_built_until_it_is_asked_for(self) -> None:
        """A class attribute here would mean the map was built during the import above."""
        module = self._import_with_pynput_missing("linux")

        self.assertFalse(hasattr(module.KeySimulator, "KEY_ID_TO_PYNPUT"))
        self.assertTrue(callable(module.KeySimulator.key_id_to_pynput))


# These build the real map, so they need a machine where pynput loads; a headless runner
# imports the module and raises here.
try:
    import pynput.keyboard  # noqa: F401
except Exception as exc:                    # no display, or no input backend
    PYNPUT_ERROR: Exception | None = exc
else:
    PYNPUT_ERROR = None


@unittest.skipIf(KeySimulator is None, f"key_simulator unavailable here: {IMPORT_ERROR}")
@unittest.skipIf(PYNPUT_ERROR is not None, f"pynput will not load here: {PYNPUT_ERROR}")
class KeyMapTests(unittest.TestCase):
    def test_the_map_carries_every_key_id_the_page_can_send(self) -> None:
        """Derived from names rather than written out, so this checks the derivation
        against the ids the Remote page actually sends."""
        mapping = KeySimulator.key_id_to_pynput()

        for key_id in ("enter", "esc", "space", "f1", "f12", "up", "down",
                       "ctrl_l", "shift_l", "a", "z", "0", "9", "-", "/"):
            with self.subTest(key_id=key_id):
                self.assertIn(key_id, mapping)

    def test_right_command_types_as_command(self) -> None:
        """The one entry that is not `Key.<its own name>`; pynput's cmd_r is unused."""
        mapping = KeySimulator.key_id_to_pynput()

        self.assertEqual(mapping["cmd_r"], mapping["cmd"])


def _found(tool, *, works: bool = True, missing: bool = False):
    from common.host import tools

    if missing:
        return tools.Found(tool, tools.State.MISSING)
    return tools.Found(tool, tools.State.FOUND, Path(f"/usr/bin/{tool.name}"),
                       tools.Probe(works))


class _Recorded:
    """A runner that notes each argv and environment it is given."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict | None]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs.get("env")))


@unittest.skipIf(KeySimulator is None, f"key_simulator unavailable here: {IMPORT_ERROR}")
class SenderTests(unittest.TestCase):
    """Which way a device presses keys, read off its session."""

    SWAY = {"WAYLAND_DISPLAY": "wayland-1", "SWAYSOCK": "/run/sway.sock"}
    PLASMA = {"WAYLAND_DISPLAY": "wayland-0", "XDG_CURRENT_DESKTOP": "KDE"}

    def _sender(self, env, have=("wtype", "ydotool"), socket=True, system="linux"):
        from common.host import key_simulator

        def resolve(tool):
            return _found(tool, missing=tool.id not in have)

        return key_simulator.sender(env, system, resolve,
                                    exists=lambda _path: socket)

    def test_a_wlroots_session_presses_through_wtype(self) -> None:
        found = self._sender(self.SWAY)
        self.assertEqual((found.via, str(found.path)), ("wtype", "/usr/bin/wtype"))

    def test_without_wtype_it_is_ydotool_through_its_socket(self) -> None:
        found = self._sender({**self.SWAY, "XDG_RUNTIME_DIR": "/run/user/1000"},
                             have=("ydotool",))
        self.assertEqual((found.via, found.socket),
                         ("ydotool", "/run/user/1000/.ydotool_socket"))

    def test_another_compositor_tries_ydotool_first(self) -> None:
        self.assertEqual(self._sender(self.PLASMA).via, "ydotool")
        self.assertEqual(self._sender(self.PLASMA, socket=False).via, "wtype")

    def test_ydotool_with_its_service_stopped_says_so(self) -> None:
        found = self._sender(self.SWAY, have=("ydotool",), socket=False)

        self.assertFalse(found.available)
        self.assertEqual(found.reason["key"], "keys.send.no_ydotool_service")
        self.assertEqual(found.reason["fix"], "user")
        self.assertTrue(found.reason["remedy"])

    def test_neither_tool_names_the_one_to_install(self) -> None:
        found = self._sender(self.SWAY, have=())

        self.assertEqual(found.reason["key"], "keys.send.needs_tool")
        self.assertEqual(found.reason["params"], {"tool": "wtype"})
        self.assertEqual(found.reason["remedy"]["setting"], "tools.wtype_path")

    def test_x11_windows_and_macos_use_pynput(self) -> None:
        self.assertEqual(self._sender({"DISPLAY": ":0"}).via, "pynput")
        for system in ("windows", "darwin"):
            with self.subTest(system=system):
                self.assertEqual(self._sender({}, system=system).via, "pynput")

    def test_no_session_is_nothing_to_fix(self) -> None:
        found = self._sender({})

        self.assertEqual(found.as_dict()["reason"]["key"], "keys.send.no_session")
        self.assertEqual(found.reason["fix"], "none")

    def test_every_reason_is_in_the_catalog(self) -> None:
        from common.host import key_simulator
        from tests.support.catalogs import served

        catalog = served()
        for key in (key_simulator.NEEDS_TOOL, key_simulator.NO_YDOTOOL_SERVICE,
                    key_simulator.NO_SESSION, key_simulator.START_YDOTOOL_SERVICE,
                    "keys.send.with_remedy"):
            with self.subTest(key=key):
                self.assertIn(key, catalog)


@unittest.skipIf(KeySimulator is None, f"key_simulator unavailable here: {IMPORT_ERROR}")
class BackendTests(unittest.TestCase):
    """What each Tool is run with. Nothing here types into this machine."""

    def _simulator(self, via: str, **found):
        from common.host import key_simulator

        runner = _Recorded()
        chosen = key_simulator.Sender(via, Path(f"/usr/bin/{via}"), **found)
        return key_simulator.KeySimulator(sender_found=chosen,
                                          runner=runner), runner

    def test_wtype_types_a_key_by_its_keysym(self) -> None:
        simulator, runner = self._simulator("wtype")

        self.assertTrue(simulator.press_code("KeyP"))
        self.assertTrue(simulator.press_code("Escape"))
        self.assertTrue(simulator.hold("page_up", 0.1))
        self.assertTrue(simulator.combo("ctrl_l", "a"))

        self.assertEqual([argv for argv, _ in runner.calls], [
            ["/usr/bin/wtype", "-k", "p"],
            ["/usr/bin/wtype", "-k", "Escape"],
            ["/usr/bin/wtype", "-P", "Prior", "-s", "100", "-p", "Prior"],
            ["/usr/bin/wtype", "-P", "Control_L", "-P", "a", "-p", "a", "-p", "Control_L"],
        ])

    def test_ydotool_presses_the_evdev_number_through_its_socket(self) -> None:
        simulator, runner = self._simulator("ydotool", socket="/tmp/.ydotool_socket")

        self.assertTrue(simulator.press_code("KeyP"))

        argv, env = runner.calls[0]
        self.assertEqual(argv, ["/usr/bin/ydotool", "key", "25:1", "25:0"])
        self.assertEqual(env["YDOTOOL_SOCKET"], "/tmp/.ydotool_socket")

    def test_a_key_with_no_name_here_presses_nothing(self) -> None:
        simulator, runner = self._simulator("wtype")

        with self.assertLogs("vpinfe.common.host.key_simulator", level="WARNING"):
            self.assertFalse(simulator.press_code("Lang3"))
        self.assertEqual(runner.calls, [])

    def test_a_device_that_cannot_press_says_why_once(self) -> None:
        from common.host import key_simulator

        chosen = key_simulator.Sender("", reason={"key": key_simulator.NO_SESSION,
                                                  "params": {}})
        simulator = key_simulator.KeySimulator(sender_found=chosen)

        with self.assertLogs("vpinfe.common.host.key_simulator", level="WARNING") as logs:
            self.assertFalse(simulator.press_code("KeyP"))
            self.assertFalse(simulator.press_code("KeyP"))
        self.assertEqual(len(logs.output), 1)

    def test_a_tool_that_fails_is_a_key_not_pressed(self) -> None:
        import subprocess

        from common.host import key_simulator

        def failing(argv, **_kwargs):
            raise subprocess.CalledProcessError(1, argv, stderr="compositor said no")

        chosen = key_simulator.Sender("wtype", Path("/usr/bin/wtype"))
        simulator = key_simulator.KeySimulator(sender_found=chosen,
                                               runner=failing)
        with self.assertLogs("vpinfe.common.host.key_simulator", level="WARNING") as logs:
            self.assertFalse(simulator.press_code("KeyP"))
        self.assertIn("compositor said no", logs.output[0])


class KeyTableTests(unittest.TestCase):
    """One row per key, so pressing and hearing read the same table."""

    def test_every_code_and_number_is_one_key(self) -> None:
        from common.host import keys

        self.assertEqual(len(keys.BY_CODE), len(keys.KEYS))
        self.assertEqual(len(keys.BY_EVDEV), len(keys.KEYS))

    def test_codes_are_the_ones_a_binding_names(self) -> None:
        """A code the settings page has no name for is a code no binding holds: a
        letter, a digit, a function key or one of the named keys."""
        import re

        from common import input_registry
        from common.host import keys

        named = set(input_registry.key_names())
        spelled = re.compile(r"^(Key[A-Z]|Digit\d|F\d{1,2})$")
        self.assertEqual([key.code for key in keys.KEYS
                          if key.code not in named and not spelled.match(key.code)], [])

    def test_the_old_ydotool_numbers_are_kept(self) -> None:
        from common.host import keys

        for key_id, number in {"esc": 1, "p": 25, "enter": 28, "pause": 119,
                               "page_down": 109, "cmd_r": 126, "f12": 88}.items():
            with self.subTest(key_id=key_id):
                self.assertEqual(keys.BY_KEY_ID[key_id].evdev, number)


if __name__ == "__main__":
    unittest.main()
