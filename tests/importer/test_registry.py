"""Reading a Windows registry export.

A `.reg` file is the one form of a foreign machine's registry that travels as a file, so
it is the one a library reached over a share can carry. Built on written-out text rather
than a machine's own export, so what is asserted is the format and not one cabinet's
settings.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common.extensions import host

host.Registry().load(host.BUNDLED_DIR / "library_importer")

from vpinfe_ext_library_importer import registry  # noqa: E402

SAMPLE = '''Windows Registry Editor Version 5.00

[HKEY_CURRENT_USER\\Software\\Freeware\\Visual PinMame\\default]
"samples"=dword:00000001
"dmd_red"=dword:000000ff

[HKEY_CURRENT_USER\\Software\\Freeware\\Visual PinMame\\afm_113b]
"cabinet_mode"=dword:00000001
"rompath"="C:\\\\vPinball\\\\VisualPinball\\\\VPinMAME\\\\roms"
@="the key's own value"

[-HKEY_CURRENT_USER\\Software\\Freeware\\Visual PinMame\\gone]
'''


class ParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = registry.parse(SAMPLE)

    def test_every_key_is_read_in_order(self) -> None:
        self.assertEqual([one.path.rsplit("\\", 1)[-1] for one in self.keys],
                         ["default", "afm_113b", "gone"])

    def test_a_dword_is_a_number(self) -> None:
        self.assertEqual(self.keys[0].values["samples"]["value"], 1)
        self.assertEqual(self.keys[0].values["dmd_red"]["value"], 255)

    def test_a_string_is_unescaped(self) -> None:
        """A path in an export is written with doubled backslashes, and handing that to
        anything that opens a file gives a path with twice the separators."""
        found = self.keys[1].values["rompath"]["value"]

        self.assertEqual(found, r"C:\vPinball\VisualPinball\VPinMAME\roms")

    def test_the_keys_own_value_is_kept_under_its_own_name(self) -> None:
        self.assertEqual(self.keys[1].values["@"]["value"], "the key's own value")

    def test_a_removal_is_recorded_rather_than_dropped(self) -> None:
        """A file that removes a setting is saying something about the machine it came
        from."""
        self.assertTrue(self.keys[2].removed)

    def test_the_raw_text_is_kept_beside_what_it_decoded_to(self) -> None:
        """A value that cannot usefully be decoded is still one somebody may want."""
        self.assertEqual(self.keys[0].values["samples"]["raw"], "dword:00000001")


class TypeTests(unittest.TestCase):
    def test_a_qword_is_a_number(self) -> None:
        self.assertEqual(
            registry.decode("hex(b):40,e2,01,00,00,00,00,00"), 123456)

    def test_a_multi_string_is_a_list(self) -> None:
        # "ab" NUL "cd" NUL NUL, UTF-16LE.
        raw = "hex(7):61,00,62,00,00,00,63,00,64,00,00,00,00,00"

        self.assertEqual(registry.decode(raw), ["ab", "cd"])

    def test_an_expandable_string_is_text(self) -> None:
        self.assertEqual(registry.decode("hex(2):61,00,62,00,00,00"), "ab")

    def test_a_byte_string_says_nothing_rather_than_guessing(self) -> None:
        """The caller keeps the raw text either way, and inventing a meaning for bytes
        would be worse than saying we cannot read them."""
        self.assertIsNone(registry.decode("hex:01,02,03"))


class FileTests(unittest.TestCase):
    def _written(self, text: str, encoding: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "export.reg"
        path.write_bytes(text.encode(encoding))
        return path

    def test_the_encoding_the_editor_writes_is_read(self) -> None:
        """UTF-16 with a mark. A plain UTF-8 read of one raises rather than returning
        nonsense, which is the good case - and is why it is tried first."""
        path = self._written(SAMPLE, "utf-16")

        with self.assertRaises(UnicodeDecodeError):
            path.read_text(encoding="utf-8")

        keys, said = registry.read(path)
        self.assertEqual(said, "")
        self.assertEqual(len(keys), 3)

    def test_one_somebody_converted_is_read_too(self) -> None:
        keys, said = registry.read(self._written(SAMPLE, "utf-8"))

        self.assertEqual(said, "")
        self.assertEqual(len(keys), 3)

    def test_something_that_is_not_an_export_is_refused(self) -> None:
        keys, said = registry.read(self._written("just a file\n", "utf-8"))

        self.assertEqual(keys, [])
        self.assertIn("does not look like", said)


class LayerTests(unittest.TestCase):
    """A per-ROM key is a sparse override on top of `default`, not a record."""

    def setUp(self) -> None:
        self.keys = registry.parse(SAMPLE)

    def test_a_rom_inherits_what_it_does_not_override(self) -> None:
        """Reading the ROM key alone gives a game a handful of settings and silently
        loses every one it was inheriting."""
        found = registry.settings_for(self.keys, "afm_113b")

        self.assertEqual(found["cabinet_mode"]["value"], 1)
        self.assertEqual(found["samples"]["value"], 1)
        self.assertEqual(found["dmd_red"]["value"], 255)

    def test_the_rom_wins_where_it_says_something(self) -> None:
        keys = registry.parse(SAMPLE.replace(
            '"cabinet_mode"=dword:00000001',
            '"cabinet_mode"=dword:00000001\n"samples"=dword:00000000'))

        self.assertEqual(registry.settings_for(keys, "afm_113b")["samples"]["value"], 0)

    def test_a_rom_nothing_was_recorded_for_still_gets_the_defaults(self) -> None:
        found = registry.settings_for(self.keys, "never_seen")

        self.assertEqual(sorted(found), ["dmd_red", "samples"])

    def test_the_machine_paths_are_kept_out_of_a_games_settings(self) -> None:
        """rompath and the directories are facts about the old machine, and folding them
        into a game would carry one cabinet's paths onto another."""
        keys = registry.parse(SAMPLE.replace(
            "[HKEY_CURRENT_USER\\Software\\Freeware\\Visual PinMame\\default]",
            "[HKEY_CURRENT_USER\\Software\\Freeware\\Visual PinMame\\globals]\n"
            '"rompath"="C:\\\\roms"\n\n'
            "[HKEY_CURRENT_USER\\Software\\Freeware\\Visual PinMame\\default]"))

        # A ROM with no rompath of its own. The sample's afm_113b has one, which is
        # what makes it the wrong game to ask this of.
        self.assertNotIn("rompath", registry.settings_for(keys, "never_seen"))
        self.assertEqual(registry.machine_settings(keys)["rompath"]["value"],
                         r"C:\roms")

    def test_only_real_roms_are_listed(self) -> None:
        self.assertEqual(registry.roms(self.keys), ["afm_113b", "gone"])


class UnderTests(unittest.TestCase):
    def test_the_keys_below_a_path_come_back_by_what_follows_it(self) -> None:
        found = registry.under(registry.parse(SAMPLE),
                               r"Software\Freeware\Visual PinMame")

        self.assertEqual(sorted(found), ["afm_113b", "default", "gone"])
        self.assertEqual(found["afm_113b"]["cabinet_mode"]["value"], 1)

    def test_the_path_is_matched_without_regard_to_case(self) -> None:
        """A registry is case-insensitive about paths, and an export carries whatever
        case the exporter felt like. The binaries on a real cabinet write
        `Visual PinMame` where the product is spelled `PinMAME`."""
        found = registry.under(registry.parse(SAMPLE),
                               r"software\freeware\visual pinmame")

        self.assertEqual(sorted(found), ["afm_113b", "default", "gone"])


if __name__ == "__main__":
    unittest.main()
