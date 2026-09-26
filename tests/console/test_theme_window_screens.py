from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from fastapi.testclient import TestClient
from screeninfo import Monitor

import httpapi
from common import config_schema, paths
from common.config_access import DisplayConfig
from common.config_store import ConfigStore
from common.host import display_service
from common.i18n import t
from console import panel, settings
from console.data import Library
from frontend import theme_windows

WIDE = Monitor(x=0, y=0, width=2560, height=1440, width_mm=597, height_mm=336,
               name="DP-1", is_primary=True)
SMALL = Monitor(x=0, y=1440, width=1280, height=390, width_mm=300, height_mm=90,
                name="HDMI-1", is_primary=False)

DISPLAYS = next(page for _group, pages in settings.DEVICE_INDEX for page in pages
                if page[0] == "hardware.displays")


class Served:
    """The Console's client, answered by this install's API in-process."""

    def __init__(self, client: TestClient) -> None:
        self._client = client

    @staticmethod
    def _answered(response: Any) -> Any:
        if response.is_error:
            raise RuntimeError(response.text)
        return response.json()

    def config_schema(self) -> list[dict]:
        return list(self._answered(self._client.get("/config/schema"))["sections"])

    def config_values(self) -> dict:
        return dict(self._answered(self._client.get("/config"))["values"])

    def config_path_checks(self) -> list[dict]:
        return list(self._answered(self._client.get("/config/paths"))["checks"])

    def put_config(self, changes: dict) -> dict:
        return dict(self._answered(self._client.put("/config", json=changes))["values"])


class ATheme(unittest.TestCase):
    """An install whose active theme's manifest declares a topper, and whose file still
    holds a screen for an apron an earlier theme declared."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.themes = root / "themes"
        self._theme("Towers", ["playfield", "backglass", "scoreview", "topper"])
        self._theme("Plain", None)
        self.ini = root / "vpinfe.ini"
        self.enterContext(patch.object(paths, "VPINFE_INI_PATH", self.ini))
        self.enterContext(patch("frontend.theme_api.THEMES_DIR", self.themes))
        store = ConfigStore(self.ini)
        store.set_value("themes", "active", "Towers")
        store.set_value("windows.apron", "screen_id", "2")
        store.save()
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def _theme(self, name: str, windows: list[str] | None) -> None:
        folder = self.themes / name
        folder.mkdir(parents=True)
        manifest: dict[str, Any] = {"name": name, "min_vpinfe": "3.0"}
        if windows is not None:
            manifest[theme_windows.MANIFEST_KEY] = windows
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _activate(self, name: str) -> None:
        store = ConfigStore(self.ini)
        store.set_value("themes", "active", name)
        store.save()

    def _stored(self, section: str) -> str:
        return ConfigStore(self.ini).config.get(section, "screen_id", fallback="")

    def _sections(self) -> dict[str, dict]:
        return {block["name"]: block
                for block in self.client.get("/config/schema").json()["sections"]}


class ServedAsSettingsTests(ATheme):
    def test_its_own_window_is_served_after_the_three_every_theme_has(self) -> None:
        names = list(self._sections())

        self.assertEqual(names[names.index("windows.score_view") + 1], "windows.topper")
        self.assertEqual([name for name in names if name.startswith("windows.")],
                         ["windows.playfield", "windows.backglass", "windows.score_view",
                          "windows.topper"])

    def test_its_screen_is_picked_from_the_screens_like_the_others(self) -> None:
        sections = self._sections()
        [topper] = sections["windows.topper"]["options"]
        [score_view] = [option for option in sections["windows.score_view"]["options"]
                        if option["key"] == "screen_id"]

        self.assertEqual(
            {field: topper[field] for field in ("key", "type", "default", "suggest", "label")},
            {"key": "screen_id", "type": "int", "default": "",
             "suggest": config_schema.SUGGEST_SCREENS, "label": score_view["label"]})
        self.assertTrue(sections["windows.topper"]["writable"])

    def test_a_screen_set_for_it_is_where_the_frontend_reads_it(self) -> None:
        response = self.client.put("/config", json={"windows.topper": {"screen_id": 1}})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["values"]["windows.topper"], {"screen_id": 1})
        self.assertEqual(
            DisplayConfig.from_config(ConfigStore(self.ini)).window_screen_id(
                theme_windows.screen_key("topper")),
            "1")

    def test_a_window_the_theme_does_not_declare_is_neither_served_nor_set(self) -> None:
        response = self.client.put("/config", json={"windows.apron": {"screen_id": 1}})

        self.assertEqual(response.status_code, 400, response.text)
        self.assertNotIn("windows.apron", self._sections())
        self.assertNotIn("windows.apron", self.client.get("/config").json()["values"])

    def test_the_screen_stored_for_a_window_no_longer_declared_is_kept(self) -> None:
        self.client.put("/config", json={"windows.topper": {"screen_id": 1}})

        self.assertEqual(self._stored("windows.apron"), "2")

    def test_a_theme_declaring_no_windows_of_its_own_is_served_the_three(self) -> None:
        self._activate("Plain")

        self.assertEqual([name for name in self._sections() if name.startswith("windows.")],
                         ["windows.playfield", "windows.backglass", "windows.score_view"])


class DrawnOnDisplaysTests(ATheme, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.served = Served(self.client)
        self.library = Library(self.served)  # type: ignore[arg-type]
        self.enterContext(patch.object(
            settings.run, "io_bound",
            new=AsyncMock(side_effect=lambda call, *args, **kwargs: call(*args, **kwargs))))
        self.enterContext(patch.object(display_service, "get_display_monitors",
                                       return_value=[WIDE, SMALL]))
        self.enterContext(patch.object(settings, "ui"))
        self.enterContext(patch.object(settings, "page_head"))
        self.enterContext(patch.object(
            panel, "select",
            side_effect=lambda offered, value, pick, **_: SimpleNamespace(
                offered=offered, value=value, pick=pick)))
        self.facts = self.enterContext(patch.object(panel, "facts"))

    async def _drawn(self) -> list[tuple[Any, Any]]:
        self.facts.reset_mock()
        await settings._draw_system_page(self.library, Mock(), MagicMock(), DISPLAYS, {}, [])
        return list(self.facts.call_args.args[1])

    @staticmethod
    def _headings(entries: list[tuple[Any, Any]]) -> list[str]:
        return [str(value) for label, value in entries if label is panel.HEADING]

    @staticmethod
    def _under(entries: list[tuple[Any, Any]], heading: str) -> tuple[Any, Any]:
        at = entries.index((panel.HEADING, heading))
        return entries[at + 1]

    async def test_it_is_headed_by_its_name_after_score_view(self) -> None:
        headings = self._headings(await self._drawn())

        self.assertEqual(headings[headings.index(t("console.settings.section_score_view")) + 1],
                         "Topper")

    async def test_its_row_picks_from_this_machine_s_screens(self) -> None:
        entries = await self._drawn()
        label, picker = self._under(entries, "Topper")

        self.assertEqual(label, self._under(entries,
                                            t("console.settings.section_score_view"))[0])
        self.assertEqual(picker.value, "")
        self.assertEqual(set(picker.offered), {"", "0", "1"})

    async def test_a_pick_there_is_the_screen_the_frontend_opens_it_on(self) -> None:
        _, picker = self._under(await self._drawn(), "Topper")

        await picker.pick(SimpleNamespace(value="1"))

        self.assertEqual(
            DisplayConfig.from_config(ConfigStore(self.ini)).window_screen_id(
                theme_windows.screen_key("topper")),
            "1")

    async def test_a_window_no_longer_declared_is_not_drawn(self) -> None:
        self.assertNotIn("Apron", self._headings(await self._drawn()))

    async def test_choosing_another_theme_changes_what_the_page_draws(self) -> None:
        await self._drawn()
        self._activate("Plain")

        self.assertNotIn("Topper", self._headings(await self._drawn()))


if __name__ == "__main__":
    unittest.main()
