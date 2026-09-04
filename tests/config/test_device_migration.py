"""Importing the one mobile device `[mobile]` could hold.

The marker is the trap. Once it is set the import silently does nothing, which is
correct for a user's file and fatal for a test: a migration that did not run looks
exactly like one that passed. Every test here builds a fresh registry, and
`_unmark` is how a test exercises the same file twice on purpose.
"""

from __future__ import annotations

import json
import unittest
from configparser import ConfigParser
from pathlib import Path
from tempfile import TemporaryDirectory

from common.config_store import ConfigStore
from common.device_migration import MOBILE_MIGRATION, ensure_mobile_device
from common.device_registry import DeviceRegistry


def _config(**mobile) -> ConfigParser:
    parser = ConfigParser()
    parser.add_section("mobile")
    for key, value in mobile.items():
        parser.set("mobile", key, str(value))
    return parser


class MobileImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "devices.json"
        self.registry = DeviceRegistry(self.path)

    def _unmark(self) -> None:
        """Clear the marker so the import can be asked to run a second time."""
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["migrations"] = [n for n in payload.get("migrations", [])
                                 if n != MOBILE_MIGRATION]
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_an_address_becomes_a_device(self) -> None:
        created = ensure_mobile_device(
            self.registry, _config(device_ip="192.168.1.50", device_port=2112))

        self.assertEqual(created, 1)
        device, = self.registry.devices()
        self.assertEqual(device.kind, "vpx_mobile")
        self.assertEqual((device.address, device.port), ("192.168.1.50", 2112))
        self.assertTrue(device.device_id, "an id was minted")

    def test_the_port_falls_back_when_the_ini_does_not_say(self) -> None:
        ensure_mobile_device(self.registry, _config(device_ip="192.168.1.50"))

        self.assertEqual(self.registry.devices()[0].port, 2112)

    def test_it_runs_once(self) -> None:
        """A second start must not mint a second entry for the same phone."""
        config = _config(device_ip="192.168.1.50")
        self.assertEqual(ensure_mobile_device(self.registry, config), 1)
        self.assertEqual(ensure_mobile_device(self.registry, config), 0)

        self.assertEqual(len(self.registry.devices()), 1)

    def test_clearing_the_marker_is_what_lets_it_run_again(self) -> None:
        """The trap, asserted: without `_unmark` the second call is a silent no-op, so a
        test that reuses a file proves nothing unless it resets deliberately."""
        config = _config(device_ip="192.168.1.50")
        ensure_mobile_device(self.registry, config)
        self.registry.forget(self.registry.devices()[0].device_id)

        self.assertEqual(ensure_mobile_device(self.registry, config), 0, "marker holds")
        self._unmark()
        self.assertEqual(ensure_mobile_device(self.registry, config), 1, "and releases")

    def test_no_address_imports_nothing_and_still_marks(self) -> None:
        """Marked anyway: the marker records that this build looked, so clearing the
        setting later does not bring the old address back on the next start."""
        self.assertEqual(ensure_mobile_device(self.registry, _config()), 0)

        self.assertEqual(self.registry.devices(), [])
        self.assertTrue(self.registry.has_migrated(MOBILE_MIGRATION))

    def test_an_existing_mobile_device_is_not_overwritten(self) -> None:
        """Someone configured a phone since; the ini is the older statement."""
        self.registry.record("Pppp444444", kind="vpx_mobile",
                             display_name="iPad", address="192.168.1.60", port=2112)

        self.assertEqual(
            ensure_mobile_device(self.registry, _config(device_ip="192.168.1.50")), 0)
        self.assertEqual([d.address for d in self.registry.devices()], ["192.168.1.60"])

    def test_an_install_entry_does_not_count_as_a_mobile_one(self) -> None:
        """An install records itself at startup, so the registry is never empty by the time
        this runs. Only a vpx_mobile entry means the import has been superseded."""
        self.registry.record("Aaaa111111", display_name="this install")

        self.assertEqual(
            ensure_mobile_device(self.registry, _config(device_ip="192.168.1.50")), 1)
        self.assertEqual(len(self.registry.devices()), 2)


class RealIniTests(unittest.TestCase):
    """Through a ConfigStore rather than a hand-built parser, because the ini a user
    actually upgrades from says `DeviceIP`, and the canonical key it resolves to is
    the only thing the migration ever asks for."""

    def test_a_2x_ini_produces_exactly_one_mobile_device(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vpinfe.ini").write_text(
                "[Settings]\ntheme = Revolution\n\n"
                "[Mobile]\nDeviceIP = 192.168.1.42\nDevicePort = 2112\n",
                encoding="utf-8")
            registry = DeviceRegistry(root / "devices.json")

            created = ensure_mobile_device(registry, ConfigStore(str(root / "vpinfe.ini")))

            self.assertEqual(created, 1)
            device, = registry.devices()
            self.assertEqual((device.kind, device.address, device.port),
                             ("vpx_mobile", "192.168.1.42", 2112))
