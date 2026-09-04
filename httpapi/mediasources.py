"""The online catalogs that will give you artwork, and what they have for a game.

VPinMediaDB was the first and is not the shape of the feature. A source declares what
it can serve and answers what it holds for one game; this reports all of them together
so a client picks a picture rather than picking a website.

Which sources are asked is a setting. Which exist is not - a source that ships is
always listed, so an install that turned one off can see that it did.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from common.config_access import MediaConfig
from common.online import asset_sources
from common.paths import get_ini_config

from . import models, scopes
from .auth import requires

logger = logging.getLogger("vpinfe.httpapi.mediasources")

router = APIRouter(prefix="/media-sources", tags=["media-sources"])


def enabled_ids() -> tuple[str, ...]:
    """The sources the owner wants asked. Empty means all of them."""
    return MediaConfig.from_config(get_ini_config()).asset_sources


@router.get("", summary="The online artwork catalogs this install knows",
            dependencies=[requires(scopes.VPS_READ)])
def list_sources() -> models.MediaSourceList:
    """Every source that ships, and whether it is one of the ones being asked.

    Disabled ones are listed rather than hidden, because "why is that catalog not
    coming up" is answered by seeing it sitting there switched off.
    """
    wanted = enabled_ids()
    asked = {source.id for source in asset_sources.sources(wanted)}
    return {"sources": [{"id": source.id, "name": source.name, "url": source.url,
                         "enabled": source.id in asked,
                         "kinds": sorted(source.kinds)}
                        for source in asset_sources.BUILT_IN]}


@router.get("/offers", summary="What the catalogs have for one game and kind",
            dependencies=[requires(scopes.VPS_READ)])
def get_offers(vps_id: str = Query(...),
               kind: str = Query(...)) -> models.MediaOfferList:
    """Asked per kind, because that is the question a slot has.

    VPS_READ rather than a scope of its own: that scope exists because the call goes
    out to a catalog on the caller's behalf, which is exactly what this is.
    """
    found = asset_sources.offers(kind, vps_id, enabled_ids())
    return {"offers": [{"source": offer.source, "name": offer.name, "url": offer.url,
                        "kind": offer.kind, "size": offer.size}
                       for offer in found]}
