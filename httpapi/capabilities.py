"""Capability declarations for API discovery.

So `GET /api/v1` describes the running instance, not a fixed list in a doc.
Nothing is declared until the endpoints backing it land. See docs/http_api.md.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Residency: where a capability has to run. Clients hold neither.
RESIDENCY_CATALOG = "catalog"
RESIDENCY_PLAY_HOST = "play_host"


@dataclass(frozen=True)
class Capability:
    """One declared capability. `is_available` runs per request, not at import, so the
    answer stays honest after a config change; return (False, reason), not bare False."""

    name: str
    residency: str
    description: str = ""
    is_available: Callable[[], bool | tuple[bool, str]] | None = None

    def resolve(self) -> dict[str, Any]:
        available, reason = True, None
        if self.is_available is not None:
            try:
                result = self.is_available()
            except Exception as exc:  # a broken probe must not break discovery
                available, reason = False, f"availability check failed: {exc}"
            else:
                if isinstance(result, tuple):
                    available, reason = result[0], result[1]
                else:
                    available = bool(result)
        return {
            "name": self.name,
            "residency": self.residency,
            "description": self.description,
            "available": available,
            "reason": reason,
        }


_CAPABILITIES: dict[str, Capability] = {}


def declare(capability: Capability) -> Capability:
    """Register a capability for discovery. Re-declaring a name replaces it."""
    _CAPABILITIES[capability.name] = capability
    return capability


def declared() -> list[dict[str, Any]]:
    """Every declared capability, sorted by name for a stable payload."""
    return [_CAPABILITIES[name].resolve() for name in sorted(_CAPABILITIES)]


def clear() -> None:
    """Drop all declarations. For tests."""
    _CAPABILITIES.clear()
