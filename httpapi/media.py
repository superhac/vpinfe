"""Every media file in the library, as its own lens on it.

A row here is a file, or the absence of one. That is the difference from the media a
game or a table reports: those answer "what does this game look like", one cell per
kind, and a cell can hold one fact. A file has several - which tables it serves, who
put it there, what it is - and a missing one has to be countable and selectable before
anything can be done about it in bulk.

Named for the file rather than for the table, because one shared file serves every
table in its folder. Reporting it once per table would count one gap as four, repeat
its origin four times, and put the same file in a selection four times over.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Query

from common.games import asset_origin
from common.media_specs import (
    MEDIA_SPECS,
    media_candidates,
    media_label_map,
    resolve_media_entries,
    spec_named,
)

from . import models, scopes
from .auth import requires

logger = logging.getLogger("vpinfe.httpapi.media")

router = APIRouter(prefix="/media", tags=["media"])

# The tiers that are this slot's own file, by the scope they belong to. A set or a
# cross-kind fallback is neither: it is another slot's file being borrowed, so it
# leaves this row empty and is reported as what is standing in.
# Two ways a file on disk answers for nobody, and they are not the same question. An
# ORPHAN names a table this folder does not have, so nothing will ever look for it.
# UNUSED is correctly named and covered by something more specific - it is the fallback,
# and it resolves again the moment what covers it goes.
ORPHAN = "orphan"
UNUSED = "unused"

_SHARED_TIERS = frozenset({"game", "default"})
_TABLE_TIERS = frozenset({"table"})


def _covered(game_dir: Path, files: set[str], medias: set[str], kind: str,
             variant: str, sets: dict[str, str] | None, stem: str | None,
             tiers: frozenset[str], winner: Path | None) -> list[Path]:
    """Files at this scope that the winner hides, each of which is a row of its own.

    A shared write only clears the spec-named family at its stem, so a `wheel.png` a
    catalog left sits under a `(Wheel) <folder>.png` and comes back the moment that one
    is removed. It is not dead, it is the fallback - which is why it is a row somebody
    can look at and decide about rather than a name in a column.
    """
    if winner is None:
        return []
    return sorted((item.path
                   for item in media_candidates(game_dir, files, medias, kind, variant,
                                                stem, sets)
                   if item.tier in tiers and item.path != winner),
                  key=lambda path: path.name)


def _orphans(files: set[str], medias: set[str], known: set[str]) -> list[tuple[str, str, str]]:
    """Spec-named files whose stem is no table here and not the folder.

    `(kind, stem, relative path)` each. Only the two places resolution looks - the
    folder root and `medias/` itself - because a file deeper than that is inside a set,
    where its name answers to the set rather than to a table.

    A file we did not name is not considered at all. `spec_named` answers None for one,
    and an unrecognized file in a folder the user owns is not a defect.
    """
    found = []
    for name in sorted(files | {item for item in medias if "/" not in item}):
        parsed = spec_named(name)
        if parsed is None or parsed[1].lower() in known:
            continue
        kind, stem = parsed
        found.append((kind, stem, name if name in files else f"medias/{name}"))
    return found


def _unused(game_id: str, row: dict, kind: str, path: Path, game_dir: Path,
            recorded: dict, hosts: dict, table: str = "",
            table_file: str = "") -> dict:
    """A file that is here, correctly named, and that nothing resolves to.

    Not the same as an orphan and not as safe to delete: the name is one resolution
    would look for, so removing whatever covers it brings this back. It is the fallback,
    and `serves` is 0 because right now nothing falls to it.
    """
    return {**_row(game_id, row, kind, table, table_file),
            "id": f"{game_id}:{kind}:{path.name}",
            "serves": 0,
            "present": True,
            "file": path.name,
            "path": asset_origin.path_of(game_dir, path) or None,
            "via": UNUSED,
            "origin": asset_origin.origin_of(hosts, game_dir, path) or None,
            "matched_to": asset_origin.match_of(recorded, game_dir, path) or None,
            "standing_in": ""}


def _row(game_id: str, row: dict, kind: str, table: str, table_file: str) -> dict:
    """The fields every row carries whatever its scope."""
    return {"id": f"{game_id}:{kind}:{table}", "game_id": game_id,
            "game": str(row.get("name") or ""),
            "manufacturer": str(row.get("manufacturer") or ""),
            "year": str(row.get("year") or ""),
            "kind": kind, "label": media_label_map().get(kind, kind),
            "table": table, "table_file": table_file,
            # What a catalog is asked for. On the row because every act on a slot needs
            # it and the alternative is a lookup per row against the games list.
            "vps_id": str(row.get("vpsid") or "")}


@router.get("", summary="Every media file in the library",
            dependencies=[requires(scopes.GAMES_READ)])
def list_media(limit: int = Query(0, ge=0), offset: int = Query(0, ge=0),
               game: str = Query(""), kind: str = Query("")) -> models.MediaSlotList:
    """One row per media file the library holds, plus one per file it does not.

    A game and kind has a **shared** row - the file each of its tables falls through to -
    and a table earns a row of its own only where a file is named for it. Two rows are
    deliberately not reported, because each would be the software inventing a gap: an
    empty per-table row, which would say a table-specific file ought to exist, and a
    missing shared row in a folder where every table already has its own.
    """
    from .games import _catalog, _media_contents, _media_settings, _tables, game_to_row

    kinds = [spec.kind for spec in MEDIA_SPECS]
    if kind:
        kinds = [item for item in kinds if item == kind]
    # Read once for the whole listing, and the folder walked once per game below.
    # `_resolved_media` re-walks and re-reads the config on every call, which a lens
    # resolving each folder once per table plus once shared pays several times over.
    variant, sets = _media_settings()

    def resolve(game_dir: Path, files: set[str], medias: set[str],
                stem: str | None) -> dict:
        return resolve_media_entries(game_dir, files, medias, variant, stem, sets)

    found: list[dict] = []
    for game_id, entry in _catalog().items():
        if game and game != game_id:
            continue
        row = game_to_row(entry)
        game_dir = Path(getattr(entry, "fullPathGame", "") or "")
        try:
            files, medias = _media_contents(game_dir)
        except OSError:
            logger.warning("media: cannot read %s", game_dir)
            continue

        tables = [table for table in _tables(entry, row) if table.get("id")]
        shared = resolve(game_dir, files, medias, None)
        # Resolved per table only to find the files named for one. The folder is walked
        # once above; each of these is set lookups against what it found.
        owned: dict[str, list[dict]] = {}
        for table in tables:
            stem = Path(table.get("filename") or "").stem
            for slot, hit in resolve(game_dir, files, medias, stem).items():
                if hit.tier in _TABLE_TIERS:
                    owned.setdefault(slot, []).append({**table, "stem": stem,
                                                       "hit": hit})

        recorded = asset_origin.sources(game_dir)
        hosts = {key: str(source.get("host", "") or "").strip()
                 for key, source in recorded.items()
                 if str(source.get("host", "") or "").strip()}

        known = {game_dir.name.lower()} | {Path(table.get("filename") or "").stem.lower()
                                           for table in tables}
        for orphan_kind, stem, relative in _orphans(files, medias, known):
            if orphan_kind not in kinds:
                continue
            path = game_dir / relative
            found.append({
                **_row(game_id, row, orphan_kind, "", stem),
                # Named for the file. The shared row of the same game and kind derives
                # its id from the table, which for both of them is "" - so without this
                # the two collide, the grid keys one over the other, and a click hands
                # the panel the wrong row.
                "id": f"{game_id}:{orphan_kind}:{relative}",
                "serves": 0,
                "present": True,
                "file": Path(relative).name,
                "path": relative,
                "via": ORPHAN,
                "origin": asset_origin.origin_of(hosts, game_dir, path) or None,
                "matched_to": asset_origin.match_of(recorded, game_dir, path) or None,
                "standing_in": "",
            })

        for slot in kinds:
            hit = shared.get(slot)
            path = hit.path if hit is not None and hit.tier in _SHARED_TIERS else None
            mine = owned.get(slot) or []
            serves = len(tables) - len(mine)
            # A shared row that nothing falls through to is not a gap: every table has a
            # file of its own, so there is nothing for a shared file to serve. Kept where
            # a file is actually there, because a file on disk is a row whatever uses it.
            if path is not None or serves > 0 or not tables:
                found.append({
                    **_row(game_id, row, slot, "", ""),
                    # Only ever about a file. A row with none says nothing here rather
                    # than how many tables would have used one, which is a different
                    # question wearing the same column.
                    "serves": serves if path is not None else None,
                    "present": path is not None,
                    "file": path.name if path is not None else None,
                    "path": asset_origin.path_of(game_dir, path) or None,
                    "via": hit.tier if path is not None else None,
                    "origin": asset_origin.origin_of(hosts, game_dir, path) or None,
                    "matched_to": asset_origin.match_of(recorded, game_dir, path) or None,
                    "standing_in": (hit.tier if hit is not None and hit.path is not None
                                    and hit.tier not in _SHARED_TIERS else ""),
                })
                for covered in _covered(game_dir, files, medias, slot, variant, sets,
                                        None, _SHARED_TIERS, path):
                    found.append(_unused(game_id, row, slot, covered, game_dir,
                                         recorded, hosts))
            for table in mine:
                own = table["hit"].path
                found.append({
                    **_row(game_id, row, slot, table["id"],
                           str(table.get("filename") or "")),
                    # One: the table it is named for. Not null - the question applies
                    # and has an answer, and a blank here would read as "no file".
                    "serves": 1,
                    "present": True,
                    "file": own.name,
                    "path": asset_origin.path_of(game_dir, own) or None,
                    "via": table["hit"].tier,
                    "origin": asset_origin.origin_of(hosts, game_dir, own) or None,
                    "matched_to": asset_origin.match_of(recorded, game_dir, own) or None,
                    "standing_in": "",
                })
                for covered in _covered(game_dir, files, medias, slot, variant, sets,
                                        table["stem"], _TABLE_TIERS, own):
                    found.append(_unused(game_id, row, slot, covered, game_dir,
                                         recorded, hosts, table["id"],
                                         str(table.get("filename") or "")))

    found.sort(key=lambda item: (item["game"].lower(), item["label"].lower(),
                                 item["table_file"].lower()))
    total = len(found)
    window = found[offset:offset + limit] if limit else found[offset:]
    return {"total": total, "offset": offset, "count": len(window), "media": window}
