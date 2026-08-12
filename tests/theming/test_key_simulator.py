"""Parsing VPX's key mappings, and saying so when there are none to use.

Visual Pinball writes `Mapping.LeftFlipper = ` with no value until the user binds that
key in its own UI. Storing those as None made a completely unbound ini look like 53
mappings, so the "no mappings found" warning never fired and every VPX button on the
Remote page did nothing while the page looked fine.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# pynput is no longer imported at module scope - see `test_imports_without_pynput` below,
# which is what keeps that true. Quartz still is, on macOS only, and stubbing PyObjC out
# is not an option: those modules run a one-shot _setup at import and do not survive being
# removed from sys.modules, so a stub here breaks a later test importing the same module.
#
# So it is imported plainly and the suite skips if the platform will not have it at all.
try:
    from managerui.key_simulator import KeySimulator
except Exception as exc:                    # no display, or no PyObjC
    KeySimulator = None
    IMPORT_ERROR: Exception | None = exc
else:
    IMPORT_ERROR = None

# What VPX writes before the user has bound anything, and after.
UNBOUND = "\n".join(["[Input]"] + [f"Mapping.{name} = " for name in
                                   ("LeftFlipper", "RightFlipper", "Start", "Plunger")])
BOUND = "\n".join([
    "[Input]",
    "Mapping.LeftFlipper = Key;225",
    "Mapping.RightFlipper = Key;229",
    "Mapping.Start = ",
])


def _parser() -> KeySimulator:
    """A KeySimulator with only the parsing half - __init__ builds an input backend."""
    simulator = KeySimulator.__new__(KeySimulator)
    simulator.debug = False
    return simulator


def _ini(body: str) -> str:
    tmp = TemporaryDirectory()
    _ini.keep.append(tmp)
    path = Path(tmp.name) / "VPinballX.ini"
    path.write_text(body, encoding="utf-8")
    return str(path)


_ini.keep = []


@unittest.skipIf(KeySimulator is None, f"keysimulator will not import here: {IMPORT_ERROR}")
class ParseKeyMappingTests(unittest.TestCase):
    def test_an_unbound_ini_yields_no_mappings(self) -> None:
        """It used to yield four, every one of them None."""
        with self.assertLogs("vpinfe.manager.keysimulator", level="WARNING") as logs:
            mappings = _parser().parse_vpinball_key_mappings(_ini(UNBOUND))

        self.assertEqual(mappings, {})
        self.assertIn("none of the 4 vpx key mappings", logs.output[0].lower())

    def test_the_warning_does_not_depend_on_debug(self) -> None:
        """The old one was inside `if self.debug`, so a normal run said nothing."""
        simulator = _parser()
        self.assertFalse(simulator.debug)
        with self.assertLogs("vpinfe.manager.keysimulator", level="WARNING"):
            simulator.parse_vpinball_key_mappings(_ini(UNBOUND))

    def test_bound_entries_are_kept_and_unbound_ones_dropped(self) -> None:
        mappings = _parser().parse_vpinball_key_mappings(_ini(BOUND))
        self.assertEqual(mappings, {"LeftFlipper": 225, "RightFlipper": 229})

    def test_an_input_section_with_no_mappings_says_that_instead(self) -> None:
        with self.assertLogs("vpinfe.manager.keysimulator", level="WARNING") as logs:
            self.assertEqual(
                _parser().parse_vpinball_key_mappings(_ini("[Input]\n")), {})
        self.assertIn("no mapping.* entries", logs.output[0].lower())


@unittest.skipIf(KeySimulator is None, f"keysimulator will not import here: {IMPORT_ERROR}")
class ConvertToKeyIdTests(unittest.TestCase):
    def test_a_scancode_with_no_key_id_is_reported(self) -> None:
        """3 of 45 on a real cabinet ini - VRCenter, VRUp, VRDown - vanished silently."""
        simulator = _parser()
        unknown = max(simulator.SDL_TO_KEY_ID) + 1000

        with self.assertLogs("vpinfe.manager.keysimulator", level="DEBUG") as logs:
            result = simulator.convert_to_key_ids({"VRCenter": unknown})

        self.assertEqual(result, {})
        self.assertIn("VRCenter", logs.output[0])

    def test_known_scancodes_still_convert(self) -> None:
        simulator = _parser()
        scancode = next(iter(simulator.SDL_TO_KEY_ID))
        self.assertEqual(simulator.convert_to_key_ids({"Start": scancode}),
                         {"Start": simulator.SDL_TO_KEY_ID[scancode]})


class HeadlessImportTests(unittest.TestCase):
    """The module has to import where pynput cannot.

    pynput raises at import on a machine with no input backend - a headless CI runner, a
    container, a server install. Three module-scope reads made the whole module
    unimportable there, so `managerui/pages/remote.py` never reached the failure it
    already imports lazily to handle.

    This does not skip on macOS: the point is that nothing touches pynput at import time,
    which is platform-independent. It stubs the import rather than the module, so it
    tests the real thing rather than a fake of it.
    """

    def _import_with_pynput_missing(self, platform: str):
        import builtins

        real_import = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name.startswith("pynput"):
                raise ImportError("this platform is not supported")
            return real_import(name, *args, **kwargs)

        saved = {name: module for name, module in sys.modules.items()
                 if name.startswith(("pynput", "managerui.key_simulator"))}
        real_platform = sys.platform
        try:
            for name in saved:
                del sys.modules[name]
            builtins.__import__ = refuse
            sys.platform = platform
            return importlib.import_module("managerui.key_simulator")
        finally:
            builtins.__import__ = real_import
            sys.platform = real_platform
            sys.modules.pop("managerui.key_simulator", None)
            sys.modules.update(saved)

    def test_imports_without_pynput(self) -> None:
        """A headless Linux runner, which is what CI is."""
        module = self._import_with_pynput_missing("linux")

        self.assertTrue(hasattr(module, "KeySimulator"))

    def test_the_key_map_is_not_built_until_it_is_asked_for(self) -> None:
        """The map is every named pynput Key. Building it at class-definition time is
        what made the import fail, so it has to stay a call - a class attribute here
        would mean it had been built during the import above."""
        module = self._import_with_pynput_missing("linux")

        self.assertFalse(hasattr(module.KeySimulator, "KEY_ID_TO_PYNPUT"))
        self.assertTrue(callable(module.KeySimulator.key_id_to_pynput))


@unittest.skipIf(KeySimulator is None, f"key_simulator unavailable here: {IMPORT_ERROR}")
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


if __name__ == "__main__":
    unittest.main()
