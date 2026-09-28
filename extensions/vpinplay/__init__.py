"""VPinPlay's cumulative rating, contributed to every entry, and each sharing player's
games sent as they are played.

Core makes the rating call. Leaving it to the browser hands the endpoint to the page, and
every window on a cabinet then asks the same question about the same game and loses the
answer on each reload. A theme reads `entry.ext.vpinplay`, and `item.vpinplay` is still
written from it for the themes that were built before there was an `ext` slot.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from . import accounts, client, community, sending, settings

# What the setting is called here. Core handed it over from its own configuration when
# this extension first loaded, so an install that was already using VPinPlay finds it
# already set.
ENDPOINT_KEY = "endpoint"

# Where VPinPlay lives unless somebody has said otherwise. The same default core carried,
# so an install that never changed it needs nothing handed over at all.
DEFAULT_ENDPOINT = "https://api.vpinplay.com:8888"
# Where a person reads about a table, which is not where this install talks to.
SITE = "https://www.vpinplay.com"


def register(ctx: Any) -> None:
    accounts.move_owner_account(ctx)

    def endpoint() -> str:
        return str(ctx.config.get(ENDPOINT_KEY, "") or DEFAULT_ENDPOINT)

    def rating_for(game: Any) -> Any:
        """What VPinPlay says about one game, or None.

        Keyed on the catalog id, because that is what VPinPlay knows a table by. A game
        no catalog has matched has nothing to ask about, which is not a failure.
        """
        vps_id = str(game.get("vps_id") or "").strip()
        if not vps_id:
            return None
        return client.fetch(endpoint(), vps_id)

    ctx.entries.contribute("vpinplay", rating_for)

    def page_for(game: Any) -> str:
        vps_id = str(game.get("vps_id") or "").strip()
        return f"{SITE}/tables?{urlencode({'vpsid': vps_id})}" if vps_id else ""

    ctx.catalogs.contribute("vpinplay", "VPinPlay", "game", page_for)

    sender = sending.Sender(ctx, endpoint)
    ctx.events.subscribe(sending.PLAY_RECORDED, sender.played)
    ctx.events.subscribe(sending.GAME_RATED, sender.rated)

    reading, writing = settings.routers(ctx, DEFAULT_ENDPOINT)
    ctx.add_router(reading, scope=ctx.scope("read"))
    ctx.add_router(writing, scope=ctx.scope("write"))
    ctx.ui.settings("/settings")

    reading, writing = accounts.routers(ctx, SITE, sender)
    ctx.add_router(reading, scope=ctx.scope("read"))
    ctx.add_router(writing, scope=ctx.scope("write"))
    ctx.ui.account("/accounts", cards=(accounts.CARD_TYPE,))

    ctx.add_router(community.router(endpoint), scope=ctx.scope("read"))
    ctx.ui.community("tables", "/community/tables", title="VPinPlay",
                     columns=community.COLUMNS, views=community.VIEWS,
                     relation=community.RELATION)

    ctx.logger.info("Contributing ratings from %s", endpoint())
