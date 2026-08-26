"""The game catalog.

A game is the pinball-machine concept - folder, identity, metadata, media and
assets. The launchable artifact is a table, exposed as a sub-resource, because a
game is not permanently one .vpx.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Body, File, Query, Request, UploadFile
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from common.config_access import MediaConfig
from common.games import (
    asset_origin,
    asset_resolver,
    game_identity,
    library_discovery,
    media_lookup,
    media_placement,
)
from common.games.game_metadata import (
    load_game_meta,
    meta_file_path,
    set_game_rating,
    vpinfe_section,
)
from common.games.game_repository import (
    all_games,
    collections_by_game_id,
    game_to_row,
)
from common.games.info_file import MetaConfig
from common.games.tables import (
    ABSENT_SINCE_KEY,
    TABLE_ID_KEY,
    default_table,
    entry_for_filename,
    hidden_tables,
    is_parsed,
    recorded_default,
    table_entries,
    table_filenames,
    table_names,
)
from common.host import launch, launch_state, pinmame_catalog
from common.media_specs import MEDIA_SPECS
from common.paths import get_ini_config

from . import filesystem, models, scopes
from .auth import ForbiddenError, requires
from .errors import ConflictError, FeatureUnavailableError, InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.games")

router = APIRouter(prefix="/games", tags=["games"])


def _catalog() -> dict:
    """Every game keyed by id, minting ids for any that lack one.

    Writes only for games without an id, so this is a no-op once the library has
    been through it. main.py does the same at startup; this keeps the API correct
    when it is driven without a full app boot.
    """
    return game_identity.ensure_unique_ids(all_games())


def _game_or_404(game_id: str):
    game = _catalog().get(game_id)
    if game is None:
        raise NotFoundError(f"No game with id {game_id}")
    return game


def _resource(row: dict, game_id: str) -> dict:
    prefix = f"/api/v1/games/{game_id}"
    return {
        "id": game_id,
        # Correlation with VPSdb, VPinPlay and the like - not this table's identity.
        "vps_id": row.get("vpsid", ""),
        "name": row.get("name", ""),
        "manufacturer": row.get("manufacturer", ""),
        "year": str(row.get("year") or ""),
        "type": row.get("type", ""),
        "themes": row.get("themes") or [],
        "authors": row.get("authors") or [],
        "rom": row.get("rom", ""),
        "version": row.get("version", ""),
        "rating": row.get("rating", 0),
        "collections": row.get("collections") or [],
        # Assets, not media: these are what the game needs to play as intended.
        # Media is the artwork VPinFE shows while browsing - see docs/conventions.md.
        # Summary from the scan; the detail endpoint recomputes and attributes files.
        "assets": _asset_summary(row),
        "links": {
            "self": prefix,
            "tables": f"{prefix}/tables",
            "media": f"{prefix}/media",
            "archive": f"{prefix}/archive",
            "launch": f"{prefix}/launch",
            "rating": f"{prefix}/rating",
        },
    }


def _asset_summary(row: dict) -> dict:
    """Presence per kind, as objects so a kind can grow attributes without a
    breaking change. alt_color keeps its formats - the flat boolean lost them."""
    formats = [name for name, flag in (("serum", "serum_exists"), ("vni", "vni_exists"))
               if row.get(flag)]
    return {
        "backglass": {"present": bool(row.get("b2s_exists"))},
        "settings": {"present": bool(row.get("ini_exists"))},
        "pup_pack": {"present": bool(row.get("pup_pack_exists"))},
        "alt_color": {"present": bool(formats), "formats": formats},
        "alt_sound": {"present": bool(row.get("alt_sound_exists"))},
        "music": {"present": bool(row.get("music_exists"))},
    }


def _listing(game_dir: Path) -> tuple[list[str], list[str]]:
    files: list[str] = []
    subdirs: list[str] = []
    if game_dir.is_dir():
        for entry in game_dir.iterdir():
            (files if entry.is_file() else subdirs).append(entry.name)
    return files, subdirs


def _inventory_assets(game_dir: Path) -> dict:
    """The inventory lens: every asset file attributed, plus the folder-wide kinds.

    Computed fresh per request, not from the scan - an audit that reports
    yesterday's folder is worse than none.
    """
    files, subdirs = _listing(game_dir)
    inv = asset_resolver.inventory(game_dir.name, files, table_names(files))
    for entry in inv.values():
        entry["present"] = bool(entry["files"])
    subdir_set = {name.lower() for name in subdirs}
    formats = [fmt for fmt, folder in (("serum", "serum"), ("vni", "vni"))
               if folder in subdir_set]
    inv["pup_pack"] = {"present": "pupvideos" in subdir_set}
    inv["alt_color"] = {"present": bool(formats), "formats": formats}
    inv["alt_sound"] = {"present": (game_dir / "pinmame" / "altsound").is_dir()}
    inv["music"] = {"present": "music" in subdir_set}
    return inv


def _table_settings(game_dir: Path) -> dict:
    """Per-table settings from the folder's .info, or {} when unreadable.

    A folder that cannot be parsed must not make its tables vanish - absent
    settings mean everything is visible, which is what an older library looks like.
    """
    try:
        from common.games.info_file import MetaConfig
        info = game_dir / f"{game_dir.name}.info"
        if info.is_file():
            return MetaConfig(str(info)).game_file_settings()
    except Exception:  # noqa: BLE001 - settings are advisory; never block the listing
        logger.debug("Could not read table settings for %s", game_dir, exc_info=True)
    return {}


def _tables(game, row: dict) -> list[dict]:
    """The game's launchable artifacts.

    Enumerates what is actually in the folder rather than trusting the single
    filename recorded in the .info: a game folder can hold several .vpx files.
    Sorted, so the answer does not depend on directory order.

    A table the metadata describes but absent from disk is still reported - a
    table pointing at a missing file is something the caller should see - but the
    default falls to one that exists, since the default is what a caller would launch.
    """
    game_dir = Path(row.get("game_dir", ""))
    described = _table_settings(game_dir)

    files, subdirs = _listing(game_dir)
    on_disk = table_names(files)

    names = list(on_disk)
    for name in table_filenames(described):
        if name not in names:
            names.append(name)
    if not names:
        return []

    # Same resolver the launcher and the metadata build use, so all three agree.
    default = default_table(files or names, game_dir.name,
                                recorded_default(vpinfe_section(game.meta_config),
                                             described))
    hidden = hidden_tables(described)

    # Dependency context, once per request: the alias map and the rom listing are
    # shared by every table in the folder.
    aliases = asset_resolver.read_alias_map(str(game_dir))
    rom_files = asset_resolver.list_rom_files(str(game_dir))

    def _tristate(value):
        """detect* flags are three-valued: yes, no, and never parsed."""
        if isinstance(value, bool):
            return value
        raw = str(value if value is not None else "").strip().lower()
        return True if raw in ("true", "1") else False if raw in ("false", "0") else None

    entries = []
    for name in names:
        described_entry = entry_for_filename(described, name)[1]
        entry = {
            # The table's own id, the same one the play lens uses. Without it the two
            # lenses describe the same table and a client cannot tell that they do -
            # filenames are not identity, which is why ids were minted in the first place.
            "id": str(described_entry.get(TABLE_ID_KEY, "") or ""),
            "format": "vpx",
            "app": "vpx",
            "filename": name,
            "version": str(described_entry.get("version", "") or ""),
            "authors": [str(a) for a in (described_entry.get("authors") or [])],
            "default": name == default,
            "hidden": name in hidden,
            "available": name in on_disk,
            "absent_since": library_discovery.absent_since(described_entry) or None,
            "assets": asset_resolver.resolve_for_table(name, game_dir.name, files),
        }
        if is_parsed(described_entry):
            # Every table carries its own ROM and detect flags, so each one answers
            # for itself. This used to be knowable only for the single file the .info
            # described; the rest returned an honest "unknown".
            chain = asset_resolver.resolve_rom_chain(
                described_entry.get("rom", ""), aliases, rom_files,
                _tristate(described_entry.get("detect_pinmame")))
            if chain["effective"]:
                # PinMAME's own audit, from the library the configured VPX ships.
                # No answer leaves the name-match conclusion standing.
                from common.config_access import SettingsConfig
                audit = pinmame_catalog.lookup(
                    SettingsConfig.from_config(get_ini_config()).vpx_bin_path,
                    str(game_dir / "pinmame" / "roms"), chain["effective"])
                asset_resolver.apply_audit(chain, audit)
            flex = asset_resolver.flexdmd_state(
                subdirs, _tristate(described_entry.get("detect_flex")))
        else:
            # Never parsed: added since the last metadata build, and the .info may already
            # carry decisions about it - hidden, or where it came from - without
            # anything having read the file itself.
            chain = {"declared": None, "alias_of": None, "effective": None,
                     "required": None, "catalog": None, "clone_of": None,
                     "audit": None, "installed": None,
                     "reason": "unknown: this table has not been parsed yet"}
            flex = asset_resolver.flexdmd_state(subdirs, None)
        chain["nvram"] = asset_resolver.nvram_state(str(game_dir), chain["effective"])
        entry["dependencies"] = {"pinmame": chain, "flexdmd": flex}
        entries.append(entry)
    return entries


@router.get("", summary="List games", dependencies=[requires(scopes.GAMES_READ)])
def list_games(
    q: str = Query("", description="Match against name, manufacturer or rom"),
    limit: int = Query(0, ge=0, description="0 returns everything"),
    offset: int = Query(0, ge=0),
) -> models.GameList:
    catalog = _catalog()
    collections = collections_by_game_id()

    items = []
    for game_id, game in catalog.items():
        row = game_to_row(game, collections)
        items.append((row.get("name", "").lower(), _resource(row, game_id)))
    items.sort(key=lambda pair: pair[0])
    resources = [resource for _name, resource in items]

    if q:
        needle = q.strip().lower()
        resources = [
            r for r in resources
            if needle in r["name"].lower()
            or needle in (r["manufacturer"] or "").lower()
            or needle in (r["rom"] or "").lower()
        ]

    total = len(resources)
    if offset:
        resources = resources[offset:]
    if limit:
        resources = resources[:limit]
    return {"total": total, "offset": offset, "count": len(resources), "games": resources}


@router.get("/{game_id}", summary="One game", dependencies=[requires(scopes.GAMES_READ)])
def get_game(game_id: str) -> models.GameResource:
    game = _game_or_404(game_id)
    row = game_to_row(game, collections_by_game_id())
    resource = _resource(row, game_id)
    resource["assets"] = _inventory_assets(Path(row.get("game_dir", "")))
    return resource


@router.get("/{game_id}/tables", summary="A game's tables",
            dependencies=[requires(scopes.GAMES_READ)])
def get_games(game_id: str) -> models.TableList:
    game = _game_or_404(game_id)
    return {"tables": _tables(game, game_to_row(game))}


def _media_contents(game_dir: Path) -> tuple[set[str], set[str]]:
    """What is in the folder and in medias/, as the resolver wants it.

    medias/ comes back with relative paths, because a media set is a subfolder and
    the resolver matches it by "wheels/<set>/<name>".
    """

    files, subdirs = _listing(game_dir)
    medias: set[str] = set()
    if "medias" in {name.lower() for name in subdirs}:
        medias_dir = game_dir / "medias"
        try:
            for dirpath, _dirs, filenames in os.walk(medias_dir):
                rel = os.path.relpath(dirpath, medias_dir)
                for fname in filenames:
                    medias.add(fname if rel == "." else
                               f"{rel}/{fname}".replace(os.sep, "/"))
        except OSError:
            medias = set()
    return set(files), medias


def _media_settings() -> tuple[str, dict[str, str] | None]:
    """The playfield variant and any active media set, as the resolver takes them."""
    media_cfg = MediaConfig.from_config(get_ini_config())
    from common.media_specs import active_set_for
    wheelset = active_set_for("wheel", media_cfg.wheelset)
    return media_cfg.playfield_variant, ({"wheel": wheelset} if wheelset else None)


def _resolved_media(game_dir: Path, table_stem: str | None = None) -> dict:
    """Every media kind against the folder as it is right now."""
    from common.media_specs import resolve_media_entries

    files, medias = _media_contents(game_dir)
    variant, active_sets = _media_settings()
    return resolve_media_entries(game_dir, files, medias, variant,
                                 table_stem, active_sets)


def _media_entries(resolved: dict, game_dir: Path, prefix: str) -> dict:
    """What a curator asks of a slot: does it resolve, how specific, and where from.

    `via` is why this file is the one being used - "table", "game", "default",
    "set:<name>" or "fallback:<kind>". `origin` is who put it there, which is a
    different question with a different source: the .info ledger, read once per
    request here rather than once per kind. Neither answer implies the other.
    """
    recorded = asset_origin.ledger(game_dir)
    return {
        key: {
            "present": hit.path is not None,
            "file": hit.path.name if hit.path is not None else None,
            "via": hit.tier,
            "origin": asset_origin.origin_of(recorded, game_dir, hit.path) or None,
            "links": {"self": f"{prefix}/{key}"} if hit.path is not None else {"self": None},
        }
        for key, hit in resolved.items()
    }


def _table_stem_or_404(game, table_id: str) -> str:
    """The stem to resolve against, or 404 if that table is not this game's."""
    filename = media_lookup.table_filename(game, table_id)
    if not filename:
        raise NotFoundError("This game has no such table",
                            details={"game": getattr(game, "gameDirName", ""),
                                     "table": table_id})
    return Path(filename).stem


@router.get("/{game_id}/media", summary="A game's shared media",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media(game_id: str) -> models.MediaList:
    """Media is the artwork shown about a game - every kind, present or not,
    so a client can enumerate what is possible instead of guessing.

    Resolved with no table stem, so this is what every table in the folder shares.
    Art named for one build belongs to that build and answers under its table.
    """
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    prefix = f"/api/v1/games/{game_id}/media"
    return {"media": _media_entries(_resolved_media(game_dir, None), game_dir, prefix)}


def _media_file_or_404(game, kind: str, table_stem: str | None):
    known = {spec.kind for spec in MEDIA_SPECS}
    if kind not in known:
        raise InvalidRequestError("Unknown media kind",
                                  details={"unknown": kind, "known": sorted(known)})
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    hit = _resolved_media(game_dir, table_stem).get(kind)
    path = hit.path if hit is not None else None
    if path is None or not path.is_file():
        raise NotFoundError(f"This game has no {kind} media")
    return FileResponse(path)


@router.get("/{game_id}/media/{kind}", summary="One shared media file",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media_file(game_id: str, kind: str):
    return _media_file_or_404(_game_or_404(game_id), kind, None)


@router.get("/{game_id}/tables/{table_id}/media", summary="One table's media",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media(game_id: str, table_id: str) -> models.MediaList:
    """The same kinds, resolved for one build rather than for the folder.

    Two builds of a game can genuinely differ - a VR room and a desktop table are
    not the same picture - so each answers for itself. `via: "table"` marks a file
    named for this .vpx; anything else it shares with its siblings.
    """
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    prefix = f"/api/v1/games/{game_id}/tables/{table_id}/media"
    resolved = _resolved_media(game_dir, _table_stem_or_404(game, table_id))
    return {"media": _media_entries(resolved, game_dir, prefix)}


@router.get("/{game_id}/tables/{table_id}/media/{kind}", summary="One table's media file",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media_file(game_id: str, table_id: str, kind: str):
    game = _game_or_404(game_id)
    return _media_file_or_404(game, kind, _table_stem_or_404(game, table_id))


async def _write_media(game, kind: str, stem: str, upload: UploadFile,
                       prefix: str, table_stem: str | None):
    """Store the bytes at `stem`'s tier, then answer with what now resolves.

    The reply is the slot as it stands rather than a bare 201: a shared file is
    outranked by any table-specific one, so "written" and "in use" are different
    facts and the caller should not have to guess which it got.
    """
    import tempfile

    known = {spec.kind for spec in MEDIA_SPECS}
    if kind not in known:
        raise InvalidRequestError("Unknown media kind",
                                  details={"unknown": kind, "known": sorted(known)})
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    suffix = Path(upload.filename or "").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as staged:
        staged.write(await upload.read())
        staged_path = staged.name
    try:
        written = await run_in_threadpool(
            media_placement.place, game_dir, kind, stem, staged_path)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    finally:
        Path(staged_path).unlink(missing_ok=True)

    await run_in_threadpool(media_placement.record_origin, game_dir, written)
    entries = _media_entries(_resolved_media(game_dir, table_stem), game_dir, prefix)
    return {"written": written.name, "media": {kind: entries[kind]}}


def _file_facts(path: Path, kind: str) -> dict:
    """Size, date and pixel size - what tells two candidates for a slot apart.

    Every part is best-effort: a file that cannot be opened still has a name worth
    showing, and a slot that reports nothing at all is worse than one missing a number.
    """
    from common.media_specs import media_family

    facts: dict = {"size_bytes": None, "modified": None, "width": None, "height": None}
    try:
        stat = path.stat()
    except OSError:
        return facts
    facts["size_bytes"] = stat.st_size
    facts["modified"] = datetime.fromtimestamp(stat.st_mtime,
                                               tz=UTC).isoformat()
    if media_family(kind) == "image":
        try:
            from PIL import Image
            with Image.open(path) as img:
                facts["width"], facts["height"] = img.size
        except Exception:
            logger.debug("Could not read image size for %s", path, exc_info=True)
    return facts


def _media_detail(game, kind: str, table_stem: str | None, prefix: str) -> dict:
    """One slot: the winner, what it is, and every tier that holds a file for it."""
    from common.media_specs import MEDIA_SPECS, canonical_kind, media_candidates, media_family

    kind = canonical_kind(kind)
    if kind not in {spec.kind for spec in MEDIA_SPECS}:
        raise InvalidRequestError("Unknown media kind",
                                  details={"unknown": kind,
                                           "known": sorted(spec.kind for spec in MEDIA_SPECS)})
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    hit = _resolved_media(game_dir, table_stem).get(kind)
    path = hit.path if hit is not None else None

    files, medias = _media_contents(game_dir)
    variant, active_sets = _media_settings()
    candidates = media_candidates(game_dir, files, medias, kind, variant,
                                  table_stem, active_sets)
    return {
        "kind": kind,
        "family": media_family(kind),
        "present": path is not None,
        "file": path.name if path is not None else None,
        "via": hit.tier if hit is not None else None,
        "origin": (asset_origin.origin_of(asset_origin.ledger(game_dir), game_dir, path)
                   or None) if path is not None else None,
        "tiers": [{"tier": item.tier, "file": item.path.name,
                   "wins": item.path == path}
                  for item in candidates],
        "links": {"self": f"{prefix}/{kind}" if path is not None else None},
        **(_file_facts(path, kind) if path is not None else
           {"size_bytes": None, "modified": None, "width": None, "height": None}),
    }


def _into_slot(game, kind: str, table_id: str, source: Path, game_id: str,
               origin: str = "user") -> dict:
    """Copy a file into the slot and answer with what now resolves.

    Shared by every route that fills a slot from a file that already exists somewhere -
    one on this machine, one the catalog published. Where the source is allowed to be
    is each caller's own question; this one is only about the write.
    """
    known = {spec.kind for spec in MEDIA_SPECS}
    if kind not in known:
        raise InvalidRequestError("Unknown media kind",
                                  details={"unknown": kind, "known": sorted(known)})
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    table_stem = _table_stem_or_404(game, table_id) if table_id else game_dir.name
    try:
        written = media_placement.place(game_dir, kind, table_stem, source)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    # Recorded with who placed it, which is what lets a later media refresh tell its
    # own art from something hand-placed and leave the latter alone.
    media_placement.record_origin(game_dir, written, origin)
    prefix = (f"/api/v1/games/{game_id}/tables/{table_id}/media" if table_id
              else f"/api/v1/games/{game_id}/media")
    entries = _media_entries(_resolved_media(game_dir, table_stem if table_id else None),
                             game_dir, prefix)
    return {"written": written.name, "media": {kind: entries[kind]}}


def _placement(game_dir: Path, kind: str, spec, table_id: str, stem: str,
               label: str) -> dict:
    """One destination: what the file would be called there, and what it would take.

    The extension is trimmed back off the name because the file decides it, and it is
    only supplied here to satisfy the family check.
    """
    suffix = spec.family[0]
    going = media_placement.displaced(game_dir, kind, stem, suffix)
    return {"table": table_id, "label": label,
            "base": media_placement.target_name(kind, stem, suffix)[:-len(suffix)],
            "displaces": sorted(str(path.relative_to(game_dir)) for path in going)}


@router.get("/{game_id}/media/{kind}/placements",
            summary="Where a file for this kind could go, and what it would replace",
            dependencies=[requires(scopes.GAMES_READ)])
def get_placements(game_id: str, kind: str) -> models.MediaPlacementList:
    """Every name this kind can take in this folder, with the cost of each.

    The tier is a filename, so choosing where a file lands is choosing what it is
    called - and that is a decision worth making at the moment of the write rather
    than inferring from which lens somebody happened to leave open.

    Answered without the file, because it can be: what a write displaces is the whole
    family at that tier, which does not depend on the extension arriving.
    """
    spec = next((item for item in MEDIA_SPECS if item.kind == kind), None)
    if spec is None:
        raise InvalidRequestError("Unknown media kind",
                                  details={"unknown": kind,
                                           "known": sorted(item.kind for item in MEDIA_SPECS)})
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")

    found = [_placement(game_dir, kind, spec, "", game_dir.name,
                        "Shared by every table")]
    for table in _tables(game, game_to_row(game)):
        stem = Path(table["filename"]).stem
        option = _placement(game_dir, kind, spec, table["id"], stem, table["filename"])
        # A .vpx named after its folder makes the two tiers the same filename, and they
        # are then the same file - the resolver finds it looking for either. Most
        # single-table folders are like that, so this is the common case rather than a
        # corner, and offering both would be two choices that do one thing.
        if table.get("id") and option["base"] not in {item["base"] for item in found}:
            found.append(option)
    return {"placements": found, "extensions": list(spec.family)}


@router.post("/{game_id}/media/{kind}/import",
             summary="Put a file from this machine into a slot",
             dependencies=[requires(scopes.GAMES_WRITE), requires(scopes.FILESYSTEM_READ)])
def import_media(game_id: str, kind: str, body: models.MediaImport) -> models.MediaWritten:
    """Copy artwork in from anywhere on this machine the hub is allowed to read.

    Both scopes, because it is both things: it reads a file off the disk and it writes
    a game's media, and holding one of those is not permission for the other.

    A copy, not a move. The file is as likely to be a download somebody wants to keep
    as a stray, and deciding that for them is not this operation's job.
    """
    game = _game_or_404(game_id)
    source = filesystem.within_roots(body.path)
    if not source.is_file():
        raise InvalidRequestError("That is not a file", details={"path": body.path})
    return _into_slot(game, kind, body.table, source, game_id)


@router.post("/{game_id}/media/{kind}/fetch",
             summary="Take a file from an online catalog into a slot",
             dependencies=[requires(scopes.GAMES_WRITE), requires(scopes.VPS_READ)])
def fetch_media(game_id: str, kind: str, body: models.MediaFetch) -> models.MediaWritten:
    """Download what an online catalog publishes and put it in the slot.

    A source and an id, never a URL: the only links this follows are ones a source
    produced for that id and kind, which is what stops it being a way to make the hub
    fetch whatever a caller likes. The id does not have to be this game's - a mod, or a
    game the matcher got wrong, is exactly when the art has to come from another entry.
    """
    import tempfile

    from common.http_client import download_file
    from common.online import asset_sources

    from .mediasources import enabled_ids

    game = _game_or_404(game_id)
    offer = asset_sources.url_for(body.source, kind, body.vps_id, body.size,
                                  enabled_ids())
    if offer is None:
        raise NotFoundError("That source has no such art",
                            details={"source": body.source, "vps_id": body.vps_id,
                                     "kind": kind, "size": body.size})
    with tempfile.TemporaryDirectory() as staging:
        staged = Path(staging) / Path(offer.url).name
        try:
            download_file(offer.url, staged)
        except Exception as exc:
            raise FeatureUnavailableError(
                f"Could not reach {body.source}: {exc}") from exc
        # Stamped with the source, so a later refresh can tell its own art from
        # somebody else's and leave the latter alone.
        return _into_slot(game, kind, body.table, staged, game_id, offer.source)


@router.get("/{game_id}/media/{kind}/detail", summary="One shared slot, in detail",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media_detail(game_id: str, kind: str) -> models.MediaDetail:
    """What a curator needs about a slot and a frontend never asks for - the file's
    size and shape, and every tier holding one, not just the tier that won."""
    game = _game_or_404(game_id)
    return _media_detail(game, kind, None, f"/api/v1/games/{game_id}/media")


@router.get("/{game_id}/tables/{table_id}/media/{kind}/detail",
            summary="One build's slot, in detail",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media_detail(game_id: str, table_id: str, kind: str) -> models.MediaDetail:
    game = _game_or_404(game_id)
    return _media_detail(game, kind, _table_stem_or_404(game, table_id),
                         f"/api/v1/games/{game_id}/tables/{table_id}/media")


@router.post("/{game_id}/media/{kind}/retier",
             summary="Rename a placed file so it serves a different tier",
             dependencies=[requires(scopes.GAMES_WRITE)])
def retier_media(game_id: str, kind: str, body: models.MediaRetier,
                 table: str = Query("", description="the build the file serves now")
                 ) -> models.MediaWritten:
    """Change who a file serves without sending it again.

    The tier is the filename, so this is a rename. `table` says where the file is now
    and the body says where it should go; either may be empty, which means the folder's
    shared name.
    """
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    from_stem = _table_stem_or_404(game, table) if table else game_dir.name
    to_stem = _table_stem_or_404(game, body.table) if body.table else game_dir.name
    try:
        written = media_placement.retier(game_dir, kind, from_stem, to_stem)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc

    prefix = (f"/api/v1/games/{game_id}/tables/{body.table}/media" if body.table
              else f"/api/v1/games/{game_id}/media")
    stem = to_stem if body.table else None
    entries = _media_entries(_resolved_media(game_dir, stem), game_dir, prefix)
    return {"written": written.name, "media": {kind: entries[kind]}}


def _displaced(game, kind: str, stem: str, filename: str) -> dict:
    """What a place of `filename` would displace at `stem`'s tier."""
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    try:
        going = media_placement.displaced(game_dir, kind, stem, Path(filename).suffix)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return {"displaced": sorted(str(path.relative_to(game_dir)) for path in going)}


@router.get("/{game_id}/media/{kind}/displaced",
            summary="What placing this file here would replace",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_media_displaced(game_id: str, kind: str,
                             filename: str = Query(...)) -> models.MediaDisplaced:
    """Asked before an upload, so a confirmation can name the files rather than warn
    in the abstract - and so the bytes are not sent for a drop the user cancels."""
    game = _game_or_404(game_id)
    return _displaced(game, kind, Path(getattr(game, "fullPathGame", "")).name, filename)


@router.get("/{game_id}/tables/{table_id}/media/{kind}/displaced",
            summary="What placing this file for one build would replace",
            dependencies=[requires(scopes.GAMES_READ)])
def get_table_media_displaced(game_id: str, table_id: str, kind: str,
                              filename: str = Query(...)) -> models.MediaDisplaced:
    game = _game_or_404(game_id)
    return _displaced(game, kind, _table_stem_or_404(game, table_id), filename)


@router.put("/{game_id}/media/{kind}", summary="Place a file every table shares",
            dependencies=[requires(scopes.GAMES_WRITE)])
async def put_game_media(game_id: str, kind: str,
                         file: UploadFile = File(...)) -> models.MediaWritten:
    """Named for the folder, so every table in it resolves this unless it has its own."""
    game = _game_or_404(game_id)
    return await _write_media(game, kind, Path(getattr(game, "fullPathGame", "")).name,
                              file, f"/api/v1/games/{game_id}/media", None)


@router.put("/{game_id}/tables/{table_id}/media/{kind}",
            summary="Place a file for one build", dependencies=[requires(scopes.GAMES_WRITE)])
async def put_table_media(game_id: str, table_id: str, kind: str,
                          file: UploadFile = File(...)) -> models.MediaWritten:
    """Named for this .vpx, so it serves this build and no other."""
    game = _game_or_404(game_id)
    stem = _table_stem_or_404(game, table_id)
    return await _write_media(
        game, kind, stem, file,
        f"/api/v1/games/{game_id}/tables/{table_id}/media", stem)


@router.delete("/{game_id}/media/{kind}", summary="Remove the file every table shares",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_game_media(game_id: str, kind: str) -> models.MediaRemoved:
    """Only the folder-named file. A build's own art and the default both survive."""
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    try:
        removed = media_placement.remove(game_dir, kind, game_dir.name)
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return {"removed": removed}


@router.delete("/{game_id}/tables/{table_id}/media/{kind}",
               summary="Remove one build's file",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_table_media(game_id: str, table_id: str, kind: str) -> models.MediaRemoved:
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    try:
        removed = media_placement.remove(game_dir, kind,
                                         _table_stem_or_404(game, table_id))
    except media_placement.UnplaceableError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return {"removed": removed}


@router.delete("/{game_id}/tables/{table_id}", summary="Forget a table that is gone",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_table(game_id: str, table_id: str) -> models.TableForgotten:
    """Drop the record of a table whose file is no longer there.

    No file is deleted, because there is none - what goes is the entry describing it.
    Refused while the .vpx is on disk: that entry describes something the user owns, and
    the next refresh would mint it again anyway. Putting the file back and refreshing
    brings the table back, under a new id.
    """
    game = _game_or_404(game_id)
    config = load_game_meta(game)
    entry = table_entries(config).get(table_id)
    if not isinstance(entry, dict):
        raise NotFoundError("This game has no such table",
                            details={"game": getattr(game, "gameDirName", ""),
                                     "table": table_id})
    if not entry.get(ABSENT_SINCE_KEY):
        raise ConflictError("That table's file is still on disk, so its record stands",
                            details={"table": table_id,
                                     "filename": entry.get("filename", "")})

    meta = MetaConfig(str(meta_file_path(game)))
    meta.forget_table(table_id)
    # The scan's copy still describes the table that just went.
    game.meta_config = load_game_meta(game)
    return {"forgotten": table_id}


@router.post("/{game_id}/launch", summary="Launch a game on this play host",
             status_code=202, dependencies=[requires(scopes.LAUNCH_INVOKE)])
def launch_game(game_id: str,
                 payload: models.LaunchRequest | None = Body(default=None),
                 ) -> models.LaunchAccepted:
    """Start a game and return once it is starting, not once it is over.

    The same service the wheel and the Remote Control page use, so a launch from
    here counts as a play and releases the peripherals like any other.
    """
    game = _game_or_404(game_id)
    table = (payload.file or None) if payload else None
    ini_config = get_ini_config()

    try:
        resolved = launch.check_launchable(game, ini_config, table)
    except launch.LaunchBusyError as exc:
        raise ConflictError(str(exc)) from exc
    except launch.UnknownTableError as exc:
        raise InvalidRequestError(str(exc), details={"file": table}) from exc
    except launch.LaunchUnavailableError as exc:
        raise FeatureUnavailableError(str(exc)) from exc

    def run():
        try:
            launch.launch_game(game, ini_config, source=launch_state.SOURCE_API,
                                table=table)
        except Exception:
            logger.exception("Launch of %s failed", game_id)

    threading.Thread(target=run, daemon=True,
                     name=f"api-launch-{game_id[:8]}").start()
    return {"launching": True, "game_id": game_id,
            "file": Path(resolved).name,
            "links": {"state": "/api/v1/play/state", "events": "/api/v1/events"}}


@router.put("/{game_id}/rating", summary="Rate a game",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_rating(game_id: str, payload: models.RatingRequest) -> models.Rating:
    """Set `User.Rating` on a game, 0-5.

    A whole-value PUT rather than a PATCH: the rating is the resource, and sending
    it again is the same request twice rather than a second increment.
    """
    game = _game_or_404(game_id)
    return {"rating": set_game_rating(game, payload.rating)}


@router.get("/{game_id}/archive", summary="Download the game folder as an archive",
            dependencies=[requires(scopes.GAMES_READ)])
def get_game_archive(request: Request, game_id: str, download_token: str = "",
                      full: bool = False, file: str = ""):
    from common.games.archive_service import cleanup_archive, create_vpxz_archive

    game = _game_or_404(game_id)
    if full:
        # The default bundle rides games:read; the whole folder is its own
        # permission. Local trust grants both today.
        identity = getattr(request.state, "identity", None)
        if identity is None or not identity.can(scopes.GAMES_EXPORT_FULL):
            raise ForbiddenError(f"Requires {scopes.GAMES_EXPORT_FULL}")
    game_dir_name = getattr(game, "gameDirName", "")
    try:
        archive = create_vpxz_archive(game_dir_name, everything=full,
                                      table=file or None)
    except ValueError as exc:
        raise InvalidRequestError("Invalid game path") from exc
    except FileNotFoundError as exc:
        raise NotFoundError("Game not found") from exc

    logger.info("Created download archive: %s", archive.path)

    def cleanup():
        cleanup_archive(archive)
        logger.info("Cleaned up temp archive: %s", archive.temp_dir)

    headers = {}
    if download_token and download_token.isalnum():
        # Progress signal for the page that started the download. Not authentication.
        headers["Set-Cookie"] = (
            f"vpinfe_vpxz_download_{download_token}=1; Max-Age=60; Path=/; SameSite=Lax")

    return FileResponse(
        archive.path,
        media_type="application/octet-stream",
        filename=archive.filename,
        headers=headers,
        background=BackgroundTask(cleanup),
    )
