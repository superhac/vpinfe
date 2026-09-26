"""What an extension declares, and what it is handed.

An extension is a directory holding `extension.json` beside a Python package whose
`register(ctx)` core calls once at startup. The context is the whole of its reach into
VPinFE - it never receives the application, and that is the guarantee the model rests on.

An implementation imports this module for the types and nothing else of ours.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import install_identity

# The platform ABI: the register/ctx signature, the event vocabulary and the scope
# vocabulary, versioned as one thing. An extension names the version it was written
# against and core refuses one it cannot honor.
PLATFORM_ABI = 1
SUPPORTED_ABI: frozenset[int] = frozenset({PLATFORM_ABI})

MANIFEST_NAME = "extension.json"

# The name is the extension's identity in five places at once - a URL segment, a scope,
# a log namespace, a config namespace and the Python package core imports - so it is
# restricted to what all five accept. No hyphen: the package is imported by this name,
# and a name that cannot be one is a trap laid for whoever writes the second module.
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# What an extension may ask of the machine, as opposed to of the domain. Declared here
# because the list is the consent surface: a capability nobody has heard of cannot be
# consented to.
CAPABILITIES: frozenset[str] = frozenset({
    "ui:mount", "config:own", "net:outbound", "proc:spawn",
    "hardware:usb", "fs:read", "fs:write",
})

PLATFORMS: frozenset[str] = frozenset({"linux", "windows", "macos"})

# What an install can be meant to do, read from the one list rather than restated: a
# second copy would be right until somebody added a feature.
FEATURES: frozenset[str] = frozenset(install_identity.FEATURES)


class ManifestError(ValueError):
    """The manifest is not one. `key` is the catalog line that says why, to whoever
    installed it, and `values` fill its slots."""

    def __init__(self, key: str, **values: str) -> None:
        super().__init__(key)
        self.key, self.values = key, values


class ContractError(RuntimeError):
    """An extension asked the context for something its manifest does not declare."""


def words(name: str) -> Callable[..., str]:
    """What the extension `name` says for a key in its `i18n/<language>.json`, in the
    language now set. `ctx.t`, for a module that is not handed the context."""
    from common.i18n import t

    def said(key: str, /, **params: Any) -> str:
        return t(f"ext.{name}.{key}", **params)

    return said


# What `register(ctx)` receives is built in `common/extensions/context.py` and described
# in `docs/extensions.md`. Not declared here as a protocol: half of it would be, since
# the config and event facades are defined in the module that imports this one, and a
# type an author could not satisfy is worse than none.


@dataclass(frozen=True)
class Manifest:
    name: str
    # Empty is looked up as `ext.<name>.name`. Set, it is a product name.
    display_name: str
    version: str
    # Empty is looked up as `ext.<name>.description`.
    description: str
    requires_platform: int
    # Core scopes it asks to use. A consent declaration; the vocabulary that decides
    # whether one is real lives with the API, so it is checked at the seam.
    scopes: tuple[str, ...] = ()
    # The actions it gates its own routes on. Core mints `ext:<name>:<action>` from
    # these, so an extension cannot name a scope belonging to another one.
    provides: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    # Install features it needs. An extension over a library is not offered to an
    # install that holds none.
    requires_features: tuple[str, ...] = ()
    # Empty means every one.
    platforms: tuple[str, ...] = ()
    # Event names it publishes, without its namespace.
    events: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "description": self.description,
            "requires_platform": self.requires_platform,
            "scopes": list(self.scopes),
            "provides": list(self.provides),
            "capabilities": list(self.capabilities),
            "requires_features": list(self.requires_features),
            "platforms": list(self.platforms),
            "events": list(self.events),
        }


def _strings(raw: Any, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ManifestError("extension.reason.manifest_not_a_list", field=field)
    return tuple(str(item).strip() for item in raw if str(item).strip())


def parse(raw: Any) -> Manifest:
    """Read a manifest, or say what is wrong with it in a line a user can act on."""
    if not isinstance(raw, dict):
        raise ManifestError("extension.reason.manifest_unreadable")

    name = str(raw.get("name") or "").strip()
    if not NAME_PATTERN.match(name):
        raise ManifestError("extension.reason.manifest_bad_name")

    try:
        abi = int(raw.get("requires_platform", ""))
    except (TypeError, ValueError):
        raise ManifestError("extension.reason.manifest_platform_unsaid") from None
    if abi not in SUPPORTED_ABI:
        raise ManifestError("extension.reason.manifest_platform_not_offered", abi=str(abi),
                            offered=", ".join(str(v) for v in sorted(SUPPORTED_ABI)))

    provides = _strings(raw.get("provides"), "provides")
    for action in provides:
        if not ACTION_PATTERN.match(action):
            raise ManifestError("extension.reason.manifest_bad_action", action=action)

    capabilities = _strings(raw.get("capabilities"), "capabilities")
    unknown = sorted(set(capabilities) - CAPABILITIES)
    if unknown:
        raise ManifestError("extension.reason.manifest_unknown_capabilities",
                            capabilities=", ".join(unknown))

    platforms = _strings(raw.get("platforms"), "platforms")
    unknown = sorted(set(platforms) - PLATFORMS)
    if unknown:
        raise ManifestError("extension.reason.manifest_unknown_platforms",
                            platforms=", ".join(unknown))

    features = _strings(raw.get("requires_features"), "requires_features")
    unknown = sorted(set(features) - FEATURES)
    if unknown:
        raise ManifestError("extension.reason.manifest_unknown_features",
                            features=", ".join(unknown))

    return Manifest(
        name=name,
        display_name=str(raw.get("display_name") or "").strip(),
        version=str(raw.get("version") or "").strip(),
        description=str(raw.get("description") or "").strip(),
        requires_platform=abi,
        scopes=_strings(raw.get("scopes"), "scopes"),
        provides=provides,
        capabilities=capabilities,
        requires_features=features,
        platforms=platforms,
        events=_strings(raw.get("events"), "events"),
    )


def read_manifest(directory: Path) -> Manifest:
    """The manifest in an extension directory."""
    path = Path(directory) / MANIFEST_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ManifestError("extension.reason.manifest_missing", file=MANIFEST_NAME) from None
    except (OSError, ValueError) as exc:
        raise ManifestError("extension.reason.manifest_unreadable") from exc
    return parse(raw)
