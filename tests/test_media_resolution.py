"""The media resolution chain: table > folder > default, families per kind.

The rules under test are MEDIA.local design decisions 1-5 made concrete: spec
naming resolves above the fixed names vpinmediadb writes, a kind accepts its
whole extension family, and consumers only ever see one winning path.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.media_paths import MEDIA_SPECS, resolve_media_files
from managerui.services.media_service import replace_media_file, source_media_path

FOLDER = "Cactus Canyon (Bally 1998)"
TABLE = "Cactus Canyon (Bally 1998) - VPW 1.2"


def _resolve(medias, root=(), stem=TABLE):
    return resolve_media_files(f"/games/{FOLDER}", set(root), set(medias),
                               "table", stem)


class TierTests(unittest.TestCase):
    def test_the_default_tier_behaves_exactly_as_before(self) -> None:
        resolved = _resolve(["wheel.png", "bg.png"])

        self.assertEqual(resolved["wheel"].name, "wheel.png")
        self.assertEqual(resolved["bg"].name, "bg.png")

    def test_a_table_wheel_beats_the_folder_and_default_ones(self) -> None:
        resolved = _resolve([f"(Wheel) {TABLE}.png", f"(Wheel) {FOLDER}.png",
                             "wheel.png"])

        self.assertEqual(resolved["wheel"].name, f"(Wheel) {TABLE}.png")

    def test_a_folder_wheel_beats_the_default_one(self) -> None:
        resolved = _resolve([f"(Wheel) {FOLDER}.png", "wheel.png"])

        self.assertEqual(resolved["wheel"].name, f"(Wheel) {FOLDER}.png")

    def test_without_a_table_stem_tier_one_is_simply_skipped(self) -> None:
        resolved = _resolve([f"(Wheel) {TABLE}.png", "wheel.png"], stem=None)

        self.assertEqual(resolved["wheel"].name, "wheel.png",
                         "a stranger build's spec file is not this table's wheel")

    def test_a_media_refresh_cannot_clobber_a_users_spec_named_file(self) -> None:
        """The emergent property worth preserving: vpinmediadb writes tier 3 only,
        so the user's tier-2 file keeps winning after any refresh."""
        before = _resolve([f"(Wheel) {FOLDER}.png", "wheel.png"])
        after = _resolve([f"(Wheel) {FOLDER}.png", "wheel.png"])  # refresh rewrote tier 3

        self.assertEqual(before["wheel"].name, after["wheel"].name)


class FamilyTests(unittest.TestCase):
    def test_a_hand_placed_jpg_wheel_finally_resolves(self) -> None:
        """The live bug: import accepted wheel.jpg but resolution demanded
        wheel.png, so the file was invisible."""
        resolved = _resolve(["wheel.jpg"])

        self.assertEqual(resolved["wheel"].name, "wheel.jpg")

    def test_family_order_prefers_png_over_jpg_within_a_tier(self) -> None:
        resolved = _resolve(["wheel.jpg", "wheel.png"])

        self.assertEqual(resolved["wheel"].name, "wheel.png")

    def test_a_higher_tier_jpg_beats_a_lower_tier_png(self) -> None:
        """Tiers outrank families: specificity is the design's axis, format is
        a tie-breaker inside one tier."""
        resolved = _resolve([f"(Wheel) {FOLDER}.jpg", "wheel.png"])

        self.assertEqual(resolved["wheel"].name, f"(Wheel) {FOLDER}.jpg")

    def test_matching_is_case_insensitive(self) -> None:
        resolved = _resolve(["Wheel.PNG"])

        self.assertEqual(resolved["wheel"].name, "Wheel.PNG")

    def test_video_kinds_share_the_token_and_split_on_family(self) -> None:
        """The spec keys on token + extension: (Playfield) X.png is the image,
        (Playfield) X.mp4 is the video, one name scheme."""
        resolved = _resolve([f"(Playfield) {FOLDER}.png", f"(Playfield) {FOLDER}.mp4"])

        self.assertEqual(resolved["table"].name, f"(Playfield) {FOLDER}.png")
        self.assertEqual(resolved["table_video"].name, f"(Playfield) {FOLDER}.mp4")

    def test_audio_accepts_ogg(self) -> None:
        resolved = _resolve(["audio.ogg"])

        self.assertEqual(resolved["audio"].name, "audio.ogg")

    def test_the_medias_folder_wins_over_the_root_at_every_tier(self) -> None:
        resolved = _resolve(medias=["wheel.png"], root=["wheel.png"])

        self.assertEqual(resolved["wheel"].parent.name, "medias")


class NewKindTests(unittest.TestCase):
    """The five 3.0 additions, resolving through the same chain as everyone."""

    def test_each_new_kind_resolves_its_fixed_name(self) -> None:
        resolved = _resolve(["instructioncard.png", "topper.png", "loading.mp4",
                             "audiolaunch.mp3", "rulesheet.pdf"])

        # Keys are snake_case; fixed filenames are not. audiolaunch.mp3 and rulesheet.pdf
        # are the names VPX's own spec uses, so they stay run together - only the kind we
        # invented ourselves follows its key.
        for kind, name in (("instruction_card", "instructioncard.png"),
                           ("topper", "topper.png"),
                           ("loading", "loading.mp4"),
                           ("audio_launch", "audiolaunch.mp3"),
                           ("rule_sheet", "rulesheet.pdf")):
            self.assertEqual(resolved[kind].name, name)

    def test_topper_video_is_its_own_kind(self) -> None:
        """Topper mirrors bg/dmd/table: the token names the kind, the extension family
        picks image or video. One mixed kind would mean a cabinet could hold a still or
        a video, never both with the video preferred."""
        resolved = _resolve(["topper.mp4"])

        self.assertIsNone(resolved["topper"])
        self.assertEqual(resolved["topper_video"].name, "topper.mp4")

    def test_a_rulesheet_can_be_markdown(self) -> None:
        resolved = _resolve([f"(RuleSheet) {FOLDER}.md"])

        self.assertEqual(resolved["rule_sheet"].name, f"(RuleSheet) {FOLDER}.md")


class TokenAliasTests(unittest.TestCase):
    """VPX publishes (GameHelp) and (GameInfo); we lead with the plain-English name.

    Both resolve, so a media pack named either way works and nothing on disk has to
    be renamed.
    """

    def test_the_plain_english_token_resolves(self) -> None:
        resolved = _resolve([f"(RuleCard) {FOLDER}.png", f"(Flyer) {FOLDER}.png"])

        self.assertEqual(resolved["instruction_card"].name, f"(RuleCard) {FOLDER}.png")
        self.assertEqual(resolved["flyer"].name, f"(Flyer) {FOLDER}.png")

    def test_the_vpx_token_still_resolves(self) -> None:
        resolved = _resolve([f"(GameHelp) {FOLDER}.png", f"(GameInfo) {FOLDER}.png"])

        self.assertEqual(resolved["instruction_card"].name, f"(GameHelp) {FOLDER}.png")
        self.assertEqual(resolved["flyer"].name, f"(GameInfo) {FOLDER}.png")

    def test_the_preferred_token_wins_within_a_tier(self) -> None:
        resolved = _resolve([f"(GameHelp) {FOLDER}.png", f"(RuleCard) {FOLDER}.png"])

        self.assertEqual(resolved["instruction_card"].name, f"(RuleCard) {FOLDER}.png")

    def test_a_table_alias_still_beats_a_folder_level_preferred_token(self) -> None:
        """Tier outranks token preference, or "most specific wins" would not hold."""
        resolved = _resolve([f"(GameHelp) {TABLE}.png", f"(RuleCard) {FOLDER}.png"])

        self.assertEqual(resolved["instruction_card"].name, f"(GameHelp) {TABLE}.png")

    def test_aliases_are_only_where_the_published_name_is_opaque(self) -> None:
        aliased = {spec.key for spec in MEDIA_SPECS if spec.alt_tokens}

        self.assertEqual(aliased, {"instruction_card", "flyer"})

    def test_spec_named_new_kinds_import_by_token(self) -> None:
        from managerui.services.asset_registry import match_media_key

        self.assertEqual(match_media_key(f"(Topper) {FOLDER}.mp4"), "topper_video")
        self.assertEqual(match_media_key(f"(Topper) {FOLDER}.png"), "topper")
        self.assertEqual(match_media_key(f"(RuleCard) {FOLDER}.png"), "instruction_card")
        self.assertEqual(match_media_key(f"(GameHelp) {FOLDER}.png"), "instruction_card")
        self.assertEqual(match_media_key("rulesheet.pdf"), "rule_sheet")
        self.assertEqual(match_media_key(f"(Loading) {FOLDER}.mp4"), "loading")
        self.assertEqual(match_media_key("audio.ogg"), "audio")


class LogoTests(unittest.TestCase):
    """logo is its own kind; the wheel borrows it only when it has nothing."""

    def test_logo_resolves_as_its_own_kind(self) -> None:
        resolved = _resolve(["logo.png"])

        self.assertEqual(resolved["logo"].name, "logo.png")

    def test_a_wheel_less_game_shows_its_logo_in_the_wheel_slot(self) -> None:
        resolved = _resolve(["logo.png"])

        self.assertEqual(resolved["wheel"].name, "logo.png",
                         "better than a blank slot, everywhere at once")

    def test_any_real_wheel_outranks_the_logo_fallback(self) -> None:
        """The fallback sits below every wheel tier - even tier 3."""
        resolved = _resolve([f"(Logo) {TABLE}.png", "wheel.png"])

        self.assertEqual(resolved["wheel"].name, "wheel.png")
        self.assertEqual(resolved["logo"].name, f"(Logo) {TABLE}.png")

    def test_the_logo_itself_resolves_through_the_full_chain(self) -> None:
        resolved = _resolve([f"(Logo) {FOLDER}.png", "logo.png"])

        self.assertEqual(resolved["logo"].name, f"(Logo) {FOLDER}.png")

    def test_logo_png_imports_as_logo_not_wheel(self) -> None:
        """The alias fix: this is the import-behavior change PAR-12 documents."""
        from managerui.services.asset_registry import match_media_key

        self.assertEqual(match_media_key("logo.png"), "logo")
        self.assertEqual(match_media_key(f"(Logo) {FOLDER}.png"), "logo")
        self.assertEqual(match_media_key("wheel.png"), "wheel")


class WheelSetTests(unittest.TestCase):
    """Wheel sets: user override > active set > plain default (MEDIA decisions
    6-8), plus the reserved virtual set "logo"."""

    def _resolve_sets(self, medias, active=None, root=()):
        return resolve_media_files(f"/games/{FOLDER}", set(root), set(medias),
                                   "table", TABLE,
                                   {"wheel": active} if active else None)

    def test_an_active_set_beats_the_plain_default(self) -> None:
        resolved = self._resolve_sets(["wheel.png", "wheels/tarcisio/wheel.png"],
                                      active="tarcisio")

        self.assertTrue(str(resolved["wheel"]).endswith(
            os.path.join("medias", "wheels", "tarcisio", "wheel.png")))

    def test_a_users_spec_named_file_still_beats_the_set(self) -> None:
        """Activating a set never clobbers a hand-made per-version wheel."""
        resolved = self._resolve_sets([f"(Wheel) {TABLE}.png",
                                       "wheels/tarcisio/wheel.png"],
                                      active="tarcisio")

        self.assertEqual(resolved["wheel"].name, f"(Wheel) {TABLE}.png")

    def test_the_set_resolves_its_own_full_chain(self) -> None:
        resolved = self._resolve_sets([f"wheels/tarcisio/(Wheel) {FOLDER}.png",
                                       "wheels/tarcisio/wheel.png"],
                                      active="tarcisio")

        self.assertEqual(resolved["wheel"].name, f"(Wheel) {FOLDER}.png")

    def test_without_an_active_set_set_folders_are_invisible(self) -> None:
        resolved = self._resolve_sets(["wheel.png", "wheels/tarcisio/wheel.png"])

        self.assertTrue(str(resolved["wheel"]).endswith(
            os.path.join("medias", "wheel.png")))

    def test_a_missing_set_falls_through_to_the_default(self) -> None:
        resolved = self._resolve_sets(["wheel.png"], active="tarcisio")

        self.assertEqual(resolved["wheel"].name, "wheel.png")

    def test_the_virtual_logo_set_prefers_the_logo_over_the_wheel(self) -> None:
        """The whole point of choosing it: the logo shows even where a
        vpinmediadb wheel exists."""
        resolved = self._resolve_sets(["wheel.png", "logo.png"], active="logo")

        self.assertEqual(resolved["wheel"].name, "logo.png")

    def test_the_virtual_logo_set_still_loses_to_a_users_spec_file(self) -> None:
        resolved = self._resolve_sets([f"(Wheel) {TABLE}.png", "logo.png"],
                                      active="logo")

        self.assertEqual(resolved["wheel"].name, f"(Wheel) {TABLE}.png")

    def test_the_virtual_logo_set_falls_back_to_the_wheel_it_shunned(self) -> None:
        """A logo-less game under the logo set keeps its wheel - never a
        blank slot where art exists."""
        resolved = self._resolve_sets(["wheel.png"], active="logo")

        self.assertEqual(resolved["wheel"].name, "wheel.png")

    def test_the_override_beats_the_configured_default(self) -> None:
        from common.media_paths import active_set_for, set_media_set_override

        try:
            set_media_set_override("wheel", "tarcisio")
            self.assertEqual(active_set_for("wheel", "colorful"), "tarcisio")
        finally:
            set_media_set_override("wheel", None)
        self.assertEqual(active_set_for("wheel", "colorful"), "colorful")
        self.assertIsNone(active_set_for("wheel", "  "))

    def test_available_sets_reads_the_relative_listing(self) -> None:
        from common.media_paths import available_sets

        tree = {"wheel.png", "wheels/tarcisio/wheel.png",
                "wheels/colorful/wheel.png", "toppers/x/topper.png"}

        self.assertEqual(available_sets("wheel", tree), ["colorful", "tarcisio"])

    def test_list_media_sets_unions_the_library_and_adds_logo(self) -> None:
        from common.media_paths import list_media_sets

        with TemporaryDirectory() as tmp:
            for game, sets in (("Table A", ["tarcisio"]),
                                ("Table B", ["tarcisio", "colorful"])):
                for name in sets:
                    (Path(tmp) / game / "medias" / "wheels" / name).mkdir(parents=True)

            self.assertEqual(list_media_sets(tmp, "wheel"),
                             ["colorful", "logo", "tarcisio"])


class SpecCopyTests(unittest.TestCase):
    def test_a_game_type_copy_keeps_every_field_but_the_key(self) -> None:
        """It used to be rebuilt from four fields, so the copies quietly reported
        no token, no fallback, no set support, and the image family for videos."""
        from common.media_paths import MEDIA_SPECS, specs_for_playfield_variant

        # One copy per spec, in order, so they pair up exactly.
        for original, copy in zip(MEDIA_SPECS, specs_for_playfield_variant("fss"), strict=True):
            self.assertEqual(copy.token, original.token, original.key)
            self.assertEqual(copy.family, original.family, original.key)
            self.assertEqual(copy.fallback_kind, original.fallback_kind, original.key)
            self.assertEqual(copy.supports_sets, original.supports_sets, original.key)
            self.assertEqual(copy.attr, original.attr, original.key)

    def test_the_fss_key_collision_stays_harmless(self) -> None:
        """Under playfield variant fss the playfield spec is renamed onto the fss key, so
        two specs share it. Benign only because both resolve the same filename -
        worth pinning, since a divergence would be silent."""
        from common.media_paths import media_filename_map, specs_for_playfield_variant

        keyed_fss = [spec for spec in specs_for_playfield_variant("fss") if spec.key == "fss"]

        self.assertEqual(len(keyed_fss), 2)
        self.assertEqual({spec.filename("fss") for spec in keyed_fss}, {"fss.png"})
        self.assertEqual(media_filename_map("fss")["fss"], "fss.png")

    def test_the_video_copies_keep_the_video_family(self) -> None:
        from common.media_paths import VIDEO_FAMILY, specs_for_playfield_variant

        by_key = {spec.key: spec for spec in specs_for_playfield_variant("table")}

        self.assertEqual(by_key["table_video"].family, VIDEO_FAMILY)
        self.assertEqual(by_key["dmd_video"].family, VIDEO_FAMILY)


class ParserCasingTests(unittest.TestCase):
    def test_addon_folders_are_found_whatever_their_casing(self) -> None:
        """PUPVideos is the casing PinUP Popper writes, and the scanner used to
        miss it while the API found it - the same table, two answers."""
        import json

        from common.games.gameparser import GameParser

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / FOLDER
            (root / "medias").mkdir(parents=True)
            (root / f"{TABLE}.vpx").write_bytes(b"vpx")
            for name in ("PUPVideos", "Serum", "VNI", "Music"):
                (root / name).mkdir()
            (root / f"{FOLDER}.info").write_text(json.dumps({
                "Info": {"Title": "Cactus Canyon"},
                "VPXFile": {"filename": f"{TABLE}.vpx"},
            }), encoding="utf-8")

            game = GameParser(tmp).getAllGames()[0]

        self.assertTrue(game.pupPackExists, "PUPVideos holds a PUP pack")
        self.assertTrue(game.altColorExists)
        self.assertTrue(game.vniExists)
        self.assertTrue(game.musicExists)


class ImportSideTests(unittest.TestCase):
    def _game(self, tmp, *files):
        root = Path(tmp) / FOLDER
        (root / "medias").mkdir(parents=True)
        for rel in files:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"old")
        return root

    def test_an_imported_jpg_keeps_being_a_jpg(self) -> None:
        """The other live bug: JPEG bytes were written into wheel.png."""
        with TemporaryDirectory() as tmp:
            root = self._game(tmp)
            upload = Path(tmp) / "upload.jpg"
            upload.write_bytes(b"jpeg bytes")

            target = replace_media_file(str(root), FOLDER, "wheel", str(upload))

        self.assertTrue(target.endswith("wheel.jpg"))

    def test_replacing_removes_the_family_siblings_that_would_shadow_it(self) -> None:
        """wheel.png sits earlier in the family than wheel.jpg, so leaving it
        behind would make the replacement invisible."""
        with TemporaryDirectory() as tmp:
            root = self._game(tmp, "medias/wheel.png", "wheel.webp")
            upload = Path(tmp) / "upload.jpg"
            upload.write_bytes(b"jpeg bytes")

            replace_media_file(str(root), FOLDER, "wheel", str(upload))

            self.assertFalse((root / "medias" / "wheel.png").exists())
            self.assertFalse((root / "wheel.webp").exists())
            resolved = source_media_path(str(root), "wheel")

        self.assertTrue(resolved.endswith("wheel.jpg"),
                        "the new file is what resolution now finds")

    def test_an_unknown_extension_falls_back_to_the_canonical_name(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._game(tmp)
            upload = Path(tmp) / "upload.tiff"
            upload.write_bytes(b"tiff bytes")

            target = replace_media_file(str(root), FOLDER, "wheel", str(upload))

        self.assertTrue(target.endswith("wheel.png"))

    def test_source_media_path_sees_spec_named_files(self) -> None:
        """It used to be a second, fixed-names-only copy of the resolution rule."""
        with TemporaryDirectory() as tmp:
            root = self._game(tmp, f"medias/(Wheel) {FOLDER}.png")

            resolved = source_media_path(str(root), "wheel")

        self.assertTrue(resolved.endswith(f"(Wheel) {FOLDER}.png"))


class ParserOrderTests(unittest.TestCase):
    def test_media_resolves_against_the_build_that_launches(self) -> None:
        """Tier 1 keys off the default table, so the parser picks the default
        before it resolves media - the same reordering the launcher needed."""
        import json

        from common.games.gameparser import GameParser

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / FOLDER
            (root / "medias").mkdir(parents=True)
            for name in (f"{TABLE}.vpx", "some other build.vpx"):
                (root / name).write_bytes(b"vpx")
            (root / f"{FOLDER}.info").write_text(json.dumps({
                "Info": {"Title": "Cactus Canyon"},
                "VPXFile": {"filename": f"{TABLE}.vpx"},
            }), encoding="utf-8")
            (root / "medias" / f"(Wheel) {TABLE}.png").write_bytes(b"png")
            (root / "medias" / "(Wheel) some other build.png").write_bytes(b"png")

            parser = GameParser(tmp)
            game = parser.getAllGames()[0]

        self.assertEqual(os.path.basename(game.WheelImagePath),
                         f"(Wheel) {TABLE}.png",
                         "the recorded build's wheel, not the other build's")


if __name__ == "__main__":
    unittest.main()
