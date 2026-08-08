"""A theme registers once, and publishes on its own after that.

The registry names a theme and where it lives. Which contract each release speaks, and
which ref serves it, come from `vpinfe-theme.json` in the author's repo - so shipping a
release is a merge they make, never a pull request against whoever owns the registry.

Three things are pinned here. A build offers the newest release it can actually run and
nothing above it, which is the protection an already-shipped client cannot give itself. A
theme with no index still resolves, because that is every theme published today. And the
layout the publishing doc recommends is the one that keeps 2.x installs working.
"""

from __future__ import annotations

import unittest

from common.online import theme_releases
from common.online.theme_installer import ThemeInstallStore
from common.online.themes import ThemeRegistry

BASE = "https://github.com/someone/vpinfe-theme-example"

TWO_LINES = {"releases": [
    {"contract": 1, "ref": "refs/tags/v1.4", "version": "1.4"},
    {"contract": 2, "ref": "refs/heads/master", "version": "2.1"},
]}


class PickTests(unittest.TestCase):
    def test_a_build_takes_the_newest_release_it_can_run(self) -> None:
        releases = theme_releases.releases_in(TWO_LINES)
        self.assertEqual(theme_releases.pick(releases, 1).ref, "refs/tags/v1.4")
        self.assertEqual(theme_releases.pick(releases, 2).ref, "refs/heads/master")

    def test_a_newer_contract_does_not_pull_in_a_newer_release(self) -> None:
        """A build serving 3 runs the 2 line rather than refusing the theme."""
        releases = theme_releases.releases_in(TWO_LINES)
        self.assertEqual(theme_releases.pick(releases, 3).contract, 2)

    def test_a_theme_this_build_cannot_run_is_not_offered(self) -> None:
        """The whole point: an old build never installs a theme it would fail on."""
        only_new = theme_releases.releases_in({"releases": [{"contract": 2, "ref": "HEAD"}]})
        self.assertIsNone(theme_releases.pick(only_new, 1))

    def test_a_malformed_entry_is_skipped_not_guessed_at(self) -> None:
        declared = theme_releases.releases_in({"releases": [
            {"contract": "two", "ref": "HEAD"},
            {"contract": 1},
            "not a dict",
            {"contract": 1, "ref": "HEAD"},
        ]})
        self.assertEqual([(r.contract, r.ref) for r in declared], [(1, "HEAD")])

    def test_no_index_means_one_contract_1_line_on_the_default_branch(self) -> None:
        self.assertEqual(theme_releases.releases_in(None), [])
        fallback = theme_releases.fallback_release()
        self.assertEqual((fallback.contract, fallback.ref), (1, "HEAD"))


class UrlTests(unittest.TestCase):
    def test_the_index_is_always_read_from_the_default_branch(self) -> None:
        """It has to sit at one fixed place - it is what names every other place."""
        self.assertEqual(theme_releases.index_url(BASE),
                         f"{BASE}/raw/HEAD/vpinfe-theme.json")

    def test_a_ref_is_spelled_the_one_way_both_hosts_serve(self) -> None:
        """GitHub 404s on Forgejo's raw form and Forgejo 404s on GitHub's, so a fully
        qualified ref is reduced to a bare one, which both resolve."""
        self.assertEqual(theme_releases.bare_ref("refs/heads/v2"), "v2")
        self.assertEqual(theme_releases.bare_ref("refs/tags/v1.4"), "v1.4")
        self.assertEqual(theme_releases.bare_ref("v2"), "v2")
        self.assertEqual(theme_releases.bare_ref(""), "HEAD")
        self.assertEqual(theme_releases.bare_ref("HEAD"), "HEAD")

    def test_the_archive_follows_the_chosen_ref(self) -> None:
        """Assuming master would install the contract 2 line on a contract 1 build."""
        self.assertEqual(ThemeInstallStore.build_zip_url(BASE, "refs/tags/v1.4"),
                         f"{BASE}/archive/v1.4.zip")

    def test_head_is_not_rewritten_to_master(self) -> None:
        """Both hosts resolve HEAD to the repo's real default branch. Assuming master
        is wrong on every repo that defaults to main."""
        self.assertEqual(ThemeInstallStore.build_zip_url(BASE, "HEAD"),
                         f"{BASE}/archive/HEAD.zip")
        self.assertEqual(ThemeInstallStore.build_zip_url(BASE), f"{BASE}/archive/HEAD.zip")


class RegistryShapeTests(unittest.TestCase):
    """The client reads the registry it has today and the one it will have."""

    def test_a_theme_is_located_under_either_shape(self) -> None:
        self.assertEqual(ThemeRegistry._base_url({"url": BASE}), BASE)
        self.assertEqual(ThemeRegistry._base_url({"theme_base_url": BASE}), BASE)
        self.assertEqual(ThemeRegistry._base_url({}), "")


class ResolveTests(unittest.TestCase):
    """What the client does per theme, with the network answered from a dict."""

    def _registry(self, contract: int, responses: dict):
        registry = ThemeRegistry(serves_contract=contract)

        def fetch(url):
            if url not in responses:
                raise KeyError(url)
            return responses[url]

        registry._fetch_json = fetch
        return registry

    def test_an_index_decides_the_ref_the_manifest_is_read_from(self) -> None:
        registry = self._registry(1, {theme_releases.index_url(BASE): TWO_LINES})
        release, manifest_url, _ = registry._resolve_release(BASE, {"url": BASE})
        self.assertEqual(release.ref, "refs/tags/v1.4")
        self.assertEqual(manifest_url, f"{BASE}/raw/v1.4/manifest.json")

    def test_the_same_theme_serves_a_newer_build_its_newer_line(self) -> None:
        registry = self._registry(2, {theme_releases.index_url(BASE): TWO_LINES})
        release, manifest_url, _ = registry._resolve_release(BASE, {"url": BASE})
        self.assertEqual(release.contract, 2)
        self.assertEqual(manifest_url, f"{BASE}/raw/master/manifest.json")

    def test_a_theme_with_no_index_keeps_its_registered_manifest_url(self) -> None:
        """Twelve published themes are this case, and none of them change."""
        legacy = f"{BASE}/raw/refs/heads/master/manifest.json"
        registry = self._registry(2, {})
        release, manifest_url, _ = registry._resolve_release(
            BASE, {"theme_base_url": BASE, "theme_manifest_url": legacy})
        self.assertEqual(release.contract, 1)
        self.assertEqual(manifest_url, legacy)

    def test_an_entry_with_only_a_url_still_finds_its_manifest(self) -> None:
        registry = self._registry(2, {})
        _, manifest_url, _ = registry._resolve_release(BASE, {"url": BASE})
        self.assertEqual(manifest_url, f"{BASE}/raw/HEAD/manifest.json")

    def test_the_documented_layout_keeps_2_x_on_the_default_branch(self) -> None:
        """A 2.x build ignores all of this and installs master.zip whatever it holds.

        So the layout theme_publishing.md recommends - contract 1 on the default branch,
        contract 2 on a branch - has to be the one that resolves correctly here, or the
        advice sends authors at the shape that breaks every installed 2.x client.
        """
        index = {"releases": [
            {"contract": 1, "ref": "refs/heads/master", "version": "1.6"},
            {"contract": 2, "ref": "refs/heads/v2", "version": "2.1"},
        ]}
        registry = self._registry(2, {theme_releases.index_url(BASE): index})
        release, manifest_url, _ = registry._resolve_release(BASE, {"url": BASE})

        self.assertEqual(release.ref, "refs/heads/v2")
        self.assertEqual(manifest_url, f"{BASE}/raw/v2/manifest.json")
        self.assertEqual(ThemeInstallStore.build_zip_url(BASE, release.ref),
                         f"{BASE}/archive/v2.zip")

        # What a 2.x build gets is its own hardcoded master.zip, which this cannot change.
        # What matters here is that we do not follow it onto the contract 2 branch.
        self.assertEqual(ThemeInstallStore.build_zip_url(BASE), f"{BASE}/archive/HEAD.zip")

    def test_a_theme_needing_a_newer_build_resolves_to_nothing(self) -> None:
        index = {"releases": [{"contract": 2, "ref": "HEAD"}]}
        registry = self._registry(1, {theme_releases.index_url(BASE): index})
        release, manifest_url, _ = registry._resolve_release(BASE, {"url": BASE})
        self.assertIsNone(release)
        self.assertIsNone(manifest_url)


if __name__ == "__main__":
    unittest.main()
