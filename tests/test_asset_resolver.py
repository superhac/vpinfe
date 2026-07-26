"""The asset model: what a game file would use, and what the folder holds for whom.

The rules under test mirror VPX's own lookup code - GetSettingsFileName in
pintable.h, the B2SServer constructor, pinmame's Alias.cpp. A regression here means
we disagree with the engine about what a launch would load.
"""

from __future__ import annotations

import unittest

from common.tables import asset_resolver as res

FOLDER = "Attack from Mars (Bally 1995)"
BIGUS = "Attack from Mars (Bally 1995) - bigus1 (1) - VPF_14317.vpx"
CYBER = "Attack from Mars (Bally 1995) - cyberpez (1) - VPF_14030.vpx"


class LaunchLensTests(unittest.TestCase):
    def test_a_stem_named_asset_wins_over_the_folder_named_one(self) -> None:
        files = [BIGUS, "Attack from Mars (Bally 1995) - bigus1 (1) - VPF_14317.directb2s",
                 f"{FOLDER}.directb2s"]

        resolved = res.resolve_for_game_file(BIGUS, FOLDER, files)

        self.assertEqual(resolved["backglass"]["resolution"], "dedicated")
        self.assertIn("bigus1", resolved["backglass"]["file"])

    def test_a_game_file_without_its_own_asset_inherits_the_folder_named_one(self) -> None:
        """VPX's fallback: the folder-named file is shared between all builds."""
        files = [BIGUS, CYBER, f"{FOLDER}.directb2s"]

        resolved = res.resolve_for_game_file(CYBER, FOLDER, files)

        self.assertEqual(resolved["backglass"],
                         {"resolution": "shared", "file": f"{FOLDER}.directb2s"})

    def test_nothing_resolves_to_none(self) -> None:
        resolved = res.resolve_for_game_file(BIGUS, FOLDER, [BIGUS])

        for kind in ("backglass", "settings", "script", "pov", "scv"):
            self.assertEqual(resolved[kind], {"resolution": "none"})

    def test_matching_is_case_insensitive_like_vpx(self) -> None:
        files = [BIGUS, BIGUS.replace(".vpx", ".DirectB2S")]

        resolved = res.resolve_for_game_file(BIGUS, FOLDER, files)

        self.assertEqual(resolved["backglass"]["resolution"], "dedicated")

    def test_a_pov_never_falls_back_to_the_folder_name(self) -> None:
        """pintable.cpp auto-imports a stem-named .pov only - no folder fallback."""
        files = [BIGUS, f"{FOLDER}.pov"]

        resolved = res.resolve_for_game_file(BIGUS, FOLDER, files)

        self.assertEqual(resolved["pov"], {"resolution": "none"})

    def test_settings_fall_back_to_the_folder_name(self) -> None:
        """GetSettingsFileName step 3: <folder-name>.ini, case-insensitively."""
        files = [BIGUS, f"{FOLDER}.INI"]

        resolved = res.resolve_for_game_file(BIGUS, FOLDER, files)

        self.assertEqual(resolved["settings"]["resolution"], "shared")


class InventoryLensTests(unittest.TestCase):
    def test_every_file_is_attributed(self) -> None:
        files = [
            BIGUS, CYBER,
            BIGUS.replace(".vpx", ".directb2s"),       # dedicated to bigus
            f"{FOLDER}.directb2s",                     # shared
            "AFM - long gone build.directb2s",         # orphaned
        ]

        inv = res.inventory(FOLDER, files, [BIGUS, CYBER])

        bindings = {e["binding"] for e in inv["backglass"]["files"]}
        self.assertEqual(bindings, {"dedicated", "shared", "orphaned"})
        dedicated = [e for e in inv["backglass"]["files"] if e["binding"] == "dedicated"]
        self.assertEqual(dedicated[0]["game_file"], BIGUS)

    def test_an_orphan_is_the_residue_of_a_deleted_build(self) -> None:
        inv = res.inventory(FOLDER, ["Old Build.directb2s"], [BIGUS])

        self.assertEqual(inv["backglass"]["files"][0]["binding"], "orphaned")

    def test_an_empty_folder_reports_empty_lists_for_every_kind(self) -> None:
        inv = res.inventory(FOLDER, [], [])

        for kind in ("backglass", "settings", "script", "pov", "scv"):
            self.assertEqual(inv[kind], {"files": []})


class RomChainTests(unittest.TestCase):
    def test_a_declared_rom_with_its_zip_is_installed(self) -> None:
        chain = res.resolve_rom_chain("afm_113b", {}, ["afm_113b.zip"])

        self.assertEqual(chain["effective"], "afm_113b")
        self.assertTrue(chain["installed"])
        self.assertIsNone(chain["alias_of"])

    def test_an_alias_rewrites_the_declared_name_before_anything_is_looked_up(self) -> None:
        """pinmame swaps alias for real before loading - Alias.cpp."""
        chain = res.resolve_rom_chain("afm_ultra", {"afm_ultra": "afm_113b"},
                                      ["afm_113b.zip"])

        self.assertEqual(chain["alias_of"], "afm_113b")
        self.assertEqual(chain["effective"], "afm_113b")
        self.assertTrue(chain["installed"])

    def test_not_found_is_reported_as_unknown_not_missing(self) -> None:
        """A DOF-only name on an EM table, or a rom in a global folder: neither is
        a defect, so the answer is null-with-reason, never False."""
        chain = res.resolve_rom_chain("GTB2001_1971", {}, [])

        self.assertIsNone(chain["installed"])
        self.assertIn("global locations not searched", chain["reason"])

    def test_no_declared_rom_is_a_complete_non_answer(self) -> None:
        chain = res.resolve_rom_chain("", {}, ["whatever.zip"])

        self.assertIsNone(chain["declared"])
        self.assertIsNone(chain["installed"])

    def test_alias_matching_is_case_insensitive_like_pinmame(self) -> None:
        chain = res.resolve_rom_chain("AFM_Ultra", {"afm_ultra": "afm_113b"}, [])

        self.assertEqual(chain["effective"], "afm_113b")

    def test_alias_file_parsing_skips_comments_and_junk(self) -> None:
        aliases = res.parse_alias_file(
            "# my aliases\n\nafm_ultra, afm_113b\nbad_line\nmm_x mm_109c\n")

        self.assertEqual(aliases, {"afm_ultra": "afm_113b", "mm_x": "mm_109c"})


class FlexDmdTests(unittest.TestCase):
    def test_content_folders_are_found(self) -> None:
        state = res.flexdmd_state(["AFM.UltraDMD", "pinmame"], detected=True)

        self.assertTrue(state["installed"])
        self.assertEqual(state["content"], ["AFM.UltraDMD"])

    def test_declared_stays_none_until_the_script_extraction_exists(self) -> None:
        """The honest degradation, same as the rom detector."""
        state = res.flexdmd_state(["AFM.UltraDMD"], detected=None)

        self.assertIsNone(state["declared"])


class NvramTests(unittest.TestCase):
    def test_no_effective_rom_means_no_nvram_question(self) -> None:
        self.assertEqual(res.nvram_state("/nowhere", None), {"present": False})

    def test_present_nvram_reports_live_modification_time(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            nvdir = Path(tmp) / "pinmame" / "nvram"
            nvdir.mkdir(parents=True)
            (nvdir / "afm_113b.nv").write_bytes(b"scores")

            state = res.nvram_state(tmp, "afm_113b")

        self.assertTrue(state["present"])
        self.assertEqual(state["file"], "afm_113b.nv")
        self.assertIsInstance(state["modified_at"], int)


if __name__ == "__main__":
    unittest.main()
