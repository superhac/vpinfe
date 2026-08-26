"""The places online that will give you artwork for a game, behind one interface.

A source declares which kinds it can serve and answers what it holds for one game;
everything above asks all of them and does not care which is which.

Two things hold across every source here. They are keyed by VPS id, so "which game" is
one lookup and not a search per catalog. And the URL never comes from a caller: a
source is named and produces its own link, which is what stops this being a way to
make the hub fetch whatever somebody asks it to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from common.online import vpsdb_media

logger = logging.getLogger("vpinfe.common.online.asset_sources")


@dataclass(frozen=True)
class Offer:
    """One file a source will hand over for a slot.

    `size` is that source's own word for a variant - "4k" against vpinmediadb, empty
    for a source that publishes one of a thing - and only it has to understand it.
    """

    source: str
    name: str
    url: str
    kind: str
    size: str = ""
    md5: str = ""


@dataclass(frozen=True)
class Source:
    """What a source is, apart from what it holds."""

    id: str
    name: str
    url: str
    kinds: frozenset[str] = field(default_factory=frozenset)

    def offers(self, kind: str, vps_id: str) -> list[Offer]:
        raise NotImplementedError


@dataclass(frozen=True)
class VPinMediaDB(Source):
    """superhac's catalog: one JSON manifest for everything it publishes.

    Held whole, so every size it carries can be offered rather than the one the
    display happens to be set to.
    """

    id: str = "vpinmediadb"
    name: str = "VPinMediaDB"
    url: str = "https://github.com/superhac/vpinmediadb"
    kinds: frozenset[str] = frozenset(vpsdb_media.MANIFEST_KINDS)

    def offers(self, kind: str, vps_id: str) -> list[Offer]:
        found = vpsdb_media.offered(_manifest(), vps_id).get(kind) or []
        return [Offer(source=self.id, name=str(item["url"]).rsplit("/", 1)[-1],
                      url=item["url"], kind=kind, size=item.get("size", ""),
                      md5=item.get("md5", ""))
                for item in found]


# Every source that ships. Which of them are asked is a setting; which exist is not.
# The bar for adding one: its art has to answer to a kind we have, or it would be
# offered for a slot it does not fit.
BUILT_IN: tuple[Source, ...] = (VPinMediaDB(),)


def _manifest() -> dict:
    """vpinmediadb's index, fetched once per process and kept.

    One file for the whole catalog, so re-fetching it per request would be a round
    trip to learn nothing. A failed fetch caches nothing and the next caller retries.
    """
    global _MANIFEST
    if _MANIFEST is None:
        from common.online.vpsdb_cache import VPinMediaDatabase
        _MANIFEST = VPinMediaDatabase(vpsdb_media.MANIFEST_URL).load()
    return _MANIFEST or {}


_MANIFEST: dict | None = None


def sources(enabled: tuple[str, ...] | None = None) -> list[Source]:
    """The sources to ask, in the order they were declared.

    An empty setting means all of them: a fresh install should find artwork without
    anyone having to discover a list first.
    """
    if not enabled:
        return list(BUILT_IN)
    wanted = {name.strip().lower() for name in enabled if name.strip()}
    return [source for source in BUILT_IN if source.id.lower() in wanted]


def offers(kind: str, vps_id: str, enabled: tuple[str, ...] | None = None) -> list[Offer]:
    """What every enabled source has for this kind, for this game.

    One source being down is not the others failing: a source that raises is logged
    and skipped, because a catalog that cannot be reached should cost its own results
    and nothing else.
    """
    found: list[Offer] = []
    for source in sources(enabled):
        if kind not in source.kinds:
            continue
        try:
            found.extend(source.offers(kind, vps_id))
        except Exception:
            logger.warning("Source %s could not be asked for %s", source.id, kind,
                           exc_info=True)
    return found


def url_for(source_id: str, kind: str, vps_id: str, size: str = "",
            enabled: tuple[str, ...] | None = None) -> Offer | None:
    """The offer a named source publishes, or None. The only way a URL is produced."""
    for offer in offers(kind, vps_id, enabled):
        if offer.source == source_id and (not size or offer.size == size):
            return offer
    return None
