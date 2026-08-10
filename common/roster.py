"""The players a hub knows about.

Keyed by `install_id`, which is the only thing about a player that never changes: a
display name is meant to be renamed and an address moves with DHCP, so neither can be
the key. Follows `common/games/collection_store.py` - a small JSON file, written whole
and atomically, carrying its own schema version.

Data only. Routing a launch to a chosen player, aggregating state across players and
resolving conflicts between them are separate decisions, and none of them are needed to
tell one player from another.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.atomic_write import write_atomic
from common.paths import CONFIG_DIR
from common.timestamps import utc_now_iso

logger = logging.getLogger("vpinfe.common.roster")

ROSTER_PATH = CONFIG_DIR / "players.json"
SCHEMA = 1
SCHEMA_KEY = "schema"
PLAYERS_KEY = "players"


@dataclass(frozen=True)
class Player:
    """One player a hub has seen.

    `display_name` and `roles` are what that install last reported, cached so a roster
    can be read without asking every player. They go stale by design - the install owns
    them, this is a copy.
    """

    install_id: str
    display_name: str = ""
    roles: tuple[str, ...] = ()
    address: str = ""
    first_seen: str = ""
    last_seen: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"install_id": self.install_id, "display_name": self.display_name,
                "roles": list(self.roles), "address": self.address,
                "first_seen": self.first_seen, "last_seen": self.last_seen,
                **self.extra}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Player | None:
        install_id = str(raw.get("install_id", "") or "").strip()
        if not install_id:
            return None
        known = {"install_id", "display_name", "roles", "address", "first_seen", "last_seen"}
        roles = raw.get("roles") or []
        return cls(
            install_id=install_id,
            display_name=str(raw.get("display_name", "") or ""),
            roles=tuple(str(r) for r in roles if str(r).strip()),
            address=str(raw.get("address", "") or ""),
            first_seen=str(raw.get("first_seen", "") or ""),
            last_seen=str(raw.get("last_seen", "") or ""),
            # Anything a newer build wrote is carried through rather than dropped, so a
            # downgrade does not silently strip fields it does not understand.
            extra={k: v for k, v in raw.items() if k not in known},
        )


class Roster:
    """Every player this hub knows, read and written whole."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else ROSTER_PATH
        self._lock = threading.RLock()

    # -- reading -------------------------------------------------------------

    def players(self) -> list[Player]:
        """Every entry, oldest first. An unreadable file is an empty roster, never an
        error: a hub with no players is the normal case, and so is a first run."""
        with self._lock:
            return self._load()

    def get(self, install_id: str) -> Player | None:
        wanted = (install_id or "").strip()
        if not wanted:
            return None
        return next((p for p in self.players() if p.install_id == wanted), None)

    def knows(self, install_id: str) -> bool:
        return self.get(install_id) is not None

    # -- writing -------------------------------------------------------------

    def record(self, install_id: str, *, display_name: str = "", roles=(),
               address: str = "") -> Player | None:
        """Note that a player exists, or that a known one has been heard from.

        `first_seen` is kept from the existing entry: a player is the same player
        however many times it reconnects. Everything else is refreshed, because the
        install owns those and this is only a copy of what it last said.
        """
        wanted = (install_id or "").strip()
        if not wanted:
            logger.debug("Ignoring a roster entry with no install id")
            return None

        now = utc_now_iso()
        with self._lock:
            players = {p.install_id: p for p in self._load()}
            existing = players.get(wanted)
            players[wanted] = Player(
                install_id=wanted,
                display_name=display_name or (existing.display_name if existing else ""),
                roles=tuple(str(r) for r in roles) or (existing.roles if existing else ()),
                address=address or (existing.address if existing else ""),
                first_seen=existing.first_seen if existing and existing.first_seen else now,
                last_seen=now,
                extra=existing.extra if existing else {},
            )
            self._save(list(players.values()))
            if existing is None:
                logger.info("Roster: new player %s (%s)", wanted, display_name or "unnamed")
            return players[wanted]

    def forget(self, install_id: str) -> bool:
        """Drop a player. Returns whether there was one to drop."""
        wanted = (install_id or "").strip()
        with self._lock:
            players = self._load()
            remaining = [p for p in players if p.install_id != wanted]
            if len(remaining) == len(players):
                return False
            self._save(remaining)
            logger.info("Roster: forgot player %s", wanted)
            return True

    # -- storage -------------------------------------------------------------

    def _load(self) -> list[Player]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Roster at %s is unreadable; treating it as empty", self.path)
            return []
        raw = payload.get(PLAYERS_KEY) if isinstance(payload, dict) else payload
        if not isinstance(raw, list):
            return []
        return [player for player in (Player.from_dict(entry) for entry in raw
                                      if isinstance(entry, dict)) if player is not None]

    def _save(self, players: list[Player]) -> None:
        # Never stamp a newer file down to what this build writes - that number belongs
        # to whichever VPinFE wrote it, the same rule the config store follows.
        payload = {SCHEMA_KEY: SCHEMA,
                   PLAYERS_KEY: [player.as_dict() for player in players]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(self.path,
                     lambda handle: json.dump(payload, handle, indent=2, ensure_ascii=False))


_roster: Roster | None = None


def get_roster() -> Roster:
    """The hub's roster. One per process."""
    global _roster
    if _roster is None:
        _roster = Roster()
    return _roster


def reset_for_tests(path=None) -> None:
    global _roster
    _roster = Roster(path) if path is not None else None
