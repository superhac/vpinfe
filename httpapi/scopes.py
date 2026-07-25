"""The scope vocabulary.

Reserved now so the names are settled before anything depends on them. Most are
not yet used by a route - they exist so that adding the endpoint later does not
also mean inventing its scope, and renaming one afterwards is a breaking change.

Shape is `<resource>:<action>`. Extensions get `ext:<name>:<action>`, which keeps
their scopes from ever colliding with a core one.
"""

from __future__ import annotations

# What this instance is: discovery, health, version, what it can do. Not domain
# data - the answer to "what am I talking to", which is what discovery exists for.
INSTANCE_READ = "instance:read"

TABLES_READ = "tables:read"
TABLES_WRITE = "tables:write"

COLLECTIONS_READ = "collections:read"
COLLECTIONS_WRITE = "collections:write"

# Play host. Reading what is happening is not the same as causing it to happen.
PLAY_READ = "play:read"
LAUNCH_INVOKE = "launch:invoke"

UPLOADS_WRITE = "uploads:write"
# Separate from tables:read on purpose: this one makes an outbound call to VPSdb
# on the caller's behalf, which is not the same permission as reading local tables.
VPS_READ = "vps:read"

CONFIG_READ = "config:read"
CONFIG_WRITE = "config:write"

SYSTEM_READ = "system:read"
# Restart, reboot, shutdown. Deliberately its own scope: it is the one that can
# end someone's game.
SYSTEM_ADMIN = "system:admin"

EVENTS_SUBSCRIBE = "events:subscribe"

CORE = frozenset({
    INSTANCE_READ,
    TABLES_READ, TABLES_WRITE,
    COLLECTIONS_READ, COLLECTIONS_WRITE,
    PLAY_READ, LAUNCH_INVOKE,
    UPLOADS_WRITE, VPS_READ,
    CONFIG_READ, CONFIG_WRITE,
    SYSTEM_READ, SYSTEM_ADMIN,
    EVENTS_SUBSCRIBE,
})

EXTENSION_PREFIX = "ext:"


def extension_scope(extension: str, action: str) -> str:
    """A scope belonging to an extension, which can never collide with a core one."""
    return f"{EXTENSION_PREFIX}{extension}:{action}"


def is_extension_scope(scope: str) -> bool:
    return scope.startswith(EXTENSION_PREFIX)


def is_known(scope: str) -> bool:
    return scope in CORE or is_extension_scope(scope)
