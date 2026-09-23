"""What the theme listing says about where each theme came from."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from common.online import theme_ops, theme_sources

STOCK = "https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json"
REPO = "https://git.example.net/someone/vpinfe-theme-reference"


class _Registry:
    def __init__(self, themes: dict, local: dict | None = None) -> None:
        self._themes, self._local = themes, local or {}

    def get_themes(self) -> dict:
        return self._themes

    def check_for_updates(self, keys: list) -> dict:
        return {}

    def is_installed(self, key: str) -> bool:
        return False

    def local_themes(self) -> dict:
        return self._local


def _theme(source: str, info: dict) -> dict:
    return {"manifest": {"name": "Any"}, "registry_info": info, "source": source}


class WhereAThemeCameFrom(unittest.TestCase):
    def _listed(self, registry: _Registry) -> dict:
        with patch.object(theme_ops.theme_service, "load_theme_option_schema",
                          return_value=None):
            return {one["key"]: one for one in theme_ops._described(registry, active="")}

    def test_a_registry_theme_names_its_registry(self) -> None:
        listed = self._listed(_Registry({"Revolution": _theme(STOCK, {"url": "https://x.net/o/r"})}))
        self.assertEqual(listed["Revolution"]["registry"], STOCK)

    def test_a_repository_listed_by_itself_names_none(self) -> None:
        entry = _theme(REPO, theme_sources.repository_entry(REPO))
        listed = self._listed(_Registry({"Mine": entry}))
        self.assertEqual(listed["Mine"]["registry"], "")

    def test_a_theme_placed_in_the_folder_names_none(self) -> None:
        listed = self._listed(_Registry({}, local={"handmade": {"name": "Handmade"}}))
        self.assertEqual(listed["handmade"]["registry"], "")


if __name__ == "__main__":
    unittest.main()
