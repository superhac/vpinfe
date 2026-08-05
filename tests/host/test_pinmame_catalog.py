"""PinMAME's catalog and audit, borrowed from the VPX install.

The locator and the chain-folding are pure logic, tested everywhere. The last
class drives the real shipped library and self-skips on machines without one -
which is exactly the availability story the feature itself tells.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common.games.asset_resolver import apply_audit, resolve_rom_chain
from common.host import pinmame_catalog


class LocatorTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop(pinmame_catalog.ENV_OVERRIDE, None)
        self.addCleanup(os.environ.pop, pinmame_catalog.ENV_OVERRIDE, None)

    def test_no_launcher_means_no_library(self) -> None:
        self.assertIsNone(pinmame_catalog.find_library(""))

    def test_linux_layout_finds_the_so_beside_the_binary(self) -> None:
        with TemporaryDirectory() as tmp:
            binary = Path(tmp) / "VPinballX_BGFX"
            binary.write_bytes(b"elf")
            (Path(tmp) / "libpinmame.so.3.7").write_bytes(b"so")

            found = pinmame_catalog.find_library(str(binary))

        self.assertIsNotNone(found)
        self.assertEqual(found.name, "libpinmame.so.3.7")

    def test_macos_bundle_layout_finds_the_frameworks_dylib(self) -> None:
        with TemporaryDirectory() as tmp:
            macos = Path(tmp) / "VPinballX.app" / "Contents" / "MacOS"
            frameworks = Path(tmp) / "VPinballX.app" / "Contents" / "Frameworks"
            macos.mkdir(parents=True)
            frameworks.mkdir(parents=True)
            binary = macos / "VPinballX_BGFX"
            binary.write_bytes(b"macho")
            (frameworks / "libpinmame.dylib").write_bytes(b"dylib")

            found = pinmame_catalog.find_library(str(binary))

        self.assertIsNotNone(found)
        self.assertEqual(found.parent.name, "Frameworks")

    def test_the_env_override_wins_and_a_bad_override_is_none(self) -> None:
        with TemporaryDirectory() as tmp:
            lib = Path(tmp) / "libpinmame.so"
            lib.write_bytes(b"so")
            os.environ[pinmame_catalog.ENV_OVERRIDE] = str(lib)
            self.assertEqual(pinmame_catalog.find_library(""), lib)

            os.environ[pinmame_catalog.ENV_OVERRIDE] = str(lib) + ".missing"
            self.assertIsNone(pinmame_catalog.find_library(""))

    def test_availability_says_why_not(self) -> None:
        available, reason = pinmame_catalog.availability("")
        self.assertFalse(available)
        self.assertIn("launcher", reason)

        with TemporaryDirectory() as tmp:
            binary = Path(tmp) / "VPinballX_BGFX"
            binary.write_bytes(b"elf")
            available, reason = pinmame_catalog.availability(str(binary))
        self.assertFalse(available)
        self.assertIn("libpinmame", reason)


class AuditFoldTests(unittest.TestCase):
    def _chain(self):
        return resolve_rom_chain("afm_113b", {}, [], required=True)

    def test_no_answer_leaves_the_name_match_standing(self) -> None:
        chain = apply_audit(self._chain(), None)

        self.assertEqual(chain["audit"], "unavailable")
        self.assertIsNone(chain["installed"])

    def test_a_full_set_makes_installed_true(self) -> None:
        chain = apply_audit(self._chain(),
                            {"catalog": True, "clone_of": "afm_113",
                             "description": "Attack From Mars (1.13b)", "found": True})

        self.assertEqual(chain["audit"], "ok")
        self.assertTrue(chain["installed"])
        self.assertEqual(chain["clone_of"], "afm_113")
        self.assertIsNone(chain["reason"])

    def test_the_audit_finally_makes_installed_false_sayable(self) -> None:
        """The name-match never says False; PinMAME's own audit may."""
        chain = apply_audit(self._chain(),
                            {"catalog": True, "clone_of": None,
                             "description": "x", "found": False})

        self.assertEqual(chain["audit"], "missing")
        self.assertFalse(chain["installed"])
        self.assertIn("audit", chain["reason"])

    def test_an_unknown_set_is_not_declared_missing(self) -> None:
        """nfl_pat is not in the catalog: players reach it through an alias. Not
        being known is not the same as not being installed."""
        chain = apply_audit(self._chain(), {"catalog": False})

        self.assertEqual(chain["audit"], "unknown_set")
        self.assertIsNone(chain["installed"])
        self.assertIn("alias", chain["reason"])


class WorkerContractTests(unittest.TestCase):
    def test_lookup_survives_a_dead_worker(self) -> None:
        with TemporaryDirectory() as tmp:
            lib = Path(tmp) / "libpinmame.so"
            lib.write_bytes(b"not really a library")
            binary = Path(tmp) / "VPinballX_BGFX"
            binary.write_bytes(b"elf")

            pinmame_catalog.clear_cache()
            with self.assertLogs("vpinfe.common.host.pinmame_catalog", level="WARNING"):
                entry = pinmame_catalog.lookup(str(binary), tmp, "afm_113b")

        self.assertIsNone(entry, "a crashed worker is no answer, not a wrong one")

    def test_answers_are_cached_per_roms_folder_state(self) -> None:
        with TemporaryDirectory() as tmp:
            binary = Path(tmp) / "VPinballX_BGFX"
            binary.write_bytes(b"elf")
            (Path(tmp) / "libpinmame.so").write_bytes(b"so")

            pinmame_catalog.clear_cache()
            fake = mock.Mock(return_value=mock.Mock(
                stdout=json.dumps({"afm_113b": {"catalog": True, "found": False}})))
            with mock.patch.object(pinmame_catalog.subprocess, "run", fake):
                first = pinmame_catalog.lookup(str(binary), tmp, "afm_113b")
                second = pinmame_catalog.lookup(str(binary), tmp, "afm_113b")

        self.assertEqual(first, second)
        self.assertEqual(fake.call_count, 1, "the second answer came from the cache")


def _shipped_library() -> str | None:
    for pattern in ("/Applications/VPinballX*.app/Contents/Frameworks/libpinmame*.dylib",):
        import glob
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[0]
    return None


@unittest.skipUnless(_shipped_library(), "no VPX install with libpinmame on this machine")
class RealLibraryTests(unittest.TestCase):
    """Runs against the actual shipped library where one exists, and self-skips
    elsewhere - CI has no VPX install, and that is the availability story."""

    def _run_worker(self, roms_dir: str, *names: str) -> dict:
        repo = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            [sys.executable, "-m", "common.host.pinmame_worker",
             _shipped_library(), roms_dir, *names],
            capture_output=True, text=True, timeout=60, cwd=str(repo),
        )
        return json.loads(proc.stdout)

    def test_the_catalog_knows_real_sets_and_rejects_dof_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            result = self._run_worker(tmp, "mm_109c", "GTB2001_1971")

        self.assertTrue(result["mm_109c"]["catalog"])
        self.assertEqual(result["mm_109c"]["clone_of"], "mm_10")
        self.assertIn("Medieval Madness", result["mm_109c"]["description"])
        self.assertFalse(result["GTB2001_1971"]["catalog"])

    def test_an_empty_roms_folder_audits_as_not_found(self) -> None:
        with TemporaryDirectory() as tmp:
            result = self._run_worker(tmp, "afm_113b")

        self.assertTrue(result["afm_113b"]["catalog"])
        self.assertFalse(result["afm_113b"]["found"])


if __name__ == "__main__":
    unittest.main()
