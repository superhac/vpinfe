"""The library as a whole, rather than one game of it.

A scan rewrites metadata across every game folder; a tag merge renames a word half the
library carries. Neither is an operation on a game, and doing either one folder at a time
leaves the library in a state nobody asked for.

The long ones run as jobs. `start` is how one is put on the queue, because every caller
wants the same thing back - something to watch - and the same refusal when the queue is
busy.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from common import jobs as job_registry
from common import service_errors
from common.games import (
    entry_lens,
    game_repository,
    game_service,
    library_vps_state,
    standalone_scripts,
    watching,
)
from common.games.collection_filters import AXES, GameListFilters
from common.games.collection_resolver import resolve
from common.games.collection_store import BUILTIN_ALL
from common.games.collections_service import get_collections_manager
from common.games.game_metadata import retag_library
from common.games.library_policy import get_library_policy


def start(kind: str, work: Callable[[job_registry.Job], object]) -> job_registry.Job:
    """Put a library-wide pass on the queue, or refuse because one is already running."""
    try:
        return job_registry.submit(kind, work)
    except job_registry.JobBusyError as exc:
        raise service_errors.BlockedError(str(exc)) from exc


def filter_axes() -> dict[str, Any]:
    """Every filter axis, with the values this library holds.

    Projected from the registry the resolver matches on, so the two cannot disagree. A
    rating axis carries no values: it is 0-5 whatever is installed.
    """
    available = GameListFilters(game_repository.all_games()).available_options()
    return {"axes": [{"name": axis.name, "scope": axis.scope, "kind": axis.kind,
                      # The name a reader sees, which the registry owns. Without it a
                      # caller derives one from the key and gets "Game type" where the
                      # rest of the app says "Type".
                      "label": axis.label,
                      "label_key": f"filter.{axis.name}.label",
                      "summary": axis.summary,
                      # Whether the axis takes several values, which is an OR across
                      # them. Declared so a caller renders the right control without
                      # knowing which axes exist.
                      "many": axis.many,
                      "values": available.get(axis.values_key)}
                     for axis in AXES]}


def merge_tags(sources: Iterable[str], into: str) -> dict[str, Any]:
    """Across the library, because a tag is not owned by a game - half of them renamed
    is a worse state than either end of the merge."""
    return {"changed": retag_library(game_repository.all_games(), list(sources), into)}


def drop_tag(tag: str) -> dict[str, Any]:
    """The vocabulary is derived, so a tag no game carries has ceased to exist."""
    return {"changed": retag_library(game_repository.all_games(), [tag], "")}


def entries() -> dict[str, Any]:
    """The play lens over everything, which is what a frontend shows before a collection
    is chosen.

    The whole library is a collection - `builtin:all`, synthesized rather than stored, so
    it answers without putting a row in anyone's file.
    """
    resolved = resolve(BUILTIN_ALL, get_collections_manager(), game_repository.all_games())
    return {"collection": "", "count": len(resolved),
            "entries": [entry_lens.entry_resource(entry) for entry in resolved]}


def preview(criteria: dict, limit: int = 0) -> dict[str, Any]:
    """Resolve criteria against the library without writing them anywhere.

    An unsaved rule is `builtin:all` plus its criteria, so this is the ordinary resolve
    with nothing stored.
    """
    manager = get_collections_manager()
    # Set for this call and cleared after it, because the store object outlives it and a
    # leftover constraint would narrow the next reader's whole library.
    try:
        manager.set_view_filters(criteria)
        resolved = resolve(BUILTIN_ALL, manager, game_repository.all_games())
    finally:
        manager.set_view_filters(None)
    if limit and limit > 0:
        resolved = resolved[:limit]
    return {"collection": "", "count": len(resolved),
            "entries": [entry_lens.entry_resource(entry) for entry in resolved]}


def scan(options: dict[str, Any]) -> job_registry.Job:
    """Rebuild game metadata from VPSdb. Writes a .info for every game it can match."""
    return start(job_registry.KIND_LIBRARY_SCAN,
                 lambda job: game_service.build_metadata(
                     job=job,
                     download_media=options.get("download_media", False),
                     update_all=options.get("update_all", False)))


def refresh() -> job_registry.Job:
    """The local counterpart to a scan: re-read the folders, give every .vpx an id, note
    the ones that are gone, and read whatever nothing has read yet. Never the network.

    Shares the scan's job kind deliberately - both write a .info for every game they
    touch, so running them at once would interleave writes to the same files.
    """
    from common.games.library_refresh import refresh as run_refresh

    return start(job_registry.KIND_LIBRARY_SCAN,
                 lambda job: run_refresh(job.reporter()))


def recount_vps_state() -> job_registry.Job:
    """Its own job kind: read-only, so it may run beside a scan."""
    return start(job_registry.KIND_VPS_ROLLUP,
                 lambda job: library_vps_state.recount(job.reporter()))


def one_info_pass(work: Callable[..., object]) -> job_registry.Job:
    """The scan's job kind, because these rewrite exactly the files a scan does and two
    at once would interleave writes to the same file."""
    return start(job_registry.KIND_LIBRARY_SCAN, lambda job: work(job=job))


def apply_script_patches() -> job_registry.Job:
    """Each fix lands as a `.vbs` sidecar beside the table it is for."""
    return start(job_registry.KIND_LIBRARY_SCAN,
                 lambda job: game_service.apply_vpx_patches(progress_cb=job.progress))


def policy() -> dict[str, Any]:
    """Which kinds this library collects and which catalogs it searches."""
    return get_library_policy().values()


def set_policy(changes: dict) -> dict[str, Any]:
    """A patch: an absent key is left alone, and a present empty list is stored - empty
    means everything, so clearing one is a real answer rather than saying nothing."""
    held = get_library_policy()
    for key, value in changes.items():
        held.set(key, value)
    return held.values()


def watching_since() -> dict[str, Any]:
    """Empty means nobody has answered yet, and until they do nothing counts as new."""
    return {"since": watching.since()}


def watch_from(since: str) -> dict[str, Any]:
    """One mechanism for both answers a first run offers: review everything is the
    beginning of time, start clean is now."""
    watching.set_since(since or watching.FROM_THE_BEGINNING)
    return {"since": watching.since()}


def acknowledge(game_id: str, kind: str, vps_file_id: str) -> None:
    """Sparse by design: only what somebody dismissed is stored."""
    watching.acknowledge(game_id, kind, vps_file_id)


def vps_rollup() -> dict[str, Any]:
    """The last rollup counted, and when. Never live: counting it resolves media for
    every game, which measured 650ms over 149 folders."""
    return library_vps_state.stored() or {"computed": "", "games": 0, "matched": 0,
                                          "kinds": []}


def info_maintenance() -> dict[str, Any]:
    """The three states a `.info` file can be in that are worth acting on, and the
    folders with no readable one at all. Counted off the library already in memory."""
    counts = game_repository.info_maintenance_counts()
    return {"pending_upgrade": counts.get("pending_upgrade", 0),
            "restorable": counts.get("restorable", 0),
            "newer_than_us": counts.get("newer_than_us", 0),
            "newest_backup": game_service.newest_backup_stamp() or "",
            "pending_games": game_service.pending_upgrade_game_names(),
            "restorable_games": game_service.restorable_game_names(),
            "unreadable": game_repository.unreadable_games()}


def offered_patches() -> dict[str, Any]:
    """What script fixes are published for this library. Changes nothing."""
    return standalone_scripts.offered_for(game_repository.all_games())
