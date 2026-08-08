"""Themes come from wherever the user says, not from one hardcoded catalog.

Two lists in the config file: registries, which name many themes, and repositories, which
are each one theme. Both are config-file only - a source is a url VPinFE fetches and
installs code from, so it is not a text box in the Manager UI.

What is pinned here is the behavior a second source has to have to be worth adding: one
bad source cannot cost you the others, a name means one thing, and an install that lists
nothing still starts.
"""

from __future__ import annotations

import unittest
from configparser import ConfigParser

from common.online import theme_releases, theme_sources
from common.online.theme_registry_client import ThemeRegistryError
from common.online.themes import ThemeRegistry

STOCK = "https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json"
MINE = "https://git.example.net/someone/vpinfe-theme-reference"


def _config(registries: str = "", repositories: str = "") -> ConfigParser:
    parser = ConfigParser()
    parser.add_section(theme_sources.SECTION)
    parser.set(theme_sources.SECTION, "registries", registries)
    parser.set(theme_sources.SECTION, "repositories", repositories)
    return parser


class NamingTests(unittest.TestCase):
    """A theme is called what whoever chose the name said, never what a url looks like."""

    def test_a_repo_takes_the_name_its_author_put_in_the_manifest(self) -> None:
        entry = theme_sources.repository_entry(MINE)
        self.assertEqual(theme_sources.name_of(MINE, entry, {"name": "Reference"}), "Reference")

    def test_a_registry_entry_that_names_itself_is_taken_at_its_word(self) -> None:
        """The registry shape PAR-42 moves to carries a name beside the url."""
        self.assertEqual(
            theme_sources.name_of("ignored", {"url": MINE, "name": "Aurora"}, {"name": "X"}),
            "Aurora")

    def test_the_old_registry_is_still_keyed_by_the_name(self) -> None:
        """Twelve published themes are this case, and the manifest may disagree - the
        registry says `cab` where the manifest says `Cab`, and the key is what installs."""
        self.assertEqual(theme_sources.name_of("cab", {"theme_base_url": MINE}, {"name": "Cab"}),
                         "cab")

    def test_a_manifest_with_no_usable_name_falls_back_to_the_url(self) -> None:
        entry = theme_sources.repository_entry(MINE)
        self.assertEqual(theme_sources.name_of(MINE, entry, {"name": "  "}), MINE)

    def test_a_repo_stands_in_for_a_registry_entry(self) -> None:
        """A registry entry is a name and a url, so one repo is already that shape."""
        self.assertEqual(ThemeRegistry._base_url(theme_sources.repository_entry(MINE)), MINE)


class PinTests(unittest.TestCase):
    def test_a_ref_can_be_pinned_onto_the_url(self) -> None:
        self.assertEqual(theme_sources.split_ref(f"{MINE}#v1.4"), (MINE, "v1.4"))
        self.assertEqual(theme_sources.split_ref(f"{MINE}/#v1.4"), (MINE, "v1.4"))
        self.assertEqual(theme_sources.split_ref(MINE), (MINE, ""))

    def test_the_entry_carries_the_pin_only_when_there_is_one(self) -> None:
        named = theme_sources.NAMED_BY_MANIFEST
        self.assertEqual(theme_sources.repository_entry(MINE), {"url": MINE, named: True})
        self.assertEqual(theme_sources.repository_entry(f"{MINE}#v1.4"),
                         {"url": MINE, named: True, "ref": "v1.4"})


class ConfigTests(unittest.TestCase):
    def test_both_lists_are_read_from_the_config(self) -> None:
        sources = theme_sources.from_config(_config(f"{STOCK},https://b.net/t.json", MINE))
        self.assertEqual(sources.registries, (STOCK, "https://b.net/t.json"))
        self.assertEqual(sources.repositories, (MINE,))

    def test_an_install_that_lists_nothing_is_not_an_error(self) -> None:
        sources = theme_sources.from_config(_config())
        self.assertEqual((sources.registries, sources.repositories), ((), ()))


class MergeTests(unittest.TestCase):
    def test_sources_combine_into_one_index(self) -> None:
        index = theme_sources.merge([("a", {"one": {"url": "u1"}}),
                                     ("b", {"two": {"url": "u2"}})])
        self.assertEqual(sorted(index), ["one", "two"])

    def test_the_first_mention_of_a_name_wins(self) -> None:
        """Two sources disagreeing about a name is the user's call, not ours to resolve."""
        with self.assertLogs("vpinfe.common.online.theme_sources", "WARNING") as logged:
            index = theme_sources.merge([("mine", {"Revolution": {"url": "mine"}}),
                                         ("stock", {"Revolution": {"url": "stock"}})])
        self.assertEqual(index["Revolution"]["url"], "mine")
        self.assertIn("Revolution", logged.output[0])

    def test_merging_does_not_write_into_the_entries(self) -> None:
        """`registry_info` is handed to the installer, so bookkeeping stays out of it."""
        entry = {"url": "u1"}
        index = theme_sources.merge([("a", {"one": entry})])
        self.assertEqual(index["one"], {"url": "u1"})


class LoadTests(unittest.TestCase):
    """`load_registry` over several sources, with the network answered from a dict."""

    def _registry(self, sources, responses: dict) -> ThemeRegistry:
        registry = ThemeRegistry(sources=sources)

        def fetch(url):
            if url not in responses:
                raise ThemeRegistryError(f"unreachable: {url}")
            return responses[url]

        registry._fetch_json = fetch
        return registry

    def test_a_repository_needs_no_catalog_to_be_offered(self) -> None:
        """The whole point: a theme nobody published is still installable, and it lands
        under the name its author gave it rather than one derived from the url."""
        manifest = {"name": "Reference", "version": "0.1.0", "author": "a",
                    "description": "d", "preview_image": "p.png", "type": "both",
                    "windows": ["playfield"]}
        registry = self._registry(theme_sources.ThemeSources(repositories=(MINE,)),
                                  {f"{MINE}/raw/HEAD/manifest.json": manifest})
        registry.load_registry()
        self.assertEqual(list(registry.themes_index), [MINE])  # provisional
        registry.load_theme_manifests()
        self.assertEqual(list(registry.themes), ["Reference"])  # settled

    def test_a_users_own_repo_is_contract_gated_like_any_other(self) -> None:
        """Where a theme came from must not decide what it is allowed to install.

        A repository entry resolves through the same path a registry entry does, so a
        build is protected from a theme it cannot run however the user reached it.
        """
        index = {"releases": [{"contract": 2, "ref": "v2", "version": "2.0"}]}
        sources = theme_sources.ThemeSources(repositories=(MINE,))

        serving_2 = self._registry(sources, {theme_releases.index_url(MINE): index})
        release, manifest_url, _ = serving_2._resolve_release(MINE, {"url": MINE})
        self.assertEqual((release.contract, manifest_url),
                         (2, f"{MINE}/raw/v2/manifest.json"))

        serving_1 = ThemeRegistry(sources=sources, serves_contract=1)
        serving_1._fetch_json = lambda url: index
        self.assertEqual(serving_1._resolve_release(MINE, {"url": MINE})[:2], (None, None))

    def test_a_pinned_ref_is_what_gets_installed(self) -> None:
        """Pinning is the user overriding release selection, so it wins over the index."""
        index = {"releases": [{"contract": 1, "ref": "master", "version": "1.6"}]}
        registry = self._registry(
            theme_sources.ThemeSources(repositories=(f"{MINE}#v1.4",)),
            {theme_releases.index_url(MINE): index})
        entry = theme_sources.repository_entry(f"{MINE}#v1.4")
        release, manifest_url, _ = registry._resolve_release(MINE, entry)
        self.assertEqual(release.ref, "v1.4")
        self.assertEqual(manifest_url, f"{MINE}/raw/v1.4/manifest.json")

    def test_a_pin_onto_a_declared_line_keeps_that_line_s_contract_gate(self) -> None:
        """Pinning names a ref, not a license to install what this build cannot run."""
        index = {"releases": [{"contract": 2, "ref": "refs/heads/v2", "version": "2.0"}]}
        entry = theme_sources.repository_entry(f"{MINE}#v2")

        serving_2 = self._registry(theme_sources.ThemeSources(),
                                   {theme_releases.index_url(MINE): index})
        self.assertEqual(serving_2._resolve_release(MINE, entry)[0].contract, 2)

        serving_1 = ThemeRegistry(sources=theme_sources.ThemeSources(), serves_contract=1)
        serving_1._fetch_json = lambda url: index
        self.assertEqual(serving_1._resolve_release(MINE, entry)[:2], (None, None))

    def test_a_pin_no_line_declares_is_taken_at_its_word(self) -> None:
        """No index, or a ref outside it - nothing knows better than the user here."""
        registry = self._registry(theme_sources.ThemeSources(), {})
        release, manifest_url, _ = registry._resolve_release(
            MINE, theme_sources.repository_entry(f"{MINE}#some-branch"))
        self.assertEqual((release.contract, release.ref), (1, "some-branch"))
        self.assertEqual(manifest_url, f"{MINE}/raw/some-branch/manifest.json")

    def _manifest(self, name: str, version: str = "1.0") -> dict:
        return {"name": name, "version": version, "author": "a", "description": "d",
                "preview_image": "p.png", "type": "both", "windows": ["playfield"]}

    def test_a_repo_that_turns_out_to_be_a_registry_theme_loses_to_it(self) -> None:
        """The clash only becomes visible once the manifest names it, so it is caught
        there rather than at merge, where a repository is still just a url."""
        repo = "https://git.example.net/me/my-fork"
        registry = self._registry(
            theme_sources.ThemeSources(registries=(STOCK,), repositories=(repo,)),
            {STOCK: {"themes": {"Revolution": {"url": "https://x.net/o/r"}}},
             f"{repo}/raw/HEAD/manifest.json": self._manifest("Revolution", "9.9"),
             "https://x.net/o/r/raw/HEAD/manifest.json": self._manifest("Revolution", "1.0")})
        registry.load_registry()
        with self.assertLogs("vpinfe.common.online.themes", "WARNING") as logged:
            registry.load_theme_manifests()
        self.assertEqual(list(registry.themes), ["Revolution"])
        self.assertEqual(registry.themes["Revolution"]["manifest"]["version"], "9.9")
        self.assertIn("keeping the first", logged.output[0])

    def test_which_source_wins_does_not_depend_on_who_answered_first(self) -> None:
        """Results are collected in source order, not completion order - otherwise a
        slow network would decide which of two same-named themes you got."""
        repo = "https://git.example.net/me/my-fork"
        responses = {STOCK: {"themes": {"Revolution": {"url": "https://x.net/o/r"}}},
                     f"{repo}/raw/HEAD/manifest.json": self._manifest("Revolution", "9.9"),
                     "https://x.net/o/r/raw/HEAD/manifest.json": self._manifest("Revolution")}
        for _ in range(8):
            registry = self._registry(
                theme_sources.ThemeSources(registries=(STOCK,), repositories=(repo,)),
                responses)
            registry.load_registry()
            with self.assertLogs("vpinfe.common.online.themes", "WARNING"):
                registry.load_theme_manifests()
            self.assertEqual(registry.themes["Revolution"]["manifest"]["version"], "9.9")

    def test_a_case_only_twin_is_called_out(self) -> None:
        """`cab` in the registry beside a manifest saying `Cab` installs both."""
        repo = "https://git.example.net/me/my-cab"
        registry = self._registry(
            theme_sources.ThemeSources(registries=(STOCK,), repositories=(repo,)),
            {STOCK: {"themes": {"cab": {"url": "https://x.net/o/cab"}}},
             f"{repo}/raw/HEAD/manifest.json": self._manifest("Cab"),
             "https://x.net/o/cab/raw/HEAD/manifest.json": self._manifest("cab")})
        registry.load_registry()
        with self.assertLogs("vpinfe.common.online.themes", "WARNING") as logged:
            registry.load_theme_manifests()
        self.assertEqual(sorted(registry.themes), ["Cab", "cab"])
        self.assertIn("only in case", logged.output[0])

    def test_a_dead_source_does_not_cost_the_user_the_others(self) -> None:
        with self.assertLogs("vpinfe.common.online.themes", "ERROR"):
            registry = self._registry(
                theme_sources.ThemeSources(registries=("https://gone.net/t.json", STOCK)),
                {STOCK: {"themes": {"Revolution": {"url": "u"}}}})
            registry.load_registry()
        self.assertEqual(list(registry.themes_index), ["Revolution"])

    def test_a_source_with_no_themes_object_is_reported_not_raised(self) -> None:
        with self.assertLogs("vpinfe.common.online.themes", "ERROR"):
            registry = self._registry(
                theme_sources.ThemeSources(registries=(STOCK, "https://b.net/t.json")),
                {STOCK: {"nothing": {}}, "https://b.net/t.json": {"themes": {"T": {"url": "u"}}}})
            registry.load_registry()
        self.assertEqual(list(registry.themes_index), ["T"])

    def test_two_registries_naming_the_same_theme_settle_at_merge(self) -> None:
        """Registry keys are known without the network, so that clash resolves early."""
        other = "https://b.net/t.json"
        with self.assertLogs("vpinfe.common.online.theme_sources", "WARNING"):
            registry = self._registry(
                theme_sources.ThemeSources(registries=(STOCK, other)),
                {STOCK: {"themes": {"Revolution": {"url": "first"}}},
                 other: {"themes": {"Revolution": {"url": "second"}}}})
            registry.load_registry()
        self.assertEqual(registry.themes_index["Revolution"]["url"], "first")

    def test_listing_no_sources_leaves_an_empty_index_rather_than_failing(self) -> None:
        """An offline cab that dropped the stock registry still runs its installed theme."""
        registry = self._registry(theme_sources.ThemeSources(), {})
        registry.load_registry()
        self.assertEqual(registry.themes_index, {})

    def test_every_source_failing_is_still_an_error(self) -> None:
        """Sources were listed and none answered - that is a broken install, not a choice."""
        with self.assertLogs("vpinfe.common.online.themes", "ERROR"):
            registry = self._registry(
                theme_sources.ThemeSources(registries=("https://gone.net/t.json",)), {})
            with self.assertRaises(ThemeRegistryError):
                registry.load_registry()


if __name__ == "__main__":
    unittest.main()
