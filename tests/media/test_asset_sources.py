"""The online catalogs, behind one interface.

VPinMediaDB was the first and is not the shape of the feature, so what is asserted
here is the registry's behaviour rather than any one source's: a source declares what
it can serve, a disabled one is not asked, and one that is down costs its own results
and nothing else.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from common.online import asset_sources
from common.online.asset_sources import Offer, Source


@dataclass(frozen=True)
class _Fake(Source):
    """A source with a known answer, so the registry is what is under test."""

    id: str = "fake"
    name: str = "Fake"
    url: str = "https://example.invalid/"
    kinds: frozenset[str] = field(default_factory=lambda: frozenset({"wheel"}))

    def offers(self, kind: str, vps_id: str) -> list[Offer]:
        return [Offer(source=self.id, name=f"{self.id}.png",
                      url=f"{self.url}{vps_id}.png", kind=kind)]


@dataclass(frozen=True)
class _Broken(_Fake):
    id: str = "broken"
    name: str = "Broken"

    def offers(self, kind: str, vps_id: str) -> list[Offer]:
        raise RuntimeError("that catalog is down")


class RegistryTests(unittest.TestCase):
    def _with(self, *sources: Source):
        return patch.object(asset_sources, "BUILT_IN", tuple(sources))

    def test_every_source_that_serves_the_kind_is_asked(self) -> None:
        one, two = _Fake(id="one"), _Fake(id="two")
        with self._with(one, two):
            found = asset_sources.offers("wheel", "vps-1")
        self.assertEqual([offer.source for offer in found], ["one", "two"])

    def test_a_source_that_does_not_serve_the_kind_is_skipped(self) -> None:
        """Asked about a kind it has never had, a source should cost nothing - not a
        request, and not a row saying it had nothing."""
        with self._with(_Fake(kinds=frozenset({"wheel"}))):
            self.assertEqual(asset_sources.offers("topper", "vps-1"), [])

    def test_a_source_that_is_down_costs_only_its_own_results(self) -> None:
        """One catalog being unreachable is not the others failing."""
        with self._with(_Broken(), _Fake(id="works")):
            found = asset_sources.offers("wheel", "vps-1")
        self.assertEqual([offer.source for offer in found], ["works"])

    def test_nothing_configured_means_every_source(self) -> None:
        """A fresh install should find artwork without discovering a list first."""
        with self._with(_Fake(id="one"), _Fake(id="two")):
            self.assertEqual([s.id for s in asset_sources.sources(())], ["one", "two"])

    def test_only_the_configured_sources_are_asked(self) -> None:
        with self._with(_Fake(id="one"), _Fake(id="two")):
            found = asset_sources.offers("wheel", "vps-1", ("two",))
        self.assertEqual([offer.source for offer in found], ["two"])

    def test_a_configured_name_that_is_not_a_source_is_ignored(self) -> None:
        """A typo in the setting should not silently disable everything."""
        with self._with(_Fake(id="one")):
            self.assertEqual(asset_sources.sources(("nonesuch",)), [])


class UrlTests(unittest.TestCase):
    """A URL is produced by a named source, never accepted from a caller."""

    def _with(self, *sources: Source):
        return patch.object(asset_sources, "BUILT_IN", tuple(sources))

    def test_a_named_source_produces_its_own_link(self) -> None:
        with self._with(_Fake(id="one"), _Fake(id="two")):
            offer = asset_sources.url_for("two", "wheel", "vps-9")
        self.assertEqual(offer.url, "https://example.invalid/vps-9.png")

    def test_a_source_nobody_ships_produces_nothing(self) -> None:
        with self._with(_Fake(id="one")):
            self.assertIsNone(asset_sources.url_for("elsewhere", "wheel", "vps-9"))

    def test_a_disabled_source_produces_nothing(self) -> None:
        """Turning a catalog off has to stop the fetch too, not just the listing."""
        with self._with(_Fake(id="one")):
            self.assertIsNone(
                asset_sources.url_for("one", "wheel", "vps-9", enabled=("two",)))


class VPinMediaDBTests(unittest.TestCase):
    """The one shipped source that has variants, since that is what the size means."""

    ENTRY = {"vps-1": {
        "1k": {"table": "https://example.invalid/1k/table.png"},
        "4k": {"table": "https://example.invalid/4k/table.png"},
        "wheel": "https://example.invalid/wheel.png",
    }}

    def test_every_size_is_offered_largest_first(self) -> None:
        with patch.object(asset_sources, "_manifest", return_value=self.ENTRY):
            found = asset_sources.VPinMediaDB().offers("playfield", "vps-1")
        self.assertEqual([offer.size for offer in found], ["4k", "1k"])

    def test_a_size_can_be_asked_for_by_name(self) -> None:
        with patch.object(asset_sources, "_manifest", return_value=self.ENTRY), \
                patch.object(asset_sources, "BUILT_IN", (asset_sources.VPinMediaDB(),)):
            offer = asset_sources.url_for("vpinmediadb", "playfield", "vps-1", "1k")
        self.assertEqual(offer.url, "https://example.invalid/1k/table.png")


if __name__ == "__main__":
    unittest.main()
