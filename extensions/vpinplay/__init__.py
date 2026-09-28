"""VPinPlay's cumulative rating, contributed to every entry, and each sharing player's
games sent as they are played.

The rating is answered from VPinPlay's table list, the one its Community list shows, never
asked of the service per game. A theme reads `entry.ext.vpinplay`, and `item.vpinplay` is
still written from it for the themes that were built before there was an `ext` slot.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from . import accounts, client, community, sending, settings

RATING_KEY = "vpinplay"
LIST_KEY = "tables"

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

    ratings = client.Ratings()
    kept = ctx.ui.kept(LIST_KEY)
    if kept is not None:
        ratings.load(kept["rows"], kept["read_at"])

    def rating_for(game: Any) -> Any:
        """VPinPlay's answer for the game's catalog id, or None."""
        return ratings.answer(str(game.get("vps_id") or "").strip())

    def read(rows: list) -> None:
        ratings.load(rows, datetime.now(UTC).isoformat(timespec="seconds")
                     .replace("+00:00", "Z"))
        ctx.entries.stale(RATING_KEY)

    ctx.entries.contribute(RATING_KEY, rating_for)

    def page_for(game: Any) -> str:
        vps_id = str(game.get("vps_id") or "").strip()
        return f"{SITE}/tables?{urlencode({'vpsid': vps_id})}" if vps_id else ""

    ctx.catalogs.contribute("vpinplay", "VPinPlay", "game", page_for)

    sender = sending.Sender(ctx, endpoint)
    ctx.events.subscribe(sending.PLAY_RECORDED, sender.played)
    ctx.events.subscribe(sending.GAME_RATED, sender.rated)
    ctx.events.subscribe(sending.SHARE_CHANGED, sender.share_changed)

    reading, writing = settings.routers(ctx, DEFAULT_ENDPOINT)
    ctx.add_router(reading, scope=ctx.scope("read"))
    ctx.add_router(writing, scope=ctx.scope("write"))
    ctx.ui.settings("/settings")

    reading, writing = accounts.routers(ctx, SITE, sender, endpoint)
    ctx.add_router(reading, scope=ctx.scope("read"))
    ctx.add_router(writing, scope=ctx.scope("write"))
    ctx.ui.account("/accounts", cards=(accounts.CARD_TYPE,), check="/available",
                   consent=(ctx.t("account.consent.identity"), ctx.t("account.consent.plays"),
                           ctx.t("account.consent.ratings")))

    ctx.add_router(community.router(endpoint, read), scope=ctx.scope("read"))
    reading, writing = community.about_routers(ctx, SITE, sender)
    ctx.add_router(reading, scope=ctx.scope("read"))
    ctx.add_router(writing, scope=ctx.scope("write"))
    ctx.ui.community(LIST_KEY, "/community/tables", title="VPinPlay",
                     columns=community.COLUMNS, views=community.VIEWS,
                     relation=community.RELATION, about="/community/tables/about")

    ctx.logger.info("Contributing ratings from %s", endpoint())
