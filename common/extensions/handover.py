"""Settings core used to hold, handed to the extension that owns them now.

A one-time move that core performs, not a door an extension reaches through. Core names
which of its own settings belong to which extension; nothing here lets an extension ask
for a setting, which is what keeps `config:own` from being decorative.

The same shape as the launchers and the locations leaving `vpinfe.ini`: read the old
place, write the new, mark it, never look again. Copied rather than moved - a reverted
install has to still find what its user typed, so the old section stays as history and
this build simply stops reading it.
"""

from __future__ import annotations

import logging

from common import config_schema
from common.config_access import cfg_get

logger = logging.getLogger("vpinfe.common.extensions.handover")

MARKER = "handed-over"

# {extension: {its setting: (our section, our key)}}. Core's list, in core, because
# deciding it anywhere else would be the door this exists not to be.
HANDOVER = {
    "vpinplay": {
        "endpoint": ("vpinplay", "api_endpoint"),
        "user_id": ("vpinplay", "user_id"),
        "initials": ("vpinplay", "initials"),
        "machine_id": ("vpinplay", "machine_id"),
        "sync_on_exit": ("vpinplay", "sync_on_exit"),
    },
}


def _default(section: str, key: str) -> str:
    """What the schema says this setting is when nobody has said."""
    found = config_schema.option(section, key)
    return str(getattr(found, "default", "") or "").strip() if found else ""


def seed(store, config) -> int:
    """Give each extension what core was configured with, once.

    Only values somebody actually set, which is not the same as values that are there:
    a fresh config file is written with every default in it, so "not empty" would hand
    over the whole section. Compared against what the schema says the default is instead.

    A default handed over would pin the extension to whatever core's default was on the
    day it was installed - and the two would then drift apart with nobody having chosen
    either. An install that never changed the endpoint gets nothing and uses the
    extension's own default, which is the same value.
    """
    if MARKER in store.migrations():
        return 0

    moved = 0
    for extension, mapping in HANDOVER.items():
        held = store.settings(extension)
        for setting, (section, key) in mapping.items():
            if setting in held:
                continue
            value = str(cfg_get(config, section, key, "") or "").strip()
            if not value or value == _default(section, key):
                continue
            store.set_setting(extension, setting, value)
            moved += 1
    store.mark_migration(MARKER)
    if moved:
        logger.info("Handed %d setting(s) to the extensions that own them now", moved)
    return moved
