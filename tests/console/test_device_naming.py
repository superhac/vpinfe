"""What a device is called, and which capability answer it gets.

Both are pure and both decide what somebody reads about hardware they may not be
standing next to, which is where a wrong answer is hardest to notice.
"""

import unittest

from common import device_client
from console import devices

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

    def test_another_install_is_unknown_until_it_has_answered(self) -> None:
        """Nothing has asked it. Saying "not offered" would report missing hardware."""
        device = {"device_id": "Bbbb222222", "kind": "vpinfe"}

        self.assertEqual(devices.capability_state(device, "launch", LOCAL, {"launch"}),
                         devices.UNKNOWN)

    def test_another_install_answers_from_what_the_probe_heard(self) -> None:
        """It declares its capabilities in the same response the probe reads for its name
        and version, so this costs no extra call - and throwing it away left every remote
        install saying "cannot be determined" for all of them."""
        device = {"device_id": "Bbbb222222", "kind": "vpinfe"}
        reach = {"state": device_client.ANSWERING, "capabilities": ["launch", "play"]}

        self.assertEqual(
            devices.capability_state(device, "launch", LOCAL, set(), reach),
            devices.PRESENT)
        self.assertEqual(
            devices.capability_state(device, "capture", LOCAL, set(), reach),
            devices.ABSENT)

    def test_a_build_that_did_not_say_is_not_a_build_that_offers_nothing(self) -> None:
        """The probe response carried no capability list at all until the field was
        declared on it, so every remote install read as offering none of them - a
        confident wrong answer, where "cannot be determined" is the true one."""
        device = {"device_id": "Bbbb222222", "kind": "vpinfe"}
        reach = {"state": device_client.ANSWERING}

        self.assertEqual(
            devices.capability_state(device, "launch", LOCAL, set(), reach),
            devices.UNKNOWN)

    def test_a_probe_that_found_nothing_leaves_it_unknown(self) -> None:
        """Unreachable is not an answer about what it offers."""
        device = {"device_id": "Bbbb222222", "kind": "vpinfe"}
        reach = {"state": device_client.UNREACHABLE, "capabilities": []}

        self.assertEqual(
            devices.capability_state(device, "launch", LOCAL, set(), reach),
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


class SettingsDoorTests(unittest.TestCase):
    """Configuration is edited on the install it configures, so this surface offers a
    door rather than the settings themselves."""

    CAB = {"device_id": "Bbbb222222", "address": "192.168.1.50", "port": 8001}

    def test_the_door_lands_on_that_install_s_system_page(self) -> None:
        """A new window on a front door is a dead end; one that lands where the settings
        are is navigation."""
        self.assertEqual(devices.settings_url(self.CAB),
                         "http://192.168.1.50:8001/console?view=system")

    def test_an_entry_with_no_port_has_nothing_to_dial(self) -> None:
        self.assertEqual(devices.settings_url({"address": "192.168.1.50"}), "")

    def test_a_device_that_answered_gets_a_live_door(self) -> None:
        reach = {"state": device_client.ANSWERING}

        self.assertEqual(devices.door_reason(self.CAB, reach, False), "")

    def test_a_device_that_is_not_answering_says_so_instead(self) -> None:
        """It must visibly not be a live door: the tab would open on a connection
        error, which is a worse answer than being told here."""
        reach = {"state": device_client.UNREACHABLE}

        self.assertTrue(devices.door_reason(self.CAB, reach, False))

    def test_an_entry_that_cannot_be_asked_says_which(self) -> None:
        reach = {"state": device_client.UNASKABLE}

        self.assertEqual(devices.door_reason(self.CAB, reach, False),
                         devices.UNREACHABLE_NOTE)

    def test_this_install_always_has_a_door(self) -> None:
        """It is a place in the Console already open, so nothing has to answer first."""
        self.assertEqual(devices.door_reason({}, None, True), "")


if __name__ == "__main__":
    unittest.main()
