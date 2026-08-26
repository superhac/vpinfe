"""Reads the hub over its own HTTP API."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlencode

import requests

from common.config_access import NetworkConfig
from common.paths import get_ini_config

logger = logging.getLogger("vpinfe.hubui")

_TIMEOUT = 15


def hub_base_url() -> str:
    network = NetworkConfig.from_config(get_ini_config())
    # hub_url set means this install reads another install's library; empty means it
    # holds its own, so the hub is this process.
    return (network.hub_url or f"http://127.0.0.1:{network.hub_port}").rstrip("/")


class HubClient:
    """An ordinary consumer of /api/v1, over HTTP rather than by import.

    Deliberate, and the point of the exercise: anything the Hub UI cannot do through
    this client, no third-party client can do either.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base = f"{base_url or hub_base_url()}/api/v1"
        self._session = requests.Session()
        self._media: dict[str, dict] = {}
        self._discovery: dict | None = None

    def _get(self, path: str) -> dict:
        _refuse_the_event_loop(path)
        response = self._session.get(f"{self._base}{path}", timeout=_TIMEOUT)
        response.raise_for_status()
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

    def tables(self, game_id: str) -> list[dict]:
        return self._get(f"/games/{game_id}/tables").get("tables", [])

    def media(self, game_id: str) -> dict:
        # Cached per client: /games carries VPS addon flags, not media coverage, so
        # coverage costs one call per game. 147 games measured at 1.1s, and threading
        # does not help - the hub answers these sequentially.
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
        response.raise_for_status()

    def rate(self, game_id: str, rating: int) -> None:
        _refuse_the_event_loop(f"/games/{game_id}/rating")
        response = self._session.put(f"{self._base}/games/{game_id}/rating",
                                     json={"rating": rating}, timeout=_TIMEOUT)
        response.raise_for_status()

    def launch(self, game_id: str) -> None:
        _refuse_the_event_loop(f"/games/{game_id}/launch")
        response = self._session.post(f"{self._base}/games/{game_id}/launch",
                                      json={}, timeout=_TIMEOUT)
        response.raise_for_status()

    def _post(self, path: str, body: dict) -> dict:
        _refuse_the_event_loop(path)
        response = self._session.post(f"{self._base}{path}", json=body, timeout=_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def _media_path(self, game_id: str, table_id: str, kind: str) -> str:
        """Which route places a file, which is the same thing as which tier it lands at."""
        return (f"/games/{game_id}/tables/{table_id}/media/{kind}" if table_id
                else f"/games/{game_id}/media/{kind}")

    def placements(self, game_id: str, kind: str) -> dict:
        """Where a file for this kind could land, and what each choice replaces."""
        return self._get(f"/games/{game_id}/media/{kind}/placements")

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
        """The online catalogs this hub knows, and which are being asked."""
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
        """Pull a catalog's art into the slot. The hub resolves the link itself."""
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
        response.raise_for_status()
        return response.json()

    def displaced_by(self, game_id: str, table_id: str, kind: str,
                     filename: str) -> list[str]:
        """What placing `filename` here would replace, asked before the bytes go up."""
        path = f"{self._media_path(game_id, table_id, kind)}/displaced"
        _refuse_the_event_loop(path)
        response = self._session.get(f"{self._base}{path}",
                                     params={"filename": filename}, timeout=_TIMEOUT)
        response.raise_for_status()
        return list(response.json().get("displaced") or [])

    def place_media(self, game_id: str, table_id: str, kind: str,
                    filename: str, data: bytes) -> dict:
        path = self._media_path(game_id, table_id, kind)
        _refuse_the_event_loop(path)
        response = self._session.put(f"{self._base}{path}",
                                     files={"file": (filename, data)}, timeout=_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def remove_media(self, game_id: str, table_id: str, kind: str) -> dict:
        path = self._media_path(game_id, table_id, kind)
        _refuse_the_event_loop(path)
        response = self._session.delete(f"{self._base}{path}", timeout=_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def forget_table(self, game_id: str, table_id: str) -> dict:
        """Drop the record of a table whose file is gone. The hub refuses if it is not."""
        path = f"/games/{game_id}/tables/{table_id}"
        _refuse_the_event_loop(path)
        response = self._session.delete(f"{self._base}{path}", timeout=_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def refresh_library(self) -> dict:
        """Ask the hub to look at the disk again. Returns the job to watch."""
        _refuse_the_event_loop("/library/refresh")
        response = self._session.post(f"{self._base}/library/refresh", timeout=_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def devices(self) -> list[dict]:
        """Every device the hub knows, as the hub knows them.

        This used to fold in two things the registry could not hold: the install you are
        sitting at, and the one vpx_mobile device the ini could name. The hub records
        itself at startup now, and a phone is a registry entry with a minted id, so both
        are ordinary rows and this is a plain read.
        """
        return self._get("/devices").get("devices", [])


def _refuse_the_event_loop(path: str) -> None:
    """Say so, loudly, when a hub call is about to block the server from answering it.

    These calls go to our own process. Made from the event loop they deadlock until the
    read times out, and what the user sees is the browser losing its socket - which
    reads as a crash rather than as a blocking call. It cost two rounds of chasing the
    wrong thing, so the mistake reports itself now. Every call belongs in run.io_bound.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return  # No loop here: a worker thread, which is where these belong.
    logger.error("hub ui: %s called on the event loop - wrap it in run.io_bound", path)
