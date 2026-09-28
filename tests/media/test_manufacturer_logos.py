"""Manufacturer logos, keyed by metadata and layered like media.

The rules under test: user layer beats default, the slug drops corporate
boilerplate so VPSdb's name variants converge, and the alias map catches what
no rule can.
"""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

from common.manufacturer_logos import (
    configure_manufacturer_logos,
    manufacturer_logo_file,
    manufacturer_logo_url,
    manufacturer_slug,
    resolve_logos_dir,
)
from tests.support.library import fake_game


def _logos(test: unittest.TestCase, tmp: str) -> Path:
    root = Path(tmp) / "manufacturer_logos"
    for layer in ("default", "user"):
        (root / layer).mkdir(parents=True)
    configure_manufacturer_logos(root)
    test.addCleanup(configure_manufacturer_logos, None)
    return root


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
    def test_a_logo_is_named_by_its_slug_and_nothing_else(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)
            (root / "default" / "bally.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_url("Bally Manufacturing"),
                             "/manufacturers/bally/logo")

    def test_the_users_file_beats_the_downloaded_one(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)
            (root / "default" / "stern.png").write_bytes(b"png")
            (root / "user" / "stern.jpg").write_bytes(b"jpg")

            self.assertEqual(manufacturer_logo_file("stern"), root / "user" / "stern.jpg")

    def test_the_alias_map_redirects_and_the_user_layer_wins_it_too(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)
            (root / "default" / "manufacturers.json").write_text(
                json.dumps({"D. Gottlieb & Co.": "gottlieb"}), encoding="utf-8")
            (root / "default" / "gottlieb.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_url("D. Gottlieb & Co."),
                             "/manufacturers/gottlieb/logo")

            (root / "user" / "manufacturers.json").write_text(
                json.dumps({"d-gottlieb": "premier"}), encoding="utf-8")
            (root / "user" / "premier.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_url("D. Gottlieb & Co."),
                             "/manufacturers/premier/logo")

    def test_no_file_no_name_or_no_folder_all_mean_none(self) -> None:
        with TemporaryDirectory() as tmp:
            _logos(self, tmp)
            self.assertIsNone(manufacturer_logo_url("Zaccaria"))
            self.assertIsNone(manufacturer_logo_url(""))
        configure_manufacturer_logos(None)
        self.assertIsNone(manufacturer_logo_url("Bally"))

    def test_a_slug_that_is_not_one_finds_no_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)
            (root / "bally.png").write_bytes(b"png")

            self.assertIsNone(manufacturer_logo_file("../bally"))
            self.assertIsNone(manufacturer_logo_file("Bally"))

    def test_a_broken_alias_file_degrades_to_no_aliases(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)
            (root / "user" / "manufacturers.json").write_text("not json", encoding="utf-8")
            (root / "default" / "bally.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_url("Bally"), "/manufacturers/bally/logo")

    def test_an_empty_alias_value_is_a_placeholder_not_an_alias(self) -> None:
        """A hand-edited TODO entry must never erase a working slug."""
        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)
            (root / "user" / "manufacturers.json").write_text(
                json.dumps({"Bally Manufacturing": "", "Bally Wulff": "  "}),
                encoding="utf-8")
            (root / "default" / "bally.png").write_bytes(b"png")

            self.assertEqual(manufacturer_logo_url("Bally Manufacturing"),
                             "/manufacturers/bally/logo")


class ReportTests(unittest.TestCase):
    def test_the_report_shows_slug_alias_and_resolution_per_name(self) -> None:
        from common.manufacturer_logos import manufacturer_report

        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)
            (root / "default" / "manufacturers.json").write_text(
                json.dumps({"Premier Technology": "gottlieb"}), encoding="utf-8")
            (root / "default" / "gottlieb.png").write_bytes(b"png")
            (root / "default" / "bally.png").write_bytes(b"png")

            rows = {row["name"]: row for row in manufacturer_report(
                ["Bally Manufacturing", "Premier Technology", "Bally Wulff"])}

        self.assertEqual(rows["Bally Manufacturing"],
                         {"name": "Bally Manufacturing", "slug": "bally",
                          "aliased_to": None, "logo": "/manufacturers/bally/logo"})
        self.assertEqual(rows["Premier Technology"]["aliased_to"], "gottlieb")
        self.assertEqual(rows["Premier Technology"]["logo"], "/manufacturers/gottlieb/logo")
        self.assertIsNone(rows["Bally Wulff"]["logo"],
                          "a miss is visible, never a fuzzy match")

    def test_the_report_exposes_an_alias_bypassing_a_users_file(self) -> None:
        """The invisible failure the report exists for: your file, shadowed."""
        from common.manufacturer_logos import manufacturer_report

        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)
            (root / "default" / "manufacturers.json").write_text(
                json.dumps({"Premier Technology": "gottlieb"}), encoding="utf-8")
            (root / "default" / "gottlieb.png").write_bytes(b"png")
            (root / "user" / "premier-technology.png").write_bytes(b"png")

            row = manufacturer_report(["Premier Technology"])[0]

        self.assertEqual(row["aliased_to"], "gottlieb")
        self.assertEqual(row["logo"], "/manufacturers/gottlieb/logo",
                         "the user's own file is not what resolves")

    def test_the_report_still_slugs_with_no_folder(self) -> None:
        from common.manufacturer_logos import manufacturer_report

        configure_manufacturer_logos(None)
        rows = manufacturer_report(["Williams Electronics", "", "  "])

        self.assertEqual(rows, [{"name": "Williams Electronics",
                                 "slug": "williams", "aliased_to": None,
                                 "logo": None}])


class ReferenceFileTests(unittest.TestCase):
    def test_the_reference_is_written_beside_the_layers(self) -> None:
        from common.manufacturer_logos import write_manufacturer_reference

        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)

            path = write_manufacturer_reference(["Bally", "Data East"])
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(path, root / "manufacturers-reference.json")
        self.assertIn("Generated by VPinFE", payload["about"])
        self.assertEqual([row["slug"] for row in payload["manufacturers"]],
                         ["bally", "data-east"])

    def test_no_folder_or_no_names_writes_nothing(self) -> None:
        from common.manufacturer_logos import write_manufacturer_reference

        configure_manufacturer_logos(None)
        self.assertIsNone(write_manufacturer_reference(["Bally"]))
        with TemporaryDirectory() as tmp:
            configure_manufacturer_logos(Path(tmp))
            self.addCleanup(configure_manufacturer_logos, None)
            self.assertIsNone(write_manufacturer_reference([]))

    def test_vps_names_come_deduped_and_sorted_from_the_cache(self) -> None:
        from common.manufacturer_logos import vps_manufacturer_names

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
    def test_the_folder_defaults_under_the_config_dir(self) -> None:
        self.assertEqual(resolve_logos_dir("", "/cfg"), Path("/cfg/manufacturer_logos"))
        self.assertEqual(resolve_logos_dir("  ", "/cfg"), Path("/cfg/manufacturer_logos"))
        self.assertEqual(resolve_logos_dir("/elsewhere/logos", "/cfg"),
                         Path("/elsewhere/logos"))


class PayloadTests(unittest.TestCase):
    def test_every_game_row_carries_the_logo_url_or_null(self) -> None:
        import json as _json

        from frontend.game_state import games_json
        from tests.support.entries import entries_for

        game = fake_game(
                   "/games/Cactus Canyon (Bally 1998)", "Cactus Canyon (Bally 1998)",
                   meta={"Info": {"Manufacturer": "Bally Manufacturing"}},
                   full_path_vpx_file="/games/Cactus Canyon (Bally 1998)/Cactus Canyon.vpx",
                   pup_pack_exists=False, alt_color_exists=False, alt_sound_exists=False,
               )

        with TemporaryDirectory() as tmp:
            root = _logos(self, tmp)
            (root / "user" / "bally.png").write_bytes(b"png")

            rows = _json.loads(games_json(entries_for([game]), contract=1))

        self.assertEqual(rows[0]["ManufacturerLogoPath"], "/manufacturers/bally/logo")


class RouteTests(unittest.TestCase):
    """What the frontend's file server answers at the URL the payload carries."""

    @classmethod
    def setUpClass(cls) -> None:
        from frontend.custom_http_server import CustomHTTPServer

        cls._tmp = TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "manufacturer_logos"
        for layer in ("default", "user"):
            (cls.root / layer).mkdir(parents=True)
        (cls.root / "default" / "bally.png").write_bytes(b"default bally")
        (cls.root / "user" / "bally.jpg").write_bytes(b"user bally")
        (cls.root / "default" / "stern.png").write_bytes(b"stern")
        configure_manufacturer_logos(cls.root)
        cls.server = CustomHTTPServer({})
        cls.server.start_file_server(port=0)
        cls.port = cls.server.file_server.server_address[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop_file_server()
        configure_manufacturer_logos(None)
        cls._tmp.cleanup()

    def _get(self, path: str) -> tuple[int, bytes, str]:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}",
                                        timeout=5) as response:
                return response.status, response.read(), response.headers["Content-Type"]
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.read(), ""

    def test_the_users_logo_is_served(self) -> None:
        self.assertEqual(self._get("/manufacturers/bally/logo"),
                         (200, b"user bally", "image/jpeg"))

    def test_a_downloaded_logo_is_served_when_the_user_has_none(self) -> None:
        self.assertEqual(self._get("/manufacturers/stern/logo")[:2], (200, b"stern"))

    def test_a_manufacturer_with_no_logo_is_a_404(self) -> None:
        self.assertEqual(self._get("/manufacturers/zaccaria/logo")[0], 404)

    def test_a_path_out_of_the_folder_is_a_404(self) -> None:
        self.assertEqual(self._get("/manufacturers/..%2Fdefault%2Fbally/logo")[0], 404)
        self.assertEqual(self._get("/manufacturers/bally/logo/extra")[0], 404)


if __name__ == "__main__":
    unittest.main()
