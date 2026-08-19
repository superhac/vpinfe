"""The devices a hub knows about.

Keyed by `install_id`, which is the only thing about a device that never changes: a
display name is meant to be renamed and an address moves with DHCP, so neither can be
the key. Follows `common/games/collection_store.py` - a small JSON file, written whole
and atomically, carrying its own schema version.

Data only. Routing a launch to a chosen device, aggregating state across devices and
resolving conflicts between them are separate decisions, and none of them are needed to
tell one device from another.
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

logger = logging.getLogger("vpinfe.common.device_registry")

DEVICE_REGISTRY_PATH = CONFIG_DIR / "devices.json"
SCHEMA = 1
SCHEMA_KEY = "schema"
DEVICES_KEY = "devices"


@dataclass(frozen=True)
class Device:
    """One device a hub has seen.

    `display_name` and `roles` are what that install last reported, cached so a registry
    can be read without asking every device. They go stale by design - the install owns
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
    def from_dict(cls, raw: dict[str, Any]) -> Device | None:
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


class DeviceRegistry:
    """Every device this hub knows, read and written whole."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else DEVICE_REGISTRY_PATH
        self._lock = threading.RLock()

    # -- reading -------------------------------------------------------------

    def devices(self) -> list[Device]:
        """Every entry, oldest first. An unreadable file is an empty registry, never an
        error: a hub with no devices is the normal case, and so is a first run."""
        with self._lock:
            return self._load()

    def get(self, install_id: str) -> Device | None:
        wanted = (install_id or "").strip()
        if not wanted:
            return None
        return next((p for p in self.devices() if p.install_id == wanted), None)

    def knows(self, install_id: str) -> bool:
        return self.get(install_id) is not None

    # -- writing -------------------------------------------------------------

    def record(self, install_id: str, *, display_name: str = "", roles=(),
               address: str = "") -> Device | None:
        """Note that a device exists, or that a known one has been heard from.

        `first_seen` is kept from the existing entry: a device is the same device
        however many times it reconnects. Everything else is refreshed, because the
        install owns those and this is only a copy of what it last said.
        """
        wanted = (install_id or "").strip()
        if not wanted:
            logger.debug("Ignoring a registry entry with no install id")
            return None

        now = utc_now_iso()
        with self._lock:
            devices = {p.install_id: p for p in self._load()}
            existing = devices.get(wanted)
            devices[wanted] = Device(
                install_id=wanted,
                display_name=display_name or (existing.display_name if existing else ""),
                roles=tuple(str(r) for r in roles) or (existing.roles if existing else ()),
                address=address or (existing.address if existing else ""),
                first_seen=existing.first_seen if existing and existing.first_seen else now,
                last_seen=now,
                extra=existing.extra if existing else {},
            )
            self._save(list(devices.values()))
            if existing is None:
                logger.info("DeviceRegistry: new device %s (%s)", wanted, display_name or "unnamed")
            return devices[wanted]

    def forget(self, install_id: str) -> bool:
        """Drop a device. Returns whether there was one to drop."""
        wanted = (install_id or "").strip()
        with self._lock:
            devices = self._load()
            remaining = [p for p in devices if p.install_id != wanted]
            if len(remaining) == len(devices):
                return False
            self._save(remaining)
            logger.info("DeviceRegistry: forgot device %s", wanted)
            return True

    # -- storage -------------------------------------------------------------

    def _load(self) -> list[Device]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("DeviceRegistry at %s is unreadable; treating it as empty", self.path)
            return []
        raw = payload.get(DEVICES_KEY) if isinstance(payload, dict) else payload
        if not isinstance(raw, list):
            return []
        return [device for device in (Device.from_dict(entry) for entry in raw
                                      if isinstance(entry, dict)) if device is not None]

    def _save(self, devices: list[Device]) -> None:
        # Never stamp a newer file down to what this build writes - that number belongs
        # to whichever VPinFE wrote it, the same rule the config store follows.
        payload = {SCHEMA_KEY: SCHEMA,
                   DEVICES_KEY: [device.as_dict() for device in devices]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(self.path,
                     lambda handle: json.dump(payload, handle, indent=2, ensure_ascii=False))


_registry: DeviceRegistry | None = None


def get_device_registry() -> DeviceRegistry:
    """The hub's registry. One per process."""
    global _registry
    if _registry is None:
        _registry = DeviceRegistry()
    return _registry


def reset_for_tests(path=None) -> None:
    global _registry
    _registry = DeviceRegistry(path) if path is not None else None
