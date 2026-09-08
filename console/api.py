"""Reads this install over its own HTTP API."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import requests

from common.config_access import NetworkConfig
from common.paths import get_ini_config

logger = logging.getLogger("vpinfe.console")

_TIMEOUT = 15
# An import copies files, which is disk work rather than a question - a pup pack is
# gigabytes and the default would give up on it partway through.
_IMPORT_TIMEOUT = 900


def local_base_url() -> str:
    """This install's own API, always.

    It used to follow the library setting, so an install reading somebody else's catalog
    ran its whole Console against that machine - settings included, which is now exactly
    the thing configuration must not do. Nothing is lost by pinning it: the nav is
    derived from features, so an install with no library of its own has no library
    sections for a remote catalog to fill.
    """
    network = NetworkConfig.from_config(get_ini_config())
    return f"http://127.0.0.1:{network.http_port}"


class ApiError(RuntimeError):
    """What the API said went wrong, in its own words - which is what a surface shows."""


class ApiClient:
    """An ordinary consumer of /api/v1, over HTTP rather than by import.

    Deliberate, and the point of the exercise: anything the Console cannot do through
    this client, no third-party client can do either.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base = f"{base_url or local_base_url()}/api/v1"
        self._session = requests.Session()
        self._media: dict[str, dict] = {}
        self._discovery: dict | None = None

    def _answered(self, response: Any) -> None:
        """Raise what the API said, not what HTTP said.

        `raise_for_status` throws away the body, so a considered message - "No Visual
        Pinball on this machine..." - reached the panel as "501 Server Error: Not
        Implemented for url: ...", which names our own route at a user and tells them
        nothing. Every write in this client goes through here for that reason.
        """
        if response.ok:
            return
        said = ""
        try:
            said = str(((response.json() or {}).get("error") or {}).get("message") or "")
        except ValueError:
            said = ""
        raise ApiError(said or f"The API answered {response.status_code}")

    def _get(self, path: str) -> dict:
        _refuse_the_event_loop(path)
        response = self._session.get(f"{self._base}{path}", timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def discovery(self) -> dict:
        if self._discovery is None:
            self._discovery = self._get("")
        return self._discovery

    def capabilities(self) -> list[dict]:
        return self.discovery().get("capabilities") or []

    def games(self) -> list[dict]:
        return self._get("/games").get("games", [])

    def filter_axes(self) -> list[dict]:
        return self._get("/library/filters").get("axes", [])

    def game(self, game_id: str) -> dict:
        return self._get(f"/games/{game_id}")

    def all_tables(self) -> list[dict]:
        """Every table in the library, one row each, with its game's name on it."""
        return list(self._get("/tables").get("tables") or [])

    def all_media(self) -> list[dict]:
        """Every media file in the library, one row each, and one per file it lacks."""
        return self._get("/media").get("media", [])

    def all_assets(self) -> list[dict]:
        """Every asset file in the library, one row each, and one per file it lacks."""
        return self._get("/assets").get("assets", [])

    def tables(self, game_id: str) -> list[dict]:
        return self._get(f"/games/{game_id}/tables").get("tables", [])

    def media(self, game_id: str) -> dict:
        # Cached per client: /games carries VPS addon flags, not media coverage, so
        # coverage costs one call per game. 147 games measured at 1.1s, and threading
        # does not help - the server answers these sequentially.
        if game_id not in self._media:
            self._media[game_id] = self._get(f"/games/{game_id}/media").get("media", {})
        return self._media[game_id]

    def forget_media(self, game_id: str) -> None:
        """Drop the cached read after a write, so the next one sees what changed."""
        self._media.pop(game_id, None)

    def table_media(self, game_id: str, table_id: str) -> dict:
        """One build's answer, which differs from the game's only where it owns a file.

        Not cached with the rest: this is asked for one game at a time, by someone
        looking at it, rather than for the whole library on the way to a grid.
        """
        return self._get(
            f"/games/{game_id}/tables/{table_id}/media").get("media", {})

    def preferences(self, scope: str) -> dict:
        return self._get(f"/preferences/{scope}").get("value", {})

    def put_preferences(self, scope: str, value: dict) -> None:
        _refuse_the_event_loop(f"/preferences/{scope}")
        response = self._session.put(f"{self._base}/preferences/{scope}",
                                     json=value, timeout=_TIMEOUT)
        self._answered(response)

    def rate(self, game_id: str, rating: int) -> None:
        _refuse_the_event_loop(f"/games/{game_id}/rating")
        response = self._session.put(f"{self._base}/games/{game_id}/rating",
                                     json={"rating": rating}, timeout=_TIMEOUT)
        self._answered(response)

    def rate_table(self, game_id: str, table_id: str, rating: int) -> None:
        """One table's own rating, which refines its game's rather than replacing it."""
        _refuse_the_event_loop(f"/games/{game_id}/tables/{table_id}/rating")
        response = self._session.put(
            f"{self._base}/games/{game_id}/tables/{table_id}/rating",
            json={"rating": rating}, timeout=_TIMEOUT)
        self._answered(response)

    def vps_sync_state(self) -> dict:
        """How fresh the local catalog is, and whether a check is owed."""
        _refuse_the_event_loop("/vps/sync")
        response = self._session.get(f"{self._base}/vps/sync", timeout=_TIMEOUT)
        self._answered(response)
        return dict(response.json() or {})

    def sync_vps(self) -> dict:
        """Check now, whatever the schedule says. The catalog is about 7 MB."""
        _refuse_the_event_loop("/vps/sync")
        response = self._session.post(f"{self._base}/vps/sync", timeout=_TIMEOUT * 6)
        self._answered(response)
        return dict(response.json() or {})

    def vps_state(self, game_id: str) -> list[dict]:
        """Per kind: what this game holds, and what the catalog lists for it."""
        _refuse_the_event_loop(f"/games/{game_id}/vps_state")
        response = self._session.get(f"{self._base}/games/{game_id}/vps_state",
                                     timeout=_TIMEOUT)
        self._answered(response)
        return list((response.json() or {}).get("kinds") or [])

    def vps_details(self, game_id: str) -> list[dict]:
        """Which of the game's details disagree with its entry - empty for a game
        nobody has re-matched, which is nearly all of them."""
        _refuse_the_event_loop(f"/games/{game_id}/vps_details")
        response = self._session.get(f"{self._base}/games/{game_id}/vps_details",
                                     timeout=_TIMEOUT)
        self._answered(response)
        return list((response.json() or {}).get("differs") or [])

    def adopt_vps_details(self, game_id: str) -> None:
        """Take the entry's details, all of them - they are one machine's facts."""
        _refuse_the_event_loop(f"/games/{game_id}/vps_details")
        response = self._session.put(f"{self._base}/games/{game_id}/vps_details",
                                     timeout=_TIMEOUT)
        self._answered(response)

    def set_table_source(self, game_id: str, table_id: str, vps_file_id: str) -> None:
        """Bind one table to the release somebody says it is. Empty unbinds."""
        _refuse_the_event_loop(f"/games/{game_id}/tables/{table_id}/source")
        response = self._session.put(
            f"{self._base}/games/{game_id}/tables/{table_id}/source",
            json={"vps_file_id": vps_file_id}, timeout=_TIMEOUT)
        self._answered(response)

    def set_asset_source(self, game_id: str, path: str, vps_file_id: str) -> None:
        """Bind one file to the VPS record somebody says it is. Empty unbinds. The path
        is the ledger's own key - folder-relative, forward slashes."""
        _refuse_the_event_loop(f"/games/{game_id}/asset_source")
        response = self._session.put(
            f"{self._base}/games/{game_id}/asset_source",
            json={"path": path, "vps_file_id": vps_file_id}, timeout=_TIMEOUT)
        self._answered(response)

    def set_favorite(self, game_id: str, favorite: bool) -> None:
        """A game's favorite flag. Games only - you favorite a machine, not a build."""
        _refuse_the_event_loop(f"/games/{game_id}/favorite")
        response = self._session.put(f"{self._base}/games/{game_id}/favorite",
                                     json={"favorite": favorite}, timeout=_TIMEOUT)
        self._answered(response)

    def set_tags(self, game_id: str, tags: list[str]) -> None:
        """The whole set. What comes back is what was stored, which may differ - the
        the API trims and drops repeats."""
        _refuse_the_event_loop(f"/games/{game_id}/tags")
        response = self._session.put(f"{self._base}/games/{game_id}/tags",
                                     json={"tags": list(tags)}, timeout=_TIMEOUT)
        self._answered(response)

    def vps_search(self, term: str, limit: int = 40) -> list[dict]:
        """Catalog entries matching every word, already in a neutral order. No score
        comes back and none is wanted - the ranker was measured and retired."""
        _refuse_the_event_loop("/vps/search")
        response = self._session.get(f"{self._base}/vps/search",
                                     params={"q": term, "limit": limit},
                                     timeout=_TIMEOUT)
        self._answered(response)
        return list(response.json().get("results") or [])

    def vps_entry(self, vps_id: str) -> dict:
        """What a game is matched to, so a surface shows the match and not its id."""
        _refuse_the_event_loop("/vps/entry")
        response = self._session.get(
            f"{self._base}/vps/entry/{quote(vps_id, safe='')}", timeout=_TIMEOUT)
        if response.status_code == 404:
            return {}
        self._answered(response)
        return dict(response.json() or {})

    def vps_releases(self, vps_id: str, listed_as: str = "tableFiles") -> list[dict]:
        """One kind of record VPSdb lists for an entry, in the order it holds them.
        `listed_as` is VPS's own key, because one of theirs can be two of ours."""
        _refuse_the_event_loop("/vps/entry/releases")
        response = self._session.get(
            f"{self._base}/vps/entry/{quote(vps_id, safe='')}/releases",
            params={"listed_as": listed_as}, timeout=_TIMEOUT)
        if response.status_code == 404:
            return []
        self._answered(response)
        return list((response.json() or {}).get("releases") or [])

    def merge_tags(self, sources: list[str], into: str) -> int:
        """Across the library: a tag is a word the library holds, not a game's."""
        _refuse_the_event_loop("/library/tags/merge")
        response = self._session.post(f"{self._base}/library/tags/merge",
                                      json={"sources": list(sources), "into": into},
                                      timeout=_TIMEOUT)
        self._answered(response)
        return int(response.json().get("changed") or 0)

    def delete_tag(self, tag: str) -> int:
        _refuse_the_event_loop("/library/tags")
        response = self._session.delete(f"{self._base}/library/tags/{quote(tag, safe='')}",
                                        timeout=_TIMEOUT)
        self._answered(response)
        return int(response.json().get("changed") or 0)

    def reset_play_record(self, game_id: str, table_id: str = "") -> None:
        """Clear the counters, keeping what was entered. A table's record is its own."""
        path = (f"/games/{game_id}/tables/{table_id}/play_record" if table_id
                else f"/games/{game_id}/play_record")
        _refuse_the_event_loop(path)
        self._answered(self._session.delete(f"{self._base}{path}", timeout=_TIMEOUT))

    def extract_script(self, game_id: str, table_id: str) -> None:
        """Write the sidecar, which is also what makes the table run it."""
        _refuse_the_event_loop(f"/games/{game_id}/tables/{table_id}/script")
        response = self._session.post(
            f"{self._base}/games/{game_id}/tables/{table_id}/script", timeout=_TIMEOUT)
        self._answered(response)

    def delete_script(self, game_id: str, table_id: str) -> None:
        """Take the sidecar away, putting the table back on its own script."""
        _refuse_the_event_loop(f"/games/{game_id}/tables/{table_id}/script")
        response = self._session.delete(
            f"{self._base}/games/{game_id}/tables/{table_id}/script", timeout=_TIMEOUT)
        self._answered(response)

    def launch(self, game_id: str, file: str = "") -> None:
        """`file` picks one of the game's tables; empty launches its default."""
        _refuse_the_event_loop(f"/games/{game_id}/launch")
        response = self._session.post(f"{self._base}/games/{game_id}/launch",
                                      json={"file": file} if file else {},
                                      timeout=_TIMEOUT)
        self._answered(response)

    def _post(self, path: str, body: dict) -> dict:
        _refuse_the_event_loop(path)
        response = self._session.post(f"{self._base}{path}", json=body, timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def _put(self, path: str, body: dict) -> dict:
        _refuse_the_event_loop(path)
        response = self._session.put(f"{self._base}{path}", json=body, timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def _patch(self, path: str, body: dict) -> dict:
        _refuse_the_event_loop(path)
        response = self._session.patch(f"{self._base}{path}", json=body,
                                       timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def _delete(self, path: str) -> None:
        _refuse_the_event_loop(path)
        response = self._session.delete(f"{self._base}{path}", timeout=_TIMEOUT)
        self._answered(response)

    # --- collections ----------------------------------------------------------
    # Addressed by name, which is what the routes take. A rename is therefore a move,
    # and every caller here has to use the name the server last reported rather than
    # one it remembered.

    def collections(self) -> list[dict]:
        return list(self._get("/collections").get("collections") or [])

    def collection_games(self, name: str) -> list[dict]:
        """The management lens: what is in it now, and why each one is there."""
        return list(self._get(f"/collections/{quote(name, safe='')}/games")
                    .get("games") or [])

    def create_collection(self, name: str, filters: dict | None = None,
                          games: list[str] | None = None) -> dict:
        """Criteria, hand-picked games, or both - they are combinable, and the kind is
        derived from what ends up stored."""
        body: dict[str, Any] = {"name": name, "games": games or []}
        if filters is not None:
            body["filters"] = filters
        return self._post("/collections", body)

    def patch_collection(self, name: str, changes: dict) -> dict:
        """Only what is sent is written, so a rename need not restate the criteria."""
        return self._patch(f"/collections/{quote(name, safe='')}", changes)

    def delete_collection(self, name: str) -> None:
        self._delete(f"/collections/{quote(name, safe='')}")

    def add_to_collection(self, name: str, game_id: str, table: str = "",
                          after_table: str | None = None) -> None:
        """`table` holds the collection to exactly that table; without it the member
        names the game and follows whichever table is its default. `after_table` puts
        the new ref beside its sibling rather than at the end of the list."""
        self._put_empty(f"/collections/{quote(name, safe='')}/games/{game_id}",
                        {"table": table, "after_table": after_table})

    def set_member_table(self, name: str, game_id: str, table: str = "",
                         was: str = "") -> None:
        """Point an existing member at a different table, in place. `was` names the ref
        to change where a game appears more than once; empty `table` gives it back its
        default."""
        self._put_empty(f"/collections/{quote(name, safe='')}/games/{game_id}/table",
                        {"table": table, "was": was})

    def remove_from_collection(self, name: str, game_id: str,
                               table: str | None = None) -> None:
        """`None` removes every ref naming this game; a string - including "" for the
        ref that names no table - removes exactly that one."""
        suffix = "" if table is None else f"?table={quote(table, safe='')}"
        self._delete(f"/collections/{quote(name, safe='')}/games/{game_id}{suffix}")

    def set_collection_order(self, name: str, games: list[str]) -> None:
        """The whole ordered list at once - atomic, and no index arithmetic here."""
        self._put_empty(f"/collections/{quote(name, safe='')}/order",
                        {"games": games})

    def collection_members(self, name: str) -> dict:
        """Stored membership with the state of each: what is written down, not what
        resolved. The only lens that reports a member naming something gone."""
        return self._get(f"/collections/{quote(name, safe='')}/members")

    def preview_filters(self, filters: dict | None, limit: int | None = None) -> dict:
        """What a rule would match, storing nothing - so a rule can be built while its
        result is on screen instead of every experiment landing on the frontend."""
        body: dict[str, Any] = {"filters": filters or {}}
        if limit:
            body["limit"] = limit
        return self._post("/library/preview", body)

    def exclude_from_collection(self, name: str, game_id: str, table: str = "") -> None:
        self._put_empty(f"/collections/{quote(name, safe='')}/excluded/{game_id}",
                        {"table": table})

    def unexclude_from_collection(self, name: str, game_id: str,
                                  table: str | None = None) -> None:
        """`None` lifts every exclusion naming this game; a string - including "" for
        the one that names no table - lifts exactly that one."""
        suffix = "" if table is None else f"?table={quote(table, safe='')}"
        self._delete(f"/collections/{quote(name, safe='')}/excluded/{game_id}{suffix}")

    def keep_collection_result(self, name: str) -> dict:
        """Replace the criteria with what they currently match. The list stops changing
        under its owner, which is what makes it static."""
        return self._post(
            f"/collections/{quote(name, safe='')}/members/from_filters", {})

    def set_collection_image(self, name: str, path: str) -> dict:
        route = f"/collections/{quote(name, safe='')}/image"
        _refuse_the_event_loop(route)
        with open(path, "rb") as handle:
            response = self._session.put(f"{self._base}{route}",
                                         files={"file": (Path(path).name, handle)},
                                         timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def clear_collection_image(self, name: str) -> None:
        self._delete(f"/collections/{quote(name, safe='')}/image")

    def _put_empty(self, path: str, body: dict | None = None) -> None:
        """A PUT that answers 204. `_put` would raise trying to read a body."""
        _refuse_the_event_loop(path)
        response = self._session.put(f"{self._base}{path}", json=body or {},
                                     timeout=_TIMEOUT)
        self._answered(response)

    def _media_path(self, game_id: str, table_id: str, kind: str) -> str:
        """Which route places a file, which is the same thing as which tier it lands at."""
        return (f"/games/{game_id}/tables/{table_id}/media/{kind}" if table_id
                else f"/games/{game_id}/media/{kind}")

    def placements(self, game_id: str, kind: str) -> dict:
        """Where a file for this kind could land, and what each choice replaces."""
        return self._get(f"/games/{game_id}/media/{kind}/placements")

    def media_overrides(self, game_id: str) -> dict:
        """Kinds where a table has art of its own, keyed by kind."""
        return self._get(f"/games/{game_id}/media/overrides").get("overrides") or {}

    def media_detail(self, game_id: str, table_id: str, kind: str) -> dict:
        """One slot in full - its file's size and shape, and every tier holding one."""
        return self._get(f"{self._media_path(game_id, table_id, kind)}/detail")

    def browse_roots(self, game_id: str = "") -> list[dict]:
        """Where browsing this machine may start, this game's own folder included."""
        query = "?" + urlencode({"game": game_id}) if game_id else ""
        return list(self._get(f"/filesystem/roots{query}").get("roots") or [])

    def browse(self, path: str) -> dict:
        """One folder on this machine, as folders and media files."""
        return self._get("/filesystem/entries?" + urlencode({"path": path}))

    def browsed_file_url(self, path: str) -> str:
        """Where the browser can fetch a file it is showing, so it can be looked at."""
        return f"{self._base}/filesystem/file?" + urlencode({"path": path})

    def import_media(self, game_id: str, table_id: str, kind: str, path: str) -> dict:
        """Copy a file from elsewhere on this machine into the slot."""
        return self._post(f"/games/{game_id}/media/{kind}/import",
                          {"path": path, "table": table_id or ""})

    def media_sources(self) -> list[dict]:
        """The online catalogs this install knows, and which are being asked."""
        return list(self._get("/media-sources").get("sources") or [])

    def media_offers(self, vps_id: str, kind: str) -> list[dict]:
        """What every enabled catalog has for this game and kind."""
        return list(self._get("/media-sources/offers?"
                              + urlencode({"vps_id": vps_id, "kind": kind}))
                    .get("offers") or [])

    def search_vps(self, query: str, limit: int = 12) -> list[dict]:
        """VPS entries by name, for taking art from a game other than this one."""
        return list(self._get("/vps/search?" + urlencode({"q": query, "limit": limit}))
                    .get("results") or [])

    def fetch_media(self, game_id: str, table_id: str, kind: str, source: str,
                    vps_id: str, size: str = "") -> dict:
        """Pull a catalog's art into the slot. The API resolves the link itself."""
        return self._post(f"/games/{game_id}/media/{kind}/fetch",
                          {"source": source, "vps_id": vps_id, "size": size,
                           "table": table_id or ""})

    def retier_media(self, game_id: str, kind: str, from_table: str,
                     to_table: str) -> dict:
        """Rename a placed file so it serves the other tier. No bytes move."""
        path = f"/games/{game_id}/media/{kind}/retier"
        _refuse_the_event_loop(path)
        response = self._session.post(f"{self._base}{path}", json={"table": to_table},
                                      params={"table": from_table}, timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def displaced_by(self, game_id: str, table_id: str, kind: str,
                     filename: str) -> list[str]:
        """What placing `filename` here would replace, asked before the bytes go up."""
        path = f"{self._media_path(game_id, table_id, kind)}/displaced"
        _refuse_the_event_loop(path)
        response = self._session.get(f"{self._base}{path}",
                                     params={"filename": filename}, timeout=_TIMEOUT)
        self._answered(response)
        return list(response.json().get("displaced") or [])

    def place_media(self, game_id: str, table_id: str, kind: str,
                    filename: str, data: bytes) -> dict:
        path = self._media_path(game_id, table_id, kind)
        _refuse_the_event_loop(path)
        response = self._session.put(f"{self._base}{path}",
                                     files={"file": (filename, data)}, timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def remove_media(self, game_id: str, table_id: str, kind: str) -> dict:
        path = self._media_path(game_id, table_id, kind)
        _refuse_the_event_loop(path)
        response = self._session.delete(f"{self._base}{path}", timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def set_table_hidden(self, game_id: str, table_id: str, hidden: bool) -> dict:
        """Offer this table in the frontend, or stop. The file is not touched."""
        path = f"/games/{game_id}/tables/{table_id}/hidden"
        _refuse_the_event_loop(path)
        response = self._session.put(f"{self._base}{path}", json={"hidden": hidden},
                                     timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def set_default_table(self, game_id: str, table_id: str) -> dict:
        """Which table this game offers first. Empty clears the choice."""
        path = f"/games/{game_id}/default_table"
        _refuse_the_event_loop(path)
        response = self._session.put(f"{self._base}{path}", json={"table": table_id},
                                     timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def metrics(self, history_seconds: float = 0) -> dict:
        """What this machine is doing, and optionally what it has been doing.

        Reading is what fills the history, so the page polling this is the thing that
        builds the record - a machine nobody is looking at keeps none.
        """
        tail = f"?history_seconds={history_seconds}" if history_seconds else ""
        return dict(self._get(f"/metrics{tail}") or {})

    def themes(self, refresh: bool = False) -> dict:
        """Every theme this install knows, active first. `refresh` re-reads the sources,
        which reaches the network - so it is asked for rather than done on every draw."""
        return dict(self._get(f"/themes?refresh={'true' if refresh else 'false'}") or {})

    def install_theme(self, key: str) -> dict:
        """Install or update - installing over an existing copy is what an update is."""
        return dict(self._post(f"/themes/{key}/install", {}) or {})

    def remove_theme(self, key: str) -> dict:
        self._delete(f"/themes/{key}")
        return {"key": key}

    def activate_theme(self, key: str) -> dict:
        return dict(self._put("/themes/active", {"key": key}) or {})

    def theme_options(self, key: str) -> dict:
        """What a theme declares it can be configured with, and its current values."""
        return dict(self._get(f"/themes/{key}/options") or {})

    def save_theme_options(self, key: str, values: dict) -> dict:
        return dict(self._put(f"/themes/{key}/options", {"values": values}) or {})

    def gpu_metrics(self) -> dict:
        """What the graphics cards are doing, asked separately because it shells out."""
        return dict(self._get("/metrics/gpu") or {})

    def about(self, refresh: bool = False) -> dict:
        """What this install and this machine are, grouped, with the text to paste.

        The plain text comes back with the groups rather than being assembled here: the
        two would drift apart the day either end gained a field.
        """
        return dict(self._get(f"/about?refresh={'true' if refresh else 'false'}") or {})

    def launchers(self) -> dict:
        """Every launcher, the tables that deviate, and which one is the default.

        The field shape travels with each launcher, so the editor is drawn from what the
        install says a launcher of that app holds rather than from a list kept here.
        """
        return dict(self._get("/launchers") or {})

    def put_launcher(self, launcher_id: str, body: dict) -> dict:
        """One whole launcher, under an id the caller owns - which is also how one copied
        from another machine lands without being renumbered."""
        return dict(self._put(f"/launchers/{launcher_id}", body) or {})

    def delete_launcher(self, launcher_id: str) -> None:
        self._delete(f"/launchers/{launcher_id}")

    def assign_launcher(self, table_id: str, launcher_id: str) -> dict:
        """Point a table at one, or clear it back to the default with an empty id."""
        return dict(self._put(f"/launchers/mappings/{table_id}",
                              {"launcher_id": launcher_id}) or {})

    # --- imports ------------------------------------------------------------
    # The files themselves are uploaded by the browser straight to the API, so nothing
    # streams through here. What the Console does is the three steps after that: read
    # what arrived, work out where it would go, and say go.

    def upload_analysis(self, upload_id: str) -> dict:
        """What was dropped, as the install reads it."""
        return dict(self._get(f"/uploads/{upload_id}/analysis") or {})

    def upload_plan(self, upload_id: str, *, game_dir: str = "", rom_name: str = "",
                    allow_new_game: bool = False, vps_id: str = "",
                    media_kind: str = "") -> dict:
        """Where each of those files would go. Nothing is written by asking."""
        path = f"/uploads/{upload_id}/plan"
        _refuse_the_event_loop(path)
        response = self._session.post(
            f"{self._base}{path}",
            json={"game_dir": game_dir, "rom_name": rom_name,
                  "allow_new_game": allow_new_game, "vps_id": vps_id,
                  "media_kind": media_kind},
            timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def upload_import(self, upload_id: str, *, game_dir: str = "", rom_name: str = "",
                      allow_new_game: bool = False, vps_id: str = "",
                      media_kind: str = "",
                      new_game_dir_name: str | None = None,
                      selected: list[int] | None = None,
                      declared: dict | None = None) -> dict:
        """Do it. `selected` left out means every item the plan offered."""
        path = f"/uploads/{upload_id}/import"
        _refuse_the_event_loop(path)
        body: dict[str, Any] = {
            "game_dir": game_dir, "rom_name": rom_name,
            "allow_new_game": allow_new_game, "vps_id": vps_id,
            "media_kind": media_kind,
        }
        if new_game_dir_name is not None:
            body["new_game_dir_name"] = new_game_dir_name
        if selected is not None:
            body["selected"] = selected
        if declared:
            body["declared"] = declared
        response = self._session.post(f"{self._base}{path}", json=body,
                                      timeout=_IMPORT_TIMEOUT)
        self._answered(response)
        return response.json()

    def abort_upload(self, upload_id: str) -> None:
        """Throw the staged files away. Best effort - a session left behind is rubbish
        in a temp directory, not a fault worth reporting to somebody."""
        try:
            self._delete(f"/uploads/{upload_id}")
        except Exception:  # noqa: BLE001
            logger.debug("console: could not abort upload %s", upload_id, exc_info=True)

    def locations(self) -> dict:
        """Every location, with what the disk says about each one right now.

        Read fresh every time: reachable and writable are answers about this moment, and
        a cache would show that a share was mounted before it dropped.
        """
        return dict(self._get("/locations") or {})

    def put_location(self, location_id: str, body: dict) -> dict:
        return dict(self._put(f"/locations/{location_id}", body) or {})

    def delete_location(self, location_id: str) -> None:
        self._delete(f"/locations/{location_id}")

    def set_location_order(self, order: list[str]) -> dict:
        """Which location outranks which. The list order is the priority."""
        return dict(self._put("/locations/order", {"order": list(order)}) or {})

    def shadowed_here(self, location_id: str) -> list[dict]:
        """Game folders in this location whose id a higher one already answers for."""
        return list((self._get(f"/locations/{location_id}/shadowed")
                     or {}).get("shadowed") or [])

    def adopt_shadowed(self, location_id: str, path: str) -> dict:
        """Give one shadowed folder an id of its own. The only write in any of this."""
        found = f"/locations/{location_id}/shadowed/adopt"
        _refuse_the_event_loop(found)
        response = self._session.post(f"{self._base}{found}", json={"path": path},
                                      timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def set_location_write_to(self, location_id: str) -> dict:
        """Where a new game's folder is created."""
        return dict(self._put(f"/locations/{location_id}/write-to", {}) or {})

    def launcher_config(self, launcher_id: str, table: str = "",
                        scope: str = "launcher") -> dict:
        """The app's declared groups and their values at one scope."""
        return dict(self._get(
            f"/launchers/{launcher_id}/config?table={table}&scope={scope}") or {})

    def config_backups(self, launcher_id: str) -> dict:
        """Copies of the file this launcher's app keeps its settings in."""
        return dict(self._get(f"/launchers/{launcher_id}/config/backups") or {})

    def take_config_backup(self, launcher_id: str, label: str = "") -> dict:
        return dict(self._post(f"/launchers/{launcher_id}/config/backups",
                               {"label": label}) or {})

    def restore_config_backup(self, launcher_id: str, name: str) -> dict:
        return dict(self._post(
            f"/launchers/{launcher_id}/config/backups/{name}/restore", {}) or {})

    def folder_settings_reaching(self, launcher_id: str, table: str) -> dict:
        """What a folder currently gives this table, for the confirm shown before a
        table takes settings of its own."""
        return dict((self._get(
            f"/launchers/{launcher_id}/config/reaching?table={table}") or {}
        ).get("reaching") or {})

    def write_launcher_config(self, launcher_id: str, values: dict, *,
                              table: str = "", scope: str = "launcher",
                              seed: bool = False) -> dict:
        return dict(self._put(f"/launchers/{launcher_id}/config",
                              {"values": values, "table": table, "scope": scope,
                               "seed": seed}) or {})

    def config_schema(self) -> list[dict]:
        """Every setting this install has, sectioned. Read from the install rather than
        carried here, so a client cannot offer a setting the install does not have."""
        return list(self._get("/config/schema").get("sections") or [])

    def config_values(self) -> dict:
        """What it is set to, typed - a bool arrives as a bool."""
        return dict(self._get("/config").get("values") or {})

    def library_policy(self) -> dict:
        """What this library collects. The library's answer, not this machine's - a
        device reading a remote library gets that library's."""
        return dict(self._get("/library/policy") or {})

    def put_library_policy(self, changes: dict) -> dict:
        """A patch. Only the keys sent are written."""
        return dict(self._put("/library/policy", changes) or {})

    def config_path_checks(self) -> list[dict]:
        """Whether each path setting finds anything on the machine holding it. Stats the
        disk, so it is answered by that install and not worked out from the value."""
        return list(self._get("/config/paths").get("checks") or [])

    def put_config(self, changes: dict) -> dict:
        """A patch, section then key. Refused whole if any key is unknown."""
        return dict(self._put("/config", changes).get("values") or {})

    def set_game_overrides(self, game_id: str, changes: dict) -> dict:
        """What the user says about the machine. Only the keys sent are written, so
        two surfaces editing different fields do not overwrite each other."""
        return self._put(f"/games/{game_id}/overrides", changes)

    def set_table_overrides(self, game_id: str, table_id: str, changes: dict) -> dict:
        """What the user says about one file. Same patch shape as the game's."""
        return self._put(f"/games/{game_id}/tables/{table_id}/overrides", changes)

    def launch_apps(self) -> list[dict]:
        """The programs that play something in this library, read rather than carried:
        a client with its own copy of the list is a second place for it to be wrong."""
        return list(self._get("/tables/apps").get("apps") or [])

    def add_keyed_table(self, game_id: str, app: str, key: str) -> dict:
        """Record something this game holds that has no file, by the name its program
        knows it by. Nothing scans one of these into existence."""
        path = f"/games/{game_id}/tables"
        _refuse_the_event_loop(path)
        response = self._session.post(f"{self._base}{path}",
                                      json={"app": app, "key": key}, timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def add_referenced_table(self, game_id: str, file_path: str) -> dict:
        """Point this game at a file that is not in its folder."""
        path = f"/games/{game_id}/tables"
        _refuse_the_event_loop(path)
        response = self._session.post(f"{self._base}{path}",
                                      json={"path": file_path}, timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def contain_table(self, game_id: str, table_id: str) -> dict:
        """Copy a referenced file into the game folder and stop pointing at it."""
        path = f"/games/{game_id}/tables/{table_id}/contain"
        _refuse_the_event_loop(path)
        response = self._session.post(f"{self._base}{path}", timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def forget_table(self, game_id: str, table_id: str) -> dict:
        """Drop the record of a table whose file is gone. The API refuses if it is not."""
        path = f"/games/{game_id}/tables/{table_id}"
        _refuse_the_event_loop(path)
        response = self._session.delete(f"{self._base}{path}", timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def actions(self) -> list[dict]:
        """What this install can be asked to do to itself, offered or not."""
        return list(self._get("/actions").get("actions") or [])

    def perform_action(self, scope: str, action: str, reason: str = "") -> dict:
        """Do one of them. The confirm has already been put to the person who asked -
        this is the call that follows their yes."""
        return self._post("/actions", {"scope": scope, "action": action,
                                       "reason": reason or "asked from the Console"})

    def logs(self, limit: int = 200, level: str = "", contains: str = "",
             source: str = "") -> dict:
        """Recent records from this install's own log, oldest first, with the list of
        files it could have come from."""
        query = urlencode({"limit": limit, "level": level, "contains": contains,
                           "source": source})
        return self._get(f"/logs?{query}")

    def update_check(self) -> dict:
        """Whether a newer build is published. Reaches the network on the server's side."""
        return self._get("/update")

    def forget_device(self, device_id: str) -> None:
        """Drop a device from the registry. It answers 204, so nothing is read."""
        _refuse_the_event_loop(f"/devices/{device_id}")
        response = self._session.delete(f"{self._base}/devices/{quote(device_id)}",
                                        timeout=_TIMEOUT)
        self._answered(response)

    def discovered_installs(self) -> list[dict]:
        """Every install announcing itself on this network, as it stands. Read when a
        page draws rather than cached: a machine is switched on while somebody is
        looking at the list."""
        return list(self._get("/devices/discovered").get("installs") or [])

    def probe_devices(self) -> list[dict]:
        """Ask every device whether it is there. Slower than an ordinary read - it dials
        each one - so the timeout is the number of them times their own."""
        _refuse_the_event_loop("/devices/probe")
        response = self._session.post(f"{self._base}/devices/probe",
                                      timeout=_TIMEOUT * 4)
        self._answered(response)
        return list((response.json() or {}).get("probes") or [])

    def perform_update(self, *, stop_table: bool = False) -> dict:
        """Take the published build. The install goes down to do it, so this is the last
        call that install answers - a failure afterwards is the update working."""
        return self._post("/update", {"stop_table": stop_table})

    def play_state(self) -> dict:
        """What the play host is doing. `launching` stays true for as long as a table
        is up, not just while it is starting."""
        return self._get("/play/state")

    def job(self, job_id: str) -> dict:
        """One run of slow work, for watching a particular one to its end."""
        return self._get(f"/jobs/{job_id}")

    def jobs(self) -> list[dict]:
        """Runs of slow work, running first. Read on a timer while one is going."""
        return self._get("/jobs").get("jobs", [])

    def refresh_library(self) -> dict:
        """Ask the install to look at the disk again. Returns the job to watch."""
        _refuse_the_event_loop("/library/refresh")
        response = self._session.post(f"{self._base}/library/refresh", timeout=_TIMEOUT)
        self._answered(response)
        return response.json()

    def devices(self) -> list[dict]:
        """Every device this install knows, as it knows them.

        This used to fold in two things the registry could not hold: the install you are
        sitting at, and the one vpx_mobile device the ini could name. The registry records
        itself at startup now, and a phone is a registry entry with a minted id, so both
        are ordinary rows and this is a plain read.
        """
        return self._get("/devices").get("devices", [])


def _refuse_the_event_loop(path: str) -> None:
    """Say so, loudly, when an API call is about to block the server from answering it.

    These calls go to our own process. Made from the event loop they deadlock until the
    read times out, and what the user sees is the browser losing its socket - which
    reads as a crash rather than as a blocking call. It cost two rounds of chasing the
    wrong thing, so the mistake reports itself now. Every call belongs in run.io_bound.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return  # No loop here: a worker thread, which is where these belong.
    logger.error("console: %s called on the event loop - wrap it in run.io_bound", path)
