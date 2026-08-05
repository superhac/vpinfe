"""Parsing VPX's key mappings, and saying so when there are none to use.

Visual Pinball writes `Mapping.LeftFlipper = ` with no value until the user binds that
key in its own UI. Storing those as None made a completely unbound ini look like 53
mappings, so the "no mappings found" warning never fired and every VPX button on the
Remote page did nothing while the page looked fine.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# keysimulator imports pynput - and Quartz on macOS - at module scope, so it cannot be
# imported on a headless Linux runner. Stubbing those out is not an option either: the
# PyObjC modules run a one-shot _setup at import and do not survive being removed from
# sys.modules, so a stub here breaks a later test that imports the same module.
#
# So it is imported plainly and the suite is skipped when the platform will not have it.
# The functions under test are pure parsing and need none of that; lifting them out of
# the module that imports pynput would give this coverage back on Linux.
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


if __name__ == "__main__":
    unittest.main()
