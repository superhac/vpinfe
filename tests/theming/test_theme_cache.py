"""The theme list kept between reads, and when each theme last changed."""

from __future__ import annotations

import unittest
from configparser import ConfigParser
from unittest.mock import patch

from common import timestamps
from common.online import theme_dates, theme_ops, theme_sync
from common.online.theme_releases import Release
from common.online.themes import ThemeRegistry
from tests.support.library import TempTree


def _registry(updated: str = "", ref: str = "HEAD") -> ThemeRegistry:
    registry = ThemeRegistry()
    registry.themes_index = {"Revolution": {"url": "https://github.com/o/r"}}
    registry.origins = {"Revolution": "https://x.net/themes.json"}
    registry.themes = {"Revolution": {
        "registry_info": {"url": "https://github.com/o/r"}, "source": "https://x.net/themes.json",
        "manifest": {"name": "Revolution", "version": "1.2"},
        "release": Release(1, ref, "1.2"), "index": None, "updated": updated}}
    return registry


class WhenAThemeLastChanged(unittest.TestCase):
    def test_github_answers_for_the_ref_and_the_date_comes_back_in_utc(self) -> None:
        asked = []

        def fetch(url: str) -> dict:
            asked.append(url)
            return {"commit": {"committer": {"date": "2026-04-29T13:26:53+02:00"}}}

        said = theme_dates.committed_at("https://github.com/owner/repo", "v2", fetch)

        self.assertEqual(["https://api.github.com/repos/owner/repo/commits/v2"], asked)
        self.assertEqual(timestamps.epoch_to_iso(timestamps.iso_to_epoch(
            "2026-04-29T11:26:53Z")), said)

    def test_forgejo_is_asked_for_its_default_branch_first(self) -> None:
        asked = []

        def fetch(url: str):
            asked.append(url)
            if url.endswith("/repos/owner/repo"):
                return {"default_branch": "main"}
            return [{"commit": {"committer": {"date": "2026-09-01T10:00:00Z"}}}]

        said = theme_dates.committed_at("https://git.example.net/owner/repo", "HEAD", fetch)

        self.assertIn("sha=main", asked[-1])
        self.assertTrue(said.startswith("2026-09-01"))

    def test_a_host_that_will_not_answer_leaves_it_blank(self) -> None:
        def refuse(url: str) -> dict:
            raise RuntimeError("403 rate limited")

        self.assertEqual("", theme_dates.committed_at("https://github.com/o/r", "", refuse))


class TheListKeptBetweenReads(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.kept = self.root / "cache" / "themes.json"
        self.sources = {"registries": ["https://x.net/themes.json"], "repositories": []}
        for target, value in (("common.online.theme_ops.THEME_CACHE_PATH", self.kept),):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("common.online.theme_ops._sources_now", lambda: self.sources)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_what_was_read_comes_back_the_same(self) -> None:
        theme_ops._keep(_registry("2026-04-29T11:26:53Z", "v2"))

        back = theme_ops._cached()

        self.assertIsNotNone(back)
        entry = back.themes["Revolution"]
        self.assertEqual((Release(1, "v2", "1.2"), "2026-04-29T11:26:53Z", "1.2"),
                         (entry["release"], entry["updated"], entry["manifest"]["version"]))

    def test_changed_sources_read_again_rather_than_answer_from_the_old_ones(self) -> None:
        theme_ops._keep(_registry())
        self.sources = {"registries": ["https://y.net/themes.json"], "repositories": []}

        self.assertIsNone(theme_ops._cached())

    def test_a_date_the_host_withheld_is_the_one_it_gave_last(self) -> None:
        fresh = _registry("")
        theme_ops._carry_dates(fresh, _registry("2026-04-29T11:26:53Z"))

        self.assertEqual("2026-04-29T11:26:53Z", fresh.themes["Revolution"]["updated"])

    def test_a_new_release_does_not_take_the_old_one_s_date(self) -> None:
        fresh = _registry("", ref="v3")
        theme_ops._carry_dates(fresh, _registry("2026-04-29T11:26:53Z", ref="v2"))

        self.assertEqual("", fresh.themes["Revolution"]["updated"])


class TheSchedule(unittest.TestCase):
    def _config(self, refresh: str, checked: str = "") -> ConfigParser:
        config = ConfigParser()
        config.add_section(theme_sync.SECTION)
        config.set(theme_sync.SECTION, "refresh", refresh)
        config.set(theme_sync.SECTION, "last_read", checked)
        return config

    def test_never_read_is_due_and_never_is_not(self) -> None:
        self.assertTrue(theme_sync.due(self._config("daily")))
        self.assertFalse(theme_sync.due(self._config("never")))

    def test_a_read_within_the_day_is_not_due_and_one_a_day_old_is(self) -> None:
        stamp = "2026-09-20T12:00:00Z"
        was = timestamps.iso_to_epoch(stamp) or 0
        config = self._config("daily", stamp)
        self.assertFalse(theme_sync.due(config, now=was + 3600))
        self.assertTrue(theme_sync.due(config, now=was + 86400))


if __name__ == "__main__":
    unittest.main()
