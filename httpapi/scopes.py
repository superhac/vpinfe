"""The scope vocabulary: `<resource>:<action>`, extensions `ext:<name>:<action>`.

Most are reserved rather than used - settling a name is cheap, renaming one after
callers depend on it is not. See docs/http_api.md.
"""

from __future__ import annotations

# What this instance is: discovery, health, version, what it can do. Not domain
# data - the answer to "what am I talking to", which is what discovery exists for.
INSTANCE_READ = "instance:read"

GAMES_READ = "games:read"
GAMES_WRITE = "games:write"
# Deliberately not part of games:read: reading the library and extracting
# complete game folders are different permissions.
GAMES_EXPORT_FULL = "games:export_full"

COLLECTIONS_READ = "collections:read"
COLLECTIONS_WRITE = "collections:write"

# Play host. Reading what is happening is not the same as causing it to happen.
PLAY_READ = "play:read"
LAUNCH_INVOKE = "launch:invoke"

UPLOADS_WRITE = "uploads:write"
# Separate from games:read on purpose: this one makes an outbound call to VPSdb
# on the caller's behalf, which is not the same permission as reading local games.
VPS_READ = "vps:read"

CONFIG_READ = "config:read"
CONFIG_WRITE = "config:write"

SYSTEM_READ = "system:read"
# Restart, reboot, shutdown. Deliberately its own scope: it is the one that can
# end someone's game.
SYSTEM_ADMIN = "system:admin"

# The players a hub knows. Reading the roster is not the same as joining it: a player
# announces itself, which is a write, and anything asking who is out there is a read.
PLAYERS_READ = "players:read"
PLAYERS_WRITE = "players:write"

EVENTS_SUBSCRIBE = "events:subscribe"

# Asking what slow work is running. Starting it carries the scope of what it does -
# a library scan writes game metadata, so it is games:write - because the right to
# watch a job is not the right to cause one.
JOBS_READ = "jobs:read"

CORE = frozenset({
    INSTANCE_READ,
    GAMES_READ, GAMES_WRITE, GAMES_EXPORT_FULL,
    COLLECTIONS_READ, COLLECTIONS_WRITE,
    PLAY_READ, LAUNCH_INVOKE,
    UPLOADS_WRITE, VPS_READ,
    CONFIG_READ, CONFIG_WRITE,
    SYSTEM_READ, SYSTEM_ADMIN,
    EVENTS_SUBSCRIBE, JOBS_READ,
    PLAYERS_READ, PLAYERS_WRITE,
})

EXTENSION_PREFIX = "ext:"


def extension_scope(extension: str, action: str) -> str:
    """A scope belonging to an extension, which can never collide with a core one."""
    return f"{EXTENSION_PREFIX}{extension}:{action}"


def is_extension_scope(scope: str) -> bool:
    return scope.startswith(EXTENSION_PREFIX)


def is_known(scope: str) -> bool:
    return scope in CORE or is_extension_scope(scope)
