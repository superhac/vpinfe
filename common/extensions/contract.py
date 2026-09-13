"""What an extension declares, and what it is handed.

An extension is a directory holding `extension.json` beside a Python package whose
`register(ctx)` core calls once at startup. The context is the whole of its reach into
VPinFE - it never receives the application, and that is the guarantee the model rests on.

An implementation imports this module for the types and nothing else of ours.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
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
    """The manifest is not one. Carries the sentence shown to whoever installed it."""


class ContractError(RuntimeError):
    """An extension asked the context for something its manifest does not declare."""


# What `register(ctx)` receives is built in `common/extensions/context.py` and described
# in `docs/extensions.md`. Not declared here as a protocol: half of it would be, since
# the config and event facades are defined in the module that imports this one, and a
# type an author could not satisfy is worse than none.


@dataclass(frozen=True)
class Manifest:
    name: str
    display_name: str
    version: str
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
        raise ManifestError(f"{field} has to be a list of strings")
    return tuple(str(item).strip() for item in raw if str(item).strip())


def parse(raw: Any, *, source: str = "") -> Manifest:
    """Read a manifest, or say what is wrong with it in a sentence a user can act on."""
    where = f" in {source}" if source else ""
    if not isinstance(raw, dict):
        raise ManifestError(f"The manifest{where} is not an object")

    name = str(raw.get("name") or "").strip()
    if not NAME_PATTERN.match(name):
        raise ManifestError(f"{name or '(unnamed)'}{where}: a name is lowercase letters, "
                            "digits, hyphen and underscore, starting with a letter")

    try:
        abi = int(raw.get("requires_platform"))
    except (TypeError, ValueError):
        raise ManifestError(f"{name}: requires_platform has to be a number") from None
    if abi not in SUPPORTED_ABI:
        raise ManifestError(f"{name} was built for platform {abi}; this build offers "
                            f"{', '.join(str(v) for v in sorted(SUPPORTED_ABI))}")

    provides = _strings(raw.get("provides"), "provides")
    for action in provides:
        if not ACTION_PATTERN.match(action):
            raise ManifestError(f"{name}: {action!r} is not an action name")

    capabilities = _strings(raw.get("capabilities"), "capabilities")
    unknown = sorted(set(capabilities) - CAPABILITIES)
    if unknown:
        raise ManifestError(f"{name} asks for capabilities this build does not offer: "
                            f"{', '.join(unknown)}")

    platforms = _strings(raw.get("platforms"), "platforms")
    unknown = sorted(set(platforms) - PLATFORMS)
    if unknown:
        raise ManifestError(f"{name} names platforms that do not exist: "
                            f"{', '.join(unknown)}")

    features = _strings(raw.get("requires_features"), "requires_features")
    unknown = sorted(set(features) - FEATURES)
    if unknown:
        raise ManifestError(f"{name} needs features that do not exist: "
                            f"{', '.join(unknown)}")

    return Manifest(
        name=name,
        display_name=str(raw.get("display_name") or name).strip(),
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
        raise ManifestError(f"No {MANIFEST_NAME} in {path.parent.name}") from None
    except (OSError, ValueError) as exc:
        raise ManifestError(f"{path.parent.name}: {MANIFEST_NAME} could not be "
                            f"read: {exc}") from None
    return parse(raw, source=f"{path.parent.name}/{MANIFEST_NAME}")
