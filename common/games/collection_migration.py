"""One-time conversions to a user's collections file.

Separate from `collection_store`, which says what a collection is allowed to be.
"""

from __future__ import annotations

import logging

from common.games.collection_store import COLLECTIONS_SCHEMA

logger = logging.getLogger("vpinfe.common.games.collection_migration")

# The collection the launcher used to maintain by hand, and the name it maintained it
# under. Kept: it is what the user sees, and what `startup_collection` may point at.
LAST_PLAYED_NAME = "Last Played"
LAST_PLAYED_MIGRATION = "last_played_is_derived"

# What it becomes. The cap was the launcher's, where it destroyed the 31st play; here it
# only stops the list being shown, so raising it later surfaces plays that far back.
LAST_PLAYED_FILTERS = {"played": True}
LAST_PLAYED_ORDER = {"by": "last_played", "direction": "desc"}
LAST_PLAYED_LIMIT = 30


def ensure_last_played(collections) -> bool:
    """Give this file a Last Played that derives itself. Returns whether it wrote.

    Converts the row the launcher used to maintain, in place, keeping its name, icon and
    position - or creates one when there is none. A fresh install gets it too: nothing
    creates it on first launch any more, so seeding is the only way a new user has one.

    Once. A user who deletes it, or turns it back into a hand-picked list, must not find
    it rebuilt under them at the next start.
    """
    if collections.has_migrated(LAST_PLAYED_MIGRATION):
        return False
    if collections.schema_version() > COLLECTIONS_SCHEMA:
        # Same rule the membership rekey follows: an older build does not rewrite a file
        # a newer one wrote, because it cannot know what else the newer one put in it.
        logger.warning("Collections file is schema %s, newer than this build's %s; "
                       "leaving Last Played as it is", collections.schema_version(),
                       COLLECTIONS_SCHEMA)
        return False

    with collections.mutate() as store:
        existing = LAST_PLAYED_NAME in store.get_collections_name()
        if not existing:
            store.add_collection(LAST_PLAYED_NAME)
        store.make_filter_collection(LAST_PLAYED_NAME, LAST_PLAYED_FILTERS,
                                     order=LAST_PLAYED_ORDER, limit=LAST_PLAYED_LIMIT)
        store.record_migration(LAST_PLAYED_MIGRATION)

    logger.info("%s %r: it now derives from the play dates in each .info",
                "Converted" if existing else "Added", LAST_PLAYED_NAME)
    return True
