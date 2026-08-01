"""Shared assets: manufacturer logos keyed by metadata, layered like media.

The rules under test: user layer beats default, the slug drops corporate
boilerplate so VPSdb's name variants converge, and the alias map catches what
no rule can.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.shared_assets import (
    configure_shared_assets,
    manufacturer_logo_web_path,
    manufacturer_slug,
    resolve_assets_dir,
)


class SlugTests(unittest.TestCase):
    def test_corporate_suffixes_drop_so_name_variants_converge(self) -> None:
        for variant in ("Bally", "Bally Manufacturing",
                        "Bally Manufacturing Corporation"):
            self.assertEqual(manufacturer_slug(variant), "bally")
        for variant in ("Williams", "Williams Electronics"):
            self.assertEqual(manufacturer_slug(variant), "williams")

    def test_multi_word_brands_keep_their_words(self) -> None:
        self.assertEqual(manufacturer_slug("Data East"), "data-east")
        self.assertEqual(manufacturer_slug("Chicago Coin"), "chicago-coin")
        self.assertEqual(manufacturer_slug("Juegos Populares"), "juegos-populares")

    def test_a_name_that_is_all_suffixes_keeps_itself(self) -> None:
        """"Williams Electronics" must never collide with a brand literally
        named "Electronics"."""
        self.assertEqual(manufacturer_slug("Electronics"), "electronics")

    def test_punctuation_never_reaches_the_filename(self) -> None:
        self.assertEqual(manufacturer_slug("D. Gottlieb & Co."), "d-gottlieb")


class LookupTests(unittest.TestCase):
    def _assets(self, tmp) -> Path:
        root = Path(tmp) / "assets"
        for layer in ("default", "user"):
            (root / "manufacturers" / layer).mkdir(parents=True)
        configure_shared_assets(root)
        self.addCleanup(configure_shared_assets, None)
        return root

    def test_the_lookup_walks_layers_then_extensions(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._assets(tmp)
            (root / "manufacturers" / "default" / "bally.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_web_path("Bally Manufacturing"),
                             "/assets/manufacturers/default/bally.png")

    def test_the_users_file_beats_the_downloaded_one(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._assets(tmp)
            (root / "manufacturers" / "default" / "stern.png").write_bytes(b"png")
            (root / "manufacturers" / "user" / "stern.jpg").write_bytes(b"jpg")

            self.assertEqual(manufacturer_logo_web_path("Stern"),
                             "/assets/manufacturers/user/stern.jpg")

    def test_the_alias_map_redirects_and_the_user_layer_wins_it_too(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._assets(tmp)
            (root / "manufacturers" / "default" / "manufacturers.json").write_text(
                json.dumps({"D. Gottlieb & Co.": "gottlieb"}), encoding="utf-8")
            (root / "manufacturers" / "default" / "gottlieb.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_web_path("D. Gottlieb & Co."),
                             "/assets/manufacturers/default/gottlieb.png")

            (root / "manufacturers" / "user" / "manufacturers.json").write_text(
                json.dumps({"d-gottlieb": "premier"}), encoding="utf-8")
            (root / "manufacturers" / "user" / "premier.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_web_path("D. Gottlieb & Co."),
                             "/assets/manufacturers/user/premier.png")

    def test_no_file_no_name_or_no_root_all_mean_none(self) -> None:
        with TemporaryDirectory() as tmp:
            self._assets(tmp)
            self.assertIsNone(manufacturer_logo_web_path("Zaccaria"))
            self.assertIsNone(manufacturer_logo_web_path(""))
        configure_shared_assets(None)
        self.assertIsNone(manufacturer_logo_web_path("Bally"))

    def test_a_broken_alias_file_degrades_to_no_aliases(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._assets(tmp)
            (root / "manufacturers" / "user" / "manufacturers.json").write_text(
                "not json", encoding="utf-8")
            (root / "manufacturers" / "default" / "bally.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_web_path("Bally"),
                             "/assets/manufacturers/default/bally.png")

    def test_an_empty_alias_value_is_a_placeholder_not_an_alias(self) -> None:
        """A hand-edited TODO entry must never erase a working slug."""
        with TemporaryDirectory() as tmp:
            root = self._assets(tmp)
            (root / "manufacturers" / "user" / "manufacturers.json").write_text(
                json.dumps({"Bally Manufacturing": "", "Bally Wulff": "  "}),
                encoding="utf-8")
            (root / "manufacturers" / "default" / "bally.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_web_path("Bally Manufacturing"),
                             "/assets/manufacturers/default/bally.png")


class ReportTests(unittest.TestCase):
    def _assets(self, tmp) -> Path:
        root = Path(tmp) / "assets"
        for layer in ("default", "user"):
            (root / "manufacturers" / layer).mkdir(parents=True)
        configure_shared_assets(root)
        self.addCleanup(configure_shared_assets, None)
        return root

    def test_the_report_shows_slug_alias_and_resolution_per_name(self) -> None:
        from common.shared_assets import manufacturer_report

        with TemporaryDirectory() as tmp:
            root = self._assets(tmp)
            (root / "manufacturers" / "default" / "manufacturers.json").write_text(
                json.dumps({"Premier Technology": "gottlieb"}), encoding="utf-8")
            (root / "manufacturers" / "default" / "gottlieb.png").write_bytes(b"png")
            (root / "manufacturers" / "default" / "bally.png").write_bytes(b"png")

            rows = {row["name"]: row for row in manufacturer_report(
                ["Bally Manufacturing", "Premier Technology", "Bally Wulff"])}

        self.assertEqual(rows["Bally Manufacturing"],
                         {"name": "Bally Manufacturing", "slug": "bally",
                          "aliased_to": None,
                          "logo": "/assets/manufacturers/default/bally.png"})
        self.assertEqual(rows["Premier Technology"]["aliased_to"], "gottlieb")
        self.assertEqual(rows["Premier Technology"]["logo"],
                         "/assets/manufacturers/default/gottlieb.png")
        self.assertIsNone(rows["Bally Wulff"]["logo"],
                          "a miss is visible, never a fuzzy match")

    def test_the_report_exposes_an_alias_bypassing_a_users_file(self) -> None:
        """The invisible failure the report exists for: your file, shadowed."""
        from common.shared_assets import manufacturer_report

        with TemporaryDirectory() as tmp:
            root = self._assets(tmp)
            (root / "manufacturers" / "default" / "manufacturers.json").write_text(
                json.dumps({"Premier Technology": "gottlieb"}), encoding="utf-8")
            (root / "manufacturers" / "default" / "gottlieb.png").write_bytes(b"png")
            (root / "manufacturers" / "user" / "premier-technology.png").write_bytes(b"png")

            row = manufacturer_report(["Premier Technology"])[0]

        self.assertEqual(row["aliased_to"], "gottlieb")
        self.assertEqual(row["logo"], "/assets/manufacturers/default/gottlieb.png",
                         "the user's own file is not what resolves")

    def test_the_report_still_slugs_with_no_assets_root(self) -> None:
        from common.shared_assets import manufacturer_report

        configure_shared_assets(None)
        rows = manufacturer_report(["Williams Electronics", "", "  "])

        self.assertEqual(rows, [{"name": "Williams Electronics",
                                 "slug": "williams", "aliased_to": None,
                                 "logo": None}])


class ReferenceFileTests(unittest.TestCase):
    def test_the_reference_is_written_beside_the_maps(self) -> None:
        from common.shared_assets import write_manufacturer_reference

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "assets"
            (root / "manufacturers" / "default").mkdir(parents=True)
            configure_shared_assets(root)
            self.addCleanup(configure_shared_assets, None)

            path = write_manufacturer_reference(["Bally", "Data East"])
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(path.name, "manufacturers-reference.json")
        self.assertIn("Generated by VPinFE", payload["about"])
        self.assertEqual([row["slug"] for row in payload["manufacturers"]],
                         ["bally", "data-east"])

    def test_no_root_or_no_names_writes_nothing(self) -> None:
        from common.shared_assets import write_manufacturer_reference

        configure_shared_assets(None)
        self.assertIsNone(write_manufacturer_reference(["Bally"]))
        with TemporaryDirectory() as tmp:
            configure_shared_assets(Path(tmp))
            self.addCleanup(configure_shared_assets, None)
            self.assertIsNone(write_manufacturer_reference([]))

    def test_vps_names_come_deduped_and_sorted_from_the_cache(self) -> None:
        from common.shared_assets import vps_manufacturer_names

        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / "vpsdb.json"
            cache.write_text(json.dumps([
                {"manufacturer": "Williams"}, {"manufacturer": "Bally"},
                {"manufacturer": "Williams"}, {"manufacturer": ""},
                {"name": "no manufacturer key"},
            ]), encoding="utf-8")

            self.assertEqual(vps_manufacturer_names(cache), ["Bally", "Williams"])
        self.assertEqual(vps_manufacturer_names("/nonexistent/vpsdb.json"), [])


class ConfigTests(unittest.TestCase):
    def test_the_assets_dir_defaults_under_the_config_dir(self) -> None:
        self.assertEqual(resolve_assets_dir("", "/cfg"), Path("/cfg/assets"))
        self.assertEqual(resolve_assets_dir("  ", "/cfg"), Path("/cfg/assets"))
        self.assertEqual(resolve_assets_dir("/elsewhere/assets", "/cfg"),
                         Path("/elsewhere/assets"))


class PayloadTests(unittest.TestCase):
    def test_every_game_row_carries_the_logo_path_or_null(self) -> None:
        import json as _json
        from types import SimpleNamespace

        from frontend.game_state import games_json

        game = SimpleNamespace(
            tableDirName="Cactus Canyon (Bally 1998)",
            fullPathTable="/games/Cactus Canyon (Bally 1998)",
            fullPathVPXfile="",
            pupPackExists=False,
            altColorExists=False,
            altSoundExists=False,
            metaConfig={"Info": {"Manufacturer": "Bally Manufacturing"}},
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "assets"
            (root / "manufacturers" / "user").mkdir(parents=True)
            (root / "manufacturers" / "user" / "bally.png").write_bytes(b"png")
            configure_shared_assets(root)
            self.addCleanup(configure_shared_assets, None)

            rows = _json.loads(games_json([game]))

        self.assertEqual(rows[0]["ManufacturerLogoPath"],
                         "/assets/manufacturers/user/bally.png")


if __name__ == "__main__":
    unittest.main()
