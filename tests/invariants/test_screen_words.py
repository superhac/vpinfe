from __future__ import annotations

import ast
import functools
import re
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests.support import trees
from tests.support.catalogs import served

CATALOG = served()
REPO = Path(__file__).resolve().parents[2]

CABINET = {
    "app.vpx.field.TableOverride.ViewCabMode.choice.2.help": "the physical cabinet",
    "app.vpx.field.TableOverride.ViewDTMode.choice.2.help": "the physical cabinet",
    "app.vpx.field.TableOverride.ViewFSSMode.choice.2.help": "the physical cabinet",
    "app.vpx.group.displays.heading.cabinet.label": "the physical cabinet the screen sits in",
    "app.vpx.group.point_of_view.heading.cabinet.label": "VPX's view for a cabinet's screen",
    "capture.outcome.closed": "someone standing at the physical cabinet closed the table",
    "config.presentation.cab_mode.description": "playing standing at the physical cabinet",
    "config.presentation.cab_mode.label": "Cabinet Mode is named for the physical cabinet",
    "config.windows.playfield.orientation.description": "how a screen is mounted in it",
    "console.themes.both": "a theme made for a cabinet or a desktop",
    "console.themes.cabinet": "a theme made for a cabinet rather than a desktop",
}

MACHINE: dict[str, str] = {
    "ext.vpinplay.error.card.no_machine_id": "VPinPlay's machineId field on a card",
}

BUILD = {
    "about.fact.build": "this VPinFE build",
    "app.vpx.no_plugins": "the VPX build beside the plugins",
    "console.assets.every_row_nothing_hidden.help": "the verb",
    "console.devices.device_s_settings_belong": "the VPinFE build a device runs",
    "console.devices.every_row_every_column.help": "the verb",
    "console.devices.newer_build": "a VPinFE build",
    "console.devices.published_build": "a VPinFE build",
    "console.devices.why_not.build_not_published_release": "this VPinFE build",
    "console.devices.why_not.build_runs_source_updates": "this VPinFE build",
    "console.devices.why_not.no_published_build_matches": "a VPinFE build",
    "console.media.every_row_nothing_hidden.help": "the verb",
    "console.sections.build": "this VPinFE build",
    "console.settings.browser_slim_build": "this VPinFE build",
    "console.sections.newer_build": "this VPinFE build",
    "console.sections.written_later_version_vpinfe": "this VPinFE build",
    "console.sections.written_older_build_can": "an older VPinFE build",
    "error.games.no_app_called_build": "this VPinFE build",
    "error.games.nothing_build_knows_plays": "this VPinFE build",
    "error.instance.no_build_for_system": "a VPinFE build",
    "error.instance.not_a_release": "this VPinFE build",
    "error.launchers.no_app_called_build": "this VPinFE build",
    "error.locations.no_location_kind_called": "this VPinFE build",
    "ext.library_importer.reason.nothing_readable": "this VPinFE build",
    "extension.reason.manifest_platform_not_offered": "this VPinFE build",
    "extension.reason.manifest_unknown_capabilities": "this VPinFE build",
    "frontend.buildmeta.build_metadata_started": "the verb",
    "frontend.mainmenu.build_metadata": "the verb",
    "frontend.mainmenu.build_metadata_options": "the verb",
    "frontend.mainmenu.building_metadata": "the verb",
    "frontend.mainmenu.start_build": "the verb",
}

LOADS = "the files a table loads"
ASSETS_PAGE = "the Assets page, of the files a table loads"

ASSET = {
    "config.general.hidden_asset_kinds.label": LOADS,
    "config.media.browse_dirs.description": LOADS,
    "config.updates.refresh_minutes.description": LOADS,
    "console.assets.assets": LOADS,
    "console.assets.assets_missing": LOADS,
    "console.assets.read_library_disk_pick": LOADS,
    "console.assets.search_assets": LOADS,
    "console.media.read_library_disk_pick": LOADS,
    "console.page.assets": ASSETS_PAGE,
    "console.section.assets": ASSETS_PAGE,
    "console.settings.page_assets": ASSETS_PAGE,
    "console.view.assets": ASSETS_PAGE,
    "console.workbench.assets": ASSETS_PAGE,
    "console.workbench.assets_2": ASSETS_PAGE,
}

WORDS = {"cabinet": CABINET, "machine": MACHINE, "build": BUILD, "asset": ASSET}

MEANT = {"cabinet": "the frontend", "machine": "a game, this device or a computer",
         "build": "a table", "asset": "file"}

# Setting names and served paths, which a person reads in a config file or a URL.
NAMED_ASSET = {
    "general.hidden_asset_kinds": LOADS,
    "network.theme_assets_port": "the theme server, named as vpin.themeAssetsPort, which shipped",
    "themeassetsport": "the theme server's port in 2.x, which shipped",
    "network.theme_assets_bind": "the theme server, named with its port",
    "/assets": LOADS,
    "/games/{game_id}/asset_source": LOADS,
    "/games/{game_id}/assets": LOADS,
    "/games/{game_id}/assets/detail": LOADS,
    "/games/{game_id}/assets/{kind}": LOADS,
    "/games/{game_id}/assets/{kind}/displaced": LOADS,
    "/games/{game_id}/assets/{kind}/import": LOADS,
    "/games/{game_id}/assets/{kind}/placements": LOADS,
    "/games/{game_id}/tables/{table_id}/assets/{kind}": LOADS,
}
PATH = re.compile(r"^/[A-Za-z_{][\w/{}.-]*$")
FRONTEND_SERVERS = ("frontend/custom_http_server.py", "frontend/runtime.py")


# What /api/v1/docs and discovery show, keyed by where the string sits: in the OpenAPI
# document, or under `discovery.` in what GET /api/v1 answers.
API_CABINET: dict[str, str] = {}

API_MACHINE = {
    "components.schemas.GameResource.description": "defines a game as the pinball machine",
}

API_BUILD = {
    "components.schemas.Action.description": "this VPinFE build",
    "components.schemas.EntryOverrides.description": "the verb",
    "components.schemas.InfoMaintenance.description": "a VPinFE build",
    "components.schemas.UpdateCheck.description": "a VPinFE build",
    "paths./collections/{name}/members/from_filters.post.description": "the verb",
    "paths./library/scan.post.summary": "the verb",
    "paths./update.get.summary": "a VPinFE build",
    "paths./update.post.description": "a VPinFE build",
    "paths./update.post.summary": "a VPinFE build",
    "paths./uploads/{upload_id}/plan.post.summary": "the verb",
}

API_WORDS = {"cabinet": API_CABINET, "machine": API_MACHINE, "build": API_BUILD}


def _says(value: Any, word: str) -> bool:
    forms = value.values() if isinstance(value, dict) else [value]
    return any(word in str(form).lower() for form in forms)


def unexplained(catalog: dict[str, Any], word: str, allowed: dict[str, str]) -> list[str]:
    return sorted(key for key, value in catalog.items()
                  if _says(value, word) and not allowed.get(key))


class EveryCatalog(unittest.TestCase):
    def test_each_use_of_the_words_is_on_its_list(self) -> None:
        for word, allowed in WORDS.items():
            with self.subTest(word=word):
                self.assertEqual(
                    unexplained(CATALOG, word, allowed), [],
                    f"say {MEANT[word]} if that is what it means; if not, add the key to "
                    f"{word.upper()} with what the word names there")

    def test_every_listed_key_still_says_its_word(self) -> None:
        for word, allowed in WORDS.items():
            with self.subTest(word=word):
                self.assertEqual(sorted(key for key in allowed
                                        if not _says(CATALOG.get(key, ""), word)), [])

    def test_the_sweep_reads_every_owner(self) -> None:
        owners = {key.split(".", 2)[0] for key in CATALOG}
        self.assertLessEqual({"app", "ext", "console", "frontend", "config"}, owners)

    def test_it_can_fail(self) -> None:
        catalog = {"a": "Shown on the Cabinet", "b": {"one": "{count} build", "other": "x"},
                   "c": "Kept", "d": "Cabinet Mode"}

        self.assertEqual(unexplained(catalog, "cabinet", {"d": "the physical cabinet"}), ["a"])
        self.assertEqual(unexplained(catalog, "build", {}), ["b"])
        self.assertEqual(unexplained(catalog, "cabinet", {"a": "", "d": "x"}), ["a"])


def served_paths(tree: ast.AST) -> set[str]:
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and PATH.match(node.value)}


def _names() -> set[str]:
    import httpapi
    from common import config_schema

    found = set()
    for option in config_schema.CONFIG_OPTIONS:
        found.add(f"{option.section}.{option.key}")
        found.update(str(alias) for alias in option.aliases or ())
        found.update(".".join(pair) for pair in option.legacy or ())
    found.update(httpapi.create_api_app().openapi()["paths"])
    for path in FRONTEND_SERVERS:
        found |= served_paths(trees.tree_for(REPO / path))
    return found


class SettingNamesAndServedPaths(unittest.TestCase):
    def test_each_that_says_asset_is_on_its_list(self) -> None:
        self.assertEqual(sorted(name for name in _names()
                                if "asset" in name.lower() and not NAMED_ASSET.get(name)), [],
                         "say file if that is what it means; if not, add it to NAMED_ASSET "
                         "with what the word names there")

    def test_every_listed_name_is_still_served(self) -> None:
        self.assertEqual(sorted(set(NAMED_ASSET) - _names()), [])

    def test_the_sweep_reads_the_frontend_s_routes_and_mounts(self) -> None:
        found = set()
        for path in FRONTEND_SERVERS:
            found |= served_paths(trees.tree_for(REPO / path))
        self.assertLessEqual({"/media/", "/manufacturers/", "/themes/"}, found)

    def test_it_would_see_a_served_path(self) -> None:
        planted = served_paths(trees.parse_snippet(
            'mount_points["/assets/"] = folder\n'
            'if request_path.startswith("/assets/"): pass\n'))

        self.assertEqual(planted, {"/assets/"})


def api_text(document: dict[str, Any]) -> dict[str, str]:
    """Every `summary` and `description` string in an OpenAPI document, at any depth, by
    where it sits: `paths./games/{game_id}.get.summary`, a parameter by its name."""
    found: dict[str, str] = {}

    def walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{where}.{key}" if where else key
                # A model field called `description` is a schema, not a string: walk into it.
                if key in ("summary", "description") and isinstance(value, str):
                    found[here] = value
                else:
                    walk(value, here)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                name = item.get("name") if isinstance(item, dict) else None
                walk(item, f"{where}[{name if isinstance(name, str) else index}]")

    walk(document, "")
    return found


@functools.cache
def _served() -> tuple[dict[str, str], frozenset[str]]:
    """The words, and the capabilities declared when they were read."""
    import httpapi
    from httpapi import capabilities, instance

    document = api_text(httpapi.create_api_app().openapi())
    declared = frozenset(capabilities._CAPABILITIES)
    # Every capability, whichever features this config switches on.
    with patch.object(capabilities, "_enabled_features", return_value=capabilities.FEATURES):
        discovery = instance.discovery_payload(httpapi.API_PREFIX, httpapi.API_VERSION)
    return {**document, **api_text({"discovery": discovery})}, declared


def _served_api_text() -> dict[str, str]:
    return _served()[0]


class TheApiDocument(unittest.TestCase):
    maxDiff = None

    def test_each_use_of_the_words_is_on_its_list(self) -> None:
        for word, allowed in API_WORDS.items():
            with self.subTest(word=word):
                self.assertEqual(
                    unexplained(_served_api_text(), word, allowed), [],
                    f"say {MEANT[word]} if that is what it means; if not, add the site to "
                    f"API_{word.upper()} with what the word names there")

    def test_every_listed_site_still_says_its_word(self) -> None:
        text = _served_api_text()
        for word, allowed in API_WORDS.items():
            with self.subTest(word=word):
                self.assertEqual(sorted(site for site in allowed
                                        if not _says(text.get(site, ""), word)), [])

    def test_the_sweep_reads_operations_parameters_and_models(self) -> None:
        sites = _served_api_text()
        self.assertTrue(any(".get.summary" in site for site in sites))
        self.assertTrue(any(".parameters[" in site for site in sites))
        self.assertTrue(any(site.startswith("components.schemas.") for site in sites))

    def test_the_sweep_reads_every_capability_discovery_can_serve(self) -> None:
        text, declared = _served()
        served = {site for site in text if site.startswith("discovery.")}
        self.assertIn("discovery.capabilities[launch].description", served)
        self.assertEqual({f"discovery.capabilities[{name}].description"
                          for name in declared}, served)

    def test_it_reads_every_depth(self) -> None:
        document = {
            "info": {"description": "I"},
            "paths": {"/a": {"get": {"summary": "S", "parameters": [
                {"name": "t", "description": "P", "schema": {"description": "Q"}}]}}},
            "components": {"schemas": {"M": {"description": "M", "properties": {
                "description": {"type": "string", "description": "F"}}}}},
        }
        self.assertEqual(api_text(document), {
            "info.description": "I",
            "paths./a.get.summary": "S",
            "paths./a.get.parameters[t].description": "P",
            "paths./a.get.parameters[t].schema.description": "Q",
            "components.schemas.M.description": "M",
            "components.schemas.M.properties.description.description": "F",
        })


if __name__ == "__main__":
    unittest.main()
