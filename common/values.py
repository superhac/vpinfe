"""Value coercion shared across the codebase.

Infrastructure: nothing here knows about games, hardware or any outside service,
so anything may depend on it. It exists because `is_truthy` lived in
`game_metadata` and `config_access` had to reach up into the domain to read a
boolean out of an ini file.
"""

from __future__ import annotations

from typing import Any

_TRUE_VALUES = {"1", "true", "yes", "on"}


def is_truthy(value: Any, default: bool = False) -> bool:
    """Whether a config or metadata value means yes.

    `default` covers the two ways a value can be absent rather than false - None
    and empty string - so a missing setting can still opt in.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized == "":
        return default
    return normalized in _TRUE_VALUES


def parse_version(value: Any) -> tuple[int, ...]:
    """A version string as a comparable tuple. `()` when it is not a version.

    Stops at the first non-numeric part, so `3.0.1-beta.2` compares as `(3, 0, 1)`
    rather than as nothing - a theme tested against a beta still means 3.0.1.
    """
    parts: list[int] = []
    for part in str(value or "").strip().lstrip("vV").split("."):
        if not part.isdigit():
            break
        parts.append(int(part))
    return tuple(parts)
