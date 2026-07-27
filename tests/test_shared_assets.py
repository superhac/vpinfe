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


class ConfigTests(unittest.TestCase):
    def test_the_assets_dir_defaults_under_the_config_dir(self) -> None:
        self.assertEqual(resolve_assets_dir("", "/cfg"), Path("/cfg/assets"))
        self.assertEqual(resolve_assets_dir("  ", "/cfg"), Path("/cfg/assets"))
        self.assertEqual(resolve_assets_dir("/elsewhere/assets", "/cfg"),
                         Path("/elsewhere/assets"))


class PayloadTests(unittest.TestCase):
    def test_every_table_row_carries_the_logo_path_or_null(self) -> None:
        import json as _json
        from types import SimpleNamespace

        from frontend.table_state import tables_json

        table = SimpleNamespace(
            tableDirName="Cactus Canyon (Bally 1998)",
            fullPathTable="/tables/Cactus Canyon (Bally 1998)",
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

            rows = _json.loads(tables_json([table]))

        self.assertEqual(rows[0]["ManufacturerLogoPath"],
                         "/assets/manufacturers/user/bally.png")


if __name__ == "__main__":
    unittest.main()
