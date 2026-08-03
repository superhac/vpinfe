"""How VPinFE mints an opaque local id. Games and tables use the same scheme.

Here rather than in `game_identity` so `tables` can import it: `game_identity` reaches
back through `game_metadata` to `metaconfig`, which imports `tables`.
"""

from __future__ import annotations

import secrets

# No 0/O or I/l, so an id survives being read down a phone or retyped out of a bug report.
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
LENGTH = 10


def new_id() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
