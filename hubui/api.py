"""Reads the hub over its own HTTP API."""

from __future__ import annotations

import asyncio
import logging

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

    def tables(self, game_id: str) -> list[dict]:
        return self._get(f"/games/{game_id}/tables").get("tables", [])

    def media(self, game_id: str) -> dict:
        # Cached per client: /games carries VPS addon flags, not media coverage, so
        # coverage costs one call per game. 147 games measured at 1.1s, and threading
        # does not help - the hub answers these sequentially.
        if game_id not in self._media:
            self._media[game_id] = self._get(f"/games/{game_id}/media").get("media", {})
        return self._media[game_id]

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
