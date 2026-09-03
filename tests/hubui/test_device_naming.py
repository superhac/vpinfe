"""What a device is called, and which capability answer it gets.

Both are pure and both decide what somebody reads about hardware they may not be
standing next to, which is where a wrong answer is hardest to notice.
"""

import unittest

from hubui import devices

LOCAL = "Aaaa111111"


class DeviceLabelTests(unittest.TestCase):
    def test_a_named_device_is_called_its_name(self) -> None:
        self.assertEqual(
            devices.device_label({"display_name": "basement cab"}), "basement cab")

    def test_an_unnamed_device_falls_back_to_where_it_answered_from(self) -> None:
        """An install that reported no name is still the one at that address."""
        self.assertEqual(
            devices.device_label({"display_name": "", "address": "192.168.1.50"}),
            "192.168.1.50")

    def test_a_device_with_neither_is_still_called_something(self) -> None:
        self.assertEqual(devices.device_label({}), "Device")

    def test_whitespace_is_not_a_name(self) -> None:
        self.assertEqual(
            devices.device_label({"display_name": "   ", "address": "10.0.0.4"}),
            "10.0.0.4")


class CapabilityStateTests(unittest.TestCase):
    def test_this_install_answers_from_what_it_declared(self) -> None:
        device = {"device_id": LOCAL, "kind": "vpinfe"}

        self.assertEqual(devices.capability_state(device, "launch", LOCAL, {"launch"}),
                         devices.PRESENT)
        self.assertEqual(devices.capability_state(device, "capture", LOCAL, {"launch"}),
                         devices.ABSENT)

    def test_another_install_is_unknown_rather_than_absent(self) -> None:
        """Nothing has asked it. Saying "not offered" would report missing hardware."""
        device = {"device_id": "Bbbb222222", "kind": "vpinfe"}

        self.assertEqual(devices.capability_state(device, "launch", LOCAL, {"launch"}),
                         devices.UNKNOWN)

    def test_a_kind_that_cannot_declare_is_answered_from_its_kind(self) -> None:
        device = {"device_id": "Pppp444444", "kind": "vpx_mobile"}

        self.assertEqual(devices.capability_state(device, "launch", LOCAL, set()),
                         devices.PRESENT)
        self.assertEqual(devices.capability_state(device, "capture", LOCAL, set()),
                         devices.ABSENT)

    def test_every_state_has_a_chip(self) -> None:
        """A state with no entry renders as a KeyError on somebody's screen."""
        for state in (devices.PRESENT, devices.ABSENT, devices.UNKNOWN):
            self.assertIn(state, devices._CHIP)


if __name__ == "__main__":
    unittest.main()
