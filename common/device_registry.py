"""The devices a hub knows about.

Keyed by `device_id`, which is the only thing about a device that never changes: a
display name is meant to be renamed and an address moves with DHCP, so neither can be
the key. Follows `common/games/collection_store.py` - a small JSON file, written whole
and atomically, carrying its own schema version.

For a VPinFE install `device_id` *is* its `install_id`, which is what makes attribution
work: an event carries the `install_id` it happened on, and that value finds the entry.
They are two names because they answer different questions - `install_id` is what an
installation calls itself, `device_id` is what this hub files it under - and because a
device that is not an install has the second and never the first.

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
from common.install_identity import mint_id
from common.paths import CONFIG_DIR
from common.timestamps import utc_now_iso

logger = logging.getLogger("vpinfe.common.device_registry")

DEVICE_REGISTRY_PATH = CONFIG_DIR / "devices.json"
SCHEMA = 1
SCHEMA_KEY = "schema"
DEVICES_KEY = "devices"
MIGRATIONS_KEY = "migrations"

# What a device is, as a closed set. A VPinFE install runs our code and answers for
# itself; a phone running VPX Mobile never does, and the hub holds everything known
# about it. Closed because a consumer switches on this - an unrecognized value would
# reach a UI as a device it has no idea how to talk to.
KIND_VPINFE = "vpinfe"
KIND_VPX_MOBILE = "vpx_mobile"
KINDS = (KIND_VPINFE, KIND_VPX_MOBILE)


def mint_device_id() -> str:
    """An id for a device that cannot offer one. Same generator install ids use, so the
    two are indistinguishable and a device that later gains an install id is not a new
    device. Minted once, when the device is added, and never again."""
    return mint_id()


def _as_port(raw: Any) -> int:
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _known_kind(raw: Any) -> str:
    value = str(raw or "").strip()
    return value if value in KINDS else KIND_VPINFE


@dataclass(frozen=True)
class Device:
    """One device a hub has seen.

    `display_name` and `roles` are what that install last reported, cached so a registry
    can be read without asking every device. They go stale by design - the install owns
    them, this is a copy.
    """

    device_id: str
    kind: str = KIND_VPINFE
    display_name: str = ""
    roles: tuple[str, ...] = ()
    address: str = ""
    # Declared by the device, because the socket a hub reads the address off says where a
    # request came from and never what that machine listens on. 0 means it did not say -
    # an entry written before installs sent one, or a device that cannot be dialed back.
    port: int = 0
    first_seen: str = ""
    last_seen: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"device_id": self.device_id, "kind": self.kind,
                "display_name": self.display_name,
                "roles": list(self.roles), "address": self.address, "port": self.port,
                "first_seen": self.first_seen, "last_seen": self.last_seen,
                **self.extra}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Device | None:
        device_id = str(raw.get("device_id", "") or "").strip()
        if not device_id:
            return None
        known = {"device_id", "kind", "display_name", "roles", "address", "port",
                 "first_seen", "last_seen"}
        roles = raw.get("roles") or []
        return cls(
            device_id=device_id,
            # An entry stored before kind existed, or by a build that knows a kind this
            # one does not: read as vpinfe rather than dropped, because the entry is
            # still a real device and losing it is worse than mislabelling it.
            kind=_known_kind(raw.get("kind")),
            display_name=str(raw.get("display_name", "") or ""),
            roles=tuple(str(r) for r in roles if str(r).strip()),
            address=str(raw.get("address", "") or ""),
            port=_as_port(raw.get("port")),
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

    def get(self, device_id: str) -> Device | None:
        wanted = (device_id or "").strip()
        if not wanted:
            return None
        return next((p for p in self.devices() if p.device_id == wanted), None)

    def knows(self, device_id: str) -> bool:
        return self.get(device_id) is not None

    # -- writing -------------------------------------------------------------

    def record(self, device_id: str, *, kind: str = "", display_name: str = "",
               roles=(), address: str = "", port: int = 0) -> Device | None:
        """Note that a device exists, or that a known one has been heard from.

        `first_seen` is kept from the existing entry: a device is the same device
        however many times it reconnects. Everything else is refreshed, because the
        install owns those and this is only a copy of what it last said.

        `kind` defaults to empty rather than to vpinfe so that a caller updating only an
        address does not restate it. A phone is written once by a person and updated
        afterwards by whatever learns where it is; defaulting would turn it back into an
        install on that second write, silently.
        """
        wanted = (device_id or "").strip()
        if not wanted:
            logger.debug("Ignoring a registry entry with no device id")
            return None

        now = utc_now_iso()
        with self._lock:
            devices = {p.device_id: p for p in self._load()}
            existing = devices.get(wanted)
            devices[wanted] = Device(
                device_id=wanted,
                kind=kind or (existing.kind if existing else KIND_VPINFE),
                display_name=display_name or (existing.display_name if existing else ""),
                roles=tuple(str(r) for r in roles) or (existing.roles if existing else ()),
                address=address or (existing.address if existing else ""),
                port=port or (existing.port if existing else 0),
                first_seen=existing.first_seen if existing and existing.first_seen else now,
                last_seen=now,
                extra=existing.extra if existing else {},
            )
            self._save(list(devices.values()))
            if existing is None:
                logger.info("DeviceRegistry: new device %s (%s)", wanted, display_name or "unnamed")
            return devices[wanted]

    def forget(self, device_id: str) -> bool:
        """Drop a device. Returns whether there was one to drop."""
        wanted = (device_id or "").strip()
        with self._lock:
            devices = self._load()
            remaining = [p for p in devices if p.device_id != wanted]
            if len(remaining) == len(devices):
                return False
            self._save(remaining)
            logger.info("DeviceRegistry: forgot device %s", wanted)
            return True

    # -- one-time conversions ------------------------------------------------

    def has_migrated(self, name: str) -> bool:
        """Whether this file has already been through the named conversion."""
        return name in self._stored_migrations()

    def record_migration(self, name: str) -> None:
        """Say it has, so it is never done to a user's file twice."""
        with self._lock:
            names = self._stored_migrations()
            if name in names:
                return
            self._save(self._load(), migrations=names + [name])

    def _stored_migrations(self) -> list[str]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        raw = payload.get(MIGRATIONS_KEY) if isinstance(payload, dict) else None
        return [str(name) for name in raw or [] if str(name).strip()]

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

    def _save(self, devices: list[Device], migrations: list[str] | None = None) -> None:
        # Never stamp a newer file down to what this build writes - that number belongs
        # to whichever VPinFE wrote it, the same rule the config store follows.
        #
        # Migrations are read back rather than held: every other method here reads the
        # file fresh, so keeping this one in memory would let two writers drop each
        # other's marker.
        payload = {SCHEMA_KEY: SCHEMA,
                   MIGRATIONS_KEY: (self._stored_migrations() if migrations is None
                                    else migrations),
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
