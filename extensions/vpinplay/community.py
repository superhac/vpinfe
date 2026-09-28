"""VPinPlay's tables, listed under Community, and what the list's page says about who
shares with VPinPlay."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException

from common.extensions.contract import why, words

from .accounts import SEND_NOW, USER_ID, YOUR_PAGE, page_for

if TYPE_CHECKING:
    from .sending import Sender

logger = logging.getLogger(__name__)
t = words("vpinplay")

OPEN_SITE = "open_site"
# Core's name for Frontend › Players, where a line may send somebody.
PLAYERS = "players"

PAGE = 100
AT_ONCE = 8
TIMEOUT_SECONDS = 15

COLUMNS = [
    {"field": "name", "under": ["manufacturer", "year"]},
    {"field": "manufacturer"},
    {"field": "year", "kind": "number"},
    {"field": "rating", "kind": "number"},
    {"field": "ratings", "kind": "number"},
    {"field": "plays", "kind": "number"},
    {"field": "hours", "kind": "number"},
    {"field": "players", "kind": "number"},
    {"field": "last_played", "kind": "date"},
    {"field": "vps_id"},
]
_SHOWN = ["name", "rating", "ratings", "plays", "hours", "players", "last_played"]


def _view(field: str, *then: str) -> dict[str, Any]:
    return {"key": field, "columns": _SHOWN, "ranks": True,
            "sort": [{"field": one, "desc": True} for one in (field, *then)]}


VIEWS = [_view("rating", "ratings"), _view("plays"), _view("hours"), _view("last_played"),
         _view("players")]
RELATION = {"field": "vps_id", "keys": "vps_entry"}


def _utc(stamp: Any) -> str:
    said = str(stamp or "").strip()
    if not said or said.endswith("Z") or "+" in said[10:]:
        return said
    return said + "Z"


def _row(item: dict[str, Any]) -> dict[str, Any]:
    minutes = item.get("runTimeTotal") or 0
    authors = item.get("authors")
    if isinstance(authors, str):
        authors = [authors] if authors.strip() else []
    return {"name": str(item.get("name") or ""),
            "manufacturer": str(item.get("manufacturer") or ""),
            "year": item.get("year") if isinstance(item.get("year"), int) else None,
            "rating": round(float(item.get("avgRating") or 0), 1) or None,
            "average": item.get("avgRating"),
            "authors": [str(one) for one in authors] if isinstance(authors, list) else [],
            "ratings": int(item.get("ratingCount") or 0),
            "plays": int(item.get("startCountTotal") or 0),
            "hours": round(float(minutes) / 60, 1) if minutes else 0,
            "players": int(item.get("playerCount") or 0),
            "last_played": _utc(item.get("lastRun")),
            "vps_id": str(item.get("vpsId") or "")}


def _page(endpoint: str, offset: int) -> dict[str, Any]:
    query = urllib.parse.urlencode({"limit": PAGE, "offset": offset, "sort_by": "name",
                                    "sort_order": 1})
    url = f"{endpoint.rstrip('/')}/api/v1/tables-plus/search?{query}"
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as answer:
        return json.loads(answer.read().decode("utf-8"))


def _rows(said: dict[str, Any]) -> list[dict[str, Any]]:
    return [_row(one) for one in said.get("items") or [] if isinstance(one, dict)]


def tables(endpoint: str) -> list[dict[str, Any]]:
    """Every table VPinPlay lists: the first page, then every page its total calls for.
    A service that gives no total is read a page at a time until it says there is no
    more."""
    said = _page(endpoint, 0)
    rows = _rows(said)
    total = (said.get("pagination") or {}).get("total")
    if isinstance(total, int):
        with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
            for page in pool.map(lambda offset: _page(endpoint, offset),
                                 range(PAGE, total, PAGE)):
                rows += _rows(page)
        return rows
    offset = 0
    while (said.get("pagination") or {}).get("hasNext") and said.get("items"):
        offset += PAGE
        said = _page(endpoint, offset)
        rows += _rows(said)
    return rows


def _host(endpoint: str) -> str:
    try:
        return urllib.parse.urlsplit(endpoint).hostname or endpoint
    except ValueError:
        return endpoint


def router(endpoint_of: Any, on_read: Any = None) -> APIRouter:
    """`on_read(rows)` is told of every list read whole, and of no failed one."""
    reading = APIRouter()

    @reading.get("/community/tables")
    def community_tables() -> dict:
        endpoint = endpoint_of()
        try:
            rows = tables(endpoint)
        except OSError as exc:
            logger.warning("VPinPlay did not answer at %s: %s", endpoint, exc)
            raise HTTPException(status_code=502, detail=why(exc, at=endpoint)) from exc
        except ValueError as exc:
            logger.warning("VPinPlay's answer at %s could not be read: %s", endpoint, exc)
            raise HTTPException(status_code=502,
                                detail=t("error.unreadable", host=_host(endpoint))) from exc
        if on_read is not None:
            on_read(rows)
        return {"rows": rows}

    return reading


def status(ctx: Any, sender: Sender) -> dict[str, str]:
    """Who shares, by initials. Otherwise why nobody does, linking to where it is fixed."""
    roster = ctx.players.roster()
    holding = [one for one in roster if ctx.players.account(one["id"]).get(USER_ID)]
    if not holding:
        return {"text": ctx.t("community.status.no_account"), "to": PLAYERS}
    if not any(ctx.players.sharing(one["id"]) for one in holding):
        return {"text": ctx.t("community.status.share_off"), "to": PLAYERS}
    sending = sender.sharing()
    if not sending:
        return {"text": ctx.t("community.status.needs_initials"), "to": PLAYERS}
    return {"text": ctx.t("community.status.sharing", players=ctx.t(
        "community.status.list_join").join(one.initials for one in sending))}


def acts(ctx: Any, site: str, sender: Sender) -> list[dict[str, str]]:
    """Send Now while a sharing account has games waiting; the site; the owner's page
    while the owner holds a user id."""
    offered = []
    if any(sender.waiting(one.player_id) for one in sender.sharing()):
        offered.append({"key": SEND_NOW, "label": ctx.t("account.act.send_now.label")})
    offered.append({"key": OPEN_SITE, "label": ctx.t("community.act.open_site.label"),
                    "url": site})
    owner = next((one for one in ctx.players.roster() if one.get("owner")), None)
    user_id = ctx.players.account(owner["id"]).get(USER_ID, "") if owner else ""
    if user_id:
        offered.append({"key": YOUR_PAGE, "label": ctx.t("account.act.your_page.label"),
                        "url": page_for(site, user_id)})
    return offered


def about_routers(ctx: Any, site: str, sender: Sender) -> tuple[APIRouter, APIRouter]:
    """The list's line and menu, and Send Now from it."""
    reading = APIRouter()
    writing = APIRouter()

    @reading.get("/community/tables/about")
    def about() -> dict:
        return {"status": status(ctx, sender), "acts": acts(ctx, site, sender)}

    @writing.post("/community/tables/about/acts/{act}")
    def run_act(act: str) -> dict:
        if act != SEND_NOW:
            raise HTTPException(404, detail=ctx.t("error.no_act", act=act))
        went, waiting = sender.send_all()
        if waiting:
            return {"message": ctx.t("account.status.waiting", count=waiting)}
        if not went:
            return {"message": ctx.t("account.nothing_waiting")}
        return {"message": ctx.t("account.sent", count=went)}

    return reading, writing
