"""A fixture extension whose Community lists derive tags and rank, and nothing real behind
them.

Kept in its own root so the suites that load every extension under `fixtures/extensions`
do not grow lists they never asked for. Its settings say which ids each list holds,
comma-separated, and whether a read fails, so a test sets up the week it wants. The two
ranked lists hold `id=rating` pairs, a rating left empty for one nobody rated.

The Ratings list also says how it stands: `status` is its line and `status_to` where the
line sends somebody, and while `waiting` holds anything its menu offers Post Now before a
link to the week. Posting empties `waiting`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

COLUMNS = [{"field": "name", "header": "Table"}, {"field": "vps_id", "header": "VPS"}]
RATED = [*COLUMNS, {"field": "rating", "header": "Rating", "kind": "number"}]
TOP = [{"key": "top", "name": "Top Rated", "ranks": True,
        "sort": [{"field": "rating", "desc": True}]}]
WEEK = "https://challenge.example/week"


def register(ctx) -> None:
    router = APIRouter()
    writing = APIRouter()

    def said(setting: str) -> list[str]:
        if ctx.config.get("fail"):
            raise HTTPException(status_code=503, detail="the fixture was asked to fail")
        return [one.strip() for one in ctx.config.get(setting).split(",") if one.strip()]

    def rows(setting: str) -> dict:
        return {"rows": [{"name": one, "vps_id": one} for one in said(setting)]}

    def rated(setting: str) -> dict:
        pairs = [one.partition("=") for one in said(setting)]
        return {"rows": [{"name": held, "vps_id": held,
                          "rating": float(rating) if rating else None}
                         for held, _, rating in pairs]}

    @router.get("/machines")
    def machines() -> dict:
        return rows("machines")

    @router.get("/releases")
    def releases() -> dict:
        return rows("releases")

    @router.get("/ratings")
    def ratings() -> dict:
        return rated("ratings")

    @router.get("/builds")
    def builds() -> dict:
        return rated("builds")

    @router.get("/ratings/about")
    def about() -> dict:
        line = ctx.config.get("status")
        acts = [{"key": "week", "label": "This Week", "url": WEEK}]
        if ctx.config.get("waiting"):
            acts.insert(0, {"key": "post", "label": "Post Now"})
        return {"status": {"text": line, "to": ctx.config.get("status_to")} if line else "",
                "acts": acts}

    @writing.post("/ratings/about/acts/{act}")
    def act(act: str) -> dict:
        if act != "post":
            raise HTTPException(404, detail="No such act")
        posted = len(ctx.config.get("waiting").split(","))
        ctx.config.set("waiting", "")
        return {"message": f"Posted {posted}"}

    ctx.add_router(router, scope=ctx.scope("read"))
    ctx.add_router(writing, scope=ctx.scope("write"))
    ctx.ui.community("machines", "/machines", title="Machines of the Month",
                     columns=COLUMNS,
                     relation={"field": "vps_id", "keys": "vps_entry"},
                     tag="Machine of the Month")
    ctx.ui.community("releases", "/releases", title="Weekly Challenge", columns=COLUMNS,
                     relation={"field": "vps_id", "keys": "vps_release"},
                     tag="Weekly Challenge")
    ctx.ui.community("ratings", "/ratings", title="Ratings", columns=RATED, views=TOP,
                     relation={"field": "vps_id", "keys": "vps_entry"},
                     about="/ratings/about")
    ctx.ui.community("builds", "/builds", title="Build Ratings", columns=RATED, views=TOP,
                     relation={"field": "vps_id", "keys": "vps_release"})
