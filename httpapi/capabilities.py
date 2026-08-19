"""Capability declarations for API discovery.

So `GET /api/v1` describes the running instance, not a fixed list in a doc.
Nothing is declared until the endpoints backing it land. See docs/http_api.md.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

# Residency: which roles a capability lives in. Listing both means each role serves
# its own, not that one capability spans the two - so if the hub and the device are
# ever separate machines, both have it. Clients hold no residency at all.
RESIDENCY_HUB = "hub"
RESIDENCY_DEVICE = "device"

RESIDENCIES = frozenset({RESIDENCY_HUB, RESIDENCY_DEVICE})


@dataclass(frozen=True)
class Capability:
    """One declared capability. `is_available` runs per request, not at import, so the
    answer stays honest after a config change; return (False, reason), not bare False."""

    name: str
    residency: Sequence[str]
    description: str = ""
    is_available: Callable[[], bool | tuple[bool, str]] | None = None

    def __post_init__(self) -> None:
        # A bare string would iterate into single characters and reach discovery
        # looking like a list of nine residencies, so it is rejected by name.
        if isinstance(self.residency, str) or not self.residency:
            raise ValueError(f"{self.name}: residency is a non-empty list of {sorted(RESIDENCIES)}")
        unknown = sorted(set(self.residency) - RESIDENCIES)
        if unknown:
            raise ValueError(f"{self.name}: unknown residency {unknown}")

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
            "residency": list(self.residency),
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
