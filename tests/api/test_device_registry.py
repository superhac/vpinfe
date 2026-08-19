"""The devices a hub knows about.

Keyed by `device_id` because it is the only thing about a device that does not change:
a display name is meant to be renamed and an address moves with DHCP. A registry that
keyed on either would lose track of a device the first time somebody used the feature.

One entry is the degenerate case of many, so nothing here treats a single device
specially - building it single-entry-only would have taken deliberate effort.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.device_registry import Device, DeviceRegistry


class DeviceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = DeviceRegistry(Path(self.tmp.name) / "devices.json")

    def test_a_hub_that_has_seen_nobody_has_an_empty_registry(self) -> None:
        self.assertEqual(self.registry.devices(), [])
        self.assertIsNone(self.registry.get("anything"))
        self.assertFalse(self.registry.knows("anything"))

    def test_recording_a_device_makes_it_known(self) -> None:
        self.registry.record("Aaaa111111", display_name="basement cab",
                           roles=("hub", "device"))

        device = self.registry.get("Aaaa111111")
        self.assertEqual(device.display_name, "basement cab")
        self.assertEqual(device.roles, ("hub", "device"))
        self.assertTrue(self.registry.knows("Aaaa111111"))

    def test_a_device_heard_from_twice_is_still_one_device(self) -> None:
        """The whole point of keying on the id: a reconnect is not a second device."""
        self.registry.record("Aaaa111111", display_name="cab")
        self.registry.record("Aaaa111111", display_name="cab")

        self.assertEqual(len(self.registry.devices()), 1)

    def test_a_rename_does_not_lose_the_device(self) -> None:
        """`display_name` addresses nothing, which is what makes renaming safe."""
        first = self.registry.record("Aaaa111111", display_name="old name")
        self.registry.record("Aaaa111111", display_name="new name")

        devices = self.registry.devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].display_name, "new name")
        self.assertEqual(devices[0].first_seen, first.first_seen,
                         "it is the same device, so it was first seen when it was")

    def test_a_new_address_is_the_same_device(self) -> None:
        """The reason the key is not an address: a phone on DHCP keeps its lease for a
        week and its identity forever. An address is an attribute that gets updated."""
        first = self.registry.record("Aaaa111111", display_name="phone",
                                     address="192.168.1.50")
        self.registry.record("Aaaa111111", display_name="phone", address="192.168.1.77")

        devices = self.registry.devices()
        self.assertEqual(len(devices), 1, "one device, not one per address it has held")
        self.assertEqual(devices[0].address, "192.168.1.77")
        self.assertEqual(devices[0].first_seen, first.first_seen)

    def test_what_the_install_owns_is_refreshed_and_what_we_own_is_not(self) -> None:
        """Name, roles and address are a cached copy of what that install last said.
        `first_seen` is ours, and is the one thing a later record must not move.

        The expected timestamp is pinned rather than read back from the first record:
        comparing two values the same code produced moves them together, so a
        `first_seen` that silently resets on every record would still look equal.
        """
        pinned = "2020-01-01T00:00:00Z"
        self.registry.record("Aaaa111111", display_name="a", roles=("device",),
                           address="192.168.1.10")
        self._rewrite_first_seen("Aaaa111111", pinned)

        later = self.registry.record("Aaaa111111", display_name="b", roles=("hub",),
                                   address="192.168.1.99")

        self.assertEqual((later.display_name, later.roles, later.address),
                         ("b", ("hub",), "192.168.1.99"))
        self.assertEqual(later.first_seen, pinned, "a re-record must not move it")
        self.assertNotEqual(later.last_seen, pinned, "but last_seen is now")

    def _rewrite_first_seen(self, device_id: str, when: str) -> None:
        """Put a known timestamp on disk, so the assertion has an outside witness."""
        payload = json.loads(self.registry.path.read_text())
        for entry in payload["devices"]:
            if entry["device_id"] == device_id:
                entry["first_seen"] = when
        self.registry.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_a_registry_holds_more_than_one(self) -> None:
        self.registry.record("Aaaa111111", display_name="cab")
        self.registry.record("Bbbb222222", display_name="desktop")

        self.assertEqual([p.device_id for p in self.registry.devices()],
                         ["Aaaa111111", "Bbbb222222"])

    def test_a_device_with_no_id_is_refused(self) -> None:
        """An id is the entry's identity; without one there is nothing to key on."""
        self.assertIsNone(self.registry.record(""))
        self.assertIsNone(self.registry.record("   "))
        self.assertEqual(self.registry.devices(), [])

    def test_forgetting_a_device_says_whether_there_was_one(self) -> None:
        self.registry.record("Aaaa111111")

        self.assertTrue(self.registry.forget("Aaaa111111"))
        self.assertFalse(self.registry.forget("Aaaa111111"))
        self.assertEqual(self.registry.devices(), [])


class DeviceRegistryStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "devices.json"

    def test_it_survives_being_reopened(self) -> None:
        DeviceRegistry(self.path).record("Aaaa111111", display_name="cab")

        self.assertEqual(DeviceRegistry(self.path).get("Aaaa111111").display_name, "cab")

    def test_the_file_carries_its_own_schema(self) -> None:
        DeviceRegistry(self.path).record("Aaaa111111")

        self.assertEqual(json.loads(self.path.read_text())["schema"], 1)

    def test_an_unreadable_registry_is_empty_rather_than_fatal(self) -> None:
        """A hub with a corrupt registry should still start. It has lost who it knew,
        which is recoverable; refusing to run is not."""
        self.path.write_text("{ not json", encoding="utf-8")

        self.assertEqual(DeviceRegistry(self.path).devices(), [])

    def test_a_field_a_newer_build_wrote_is_not_dropped(self) -> None:
        """A downgrade must not silently strip what it does not understand."""
        self.path.write_text(json.dumps({
            "schema": 99,
            "devices": [{"device_id": "Aaaa111111", "something_new": "keep me"}],
        }), encoding="utf-8")

        registry = DeviceRegistry(self.path)
        registry.record("Aaaa111111", display_name="cab")

        self.assertEqual(json.loads(self.path.read_text())["devices"][0]["something_new"],
                         "keep me")

    def test_an_entry_with_no_id_is_skipped_rather_than_crashing(self) -> None:
        self.path.write_text(json.dumps({
            "schema": 1,
            "devices": [{"display_name": "nameless"}, {"device_id": "Aaaa111111"}],
        }), encoding="utf-8")

        self.assertEqual([p.device_id for p in DeviceRegistry(self.path).devices()],
                         ["Aaaa111111"])


class DeviceTests(unittest.TestCase):
    def test_a_device_round_trips_through_its_dict(self) -> None:
        device = Device(device_id="Aaaa111111", display_name="cab",
                        roles=("hub", "device"), address="192.168.1.10",
                        first_seen="2026-01-01T00:00:00Z", last_seen="2026-01-02T00:00:00Z")

        self.assertEqual(Device.from_dict(device.as_dict()), device)


if __name__ == "__main__":
    unittest.main()
