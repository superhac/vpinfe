"""Which asset kind a file is, decided by the registry alone.

Everything downstream - what a plan proposes, where an import writes - follows from the
kind, so these are the rules the rest of the upload path is built on.
"""

from __future__ import annotations

import unittest

from common.games.asset_registry import (
    classify_bare_extension,
    match_media_key,
    spec_for,
)


class AssetRegistryTests(unittest.TestCase):
    def test_classify_bare_extension(self):
        cases = [
            ("Medieval Madness.vpx", "table"),
            ("Medieval Madness.directb2s", "backglass"),
            ("mm_105b.crz", "altcolor_serum"),
            ("mm_105b.CRZ", "altcolor_serum"),
            ("mm_105b.cROMc", "altcolor_serum"),   # Serum's other format
            ("mm_105b.vni", "altcolor_vni"),
            ("mm_105b.PAL", "altcolor_vni"),
            ("mm_105b.pac", "altcolor_vni"),
            ("Medieval Madness.ini", "ini"),
            ("wheel.png", "media"),
            ("bg.mp4", "media"),
            ("audio.mp3", "media"),
            ("roms.zip", None),        # archives are inspected, not bare-classified
            ("pack.7z", None),
            ("readme.txt", None),
            ("noext", None),
        ]
        for filename, expected in cases:
            with self.subTest(filename=filename):
                spec = classify_bare_extension(filename)
                self.assertEqual(spec.key if spec else None, expected)

    def test_match_media_key_canonical_names(self):
        cases = [
            ("bg.png", "backglass"),
            ("dmd.png", "scoreview"),
            ("dmd.mp4", "scoreview_video"),
            ("table.png", "playfield"),
            ("table.mp4", "playfield_video"),
            ("wheel.png", "wheel"),
            ("audio.mp3", "audio"),
            ("realdmd-color.png", "real_dmd_color"),
        ]
        for filename, expected in cases:
            with self.subTest(filename=filename):
                self.assertEqual(match_media_key(filename), expected)

    def test_match_media_key_keyword_fallback(self):
        cases = [
            ("MyTable_wheel.png", "wheel"),
            ("Table_backglass.png", "backglass"),
            ("Game_dmd.mp4", "scoreview_video"),
            ("realdmd.png", "real_dmd"),
            ("song.mp3", "audio"),        # any recognized audio file -> audio slot
            ("photo.png", None),          # no keyword -> unrecognized
            ("notes.txt", None),          # non-media extension
        ]
        for filename, expected in cases:
            with self.subTest(filename=filename):
                self.assertEqual(match_media_key(filename), expected)

    def test_realdmd_not_claimed_by_dmd_rule(self):
        # "real_dmd" contains "scoreview"; the realdmd rule must win, and a realdmd video
        # (no such slot) must not fall through to dmd_video.
        self.assertEqual(match_media_key("realdmd.png"), "real_dmd")
        self.assertIsNone(match_media_key("realdmd.mp4"))

    def test_spec_for_flags(self):
        self.assertFalse(spec_for("table").requires_game)
        self.assertTrue(spec_for("backglass").requires_game)
        self.assertTrue(spec_for("altcolor_serum").requires_rom)
        self.assertFalse(spec_for("pup_pack").requires_rom)
        self.assertTrue(spec_for("media").allow_multiple)
        with self.assertRaises(KeyError):
            spec_for("nonexistent")


if __name__ == "__main__":
    unittest.main()
