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
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Body, File, Query, Request, UploadFile
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from common.config_access import MediaConfig
from common.games import (
    apps,
    asset_origin,
    asset_registry,
    asset_resolver,
    game_identity,
    game_service,
    library_discovery,
    media_lookup,
    media_placement,
)
from common.games.game_metadata import (
    adopt_vps_details,
    game_vps_id,
    load_game_meta,
    meta_file_path,
    reset_game_play_record,
    reset_table_play_record,
    set_game_favorite,
    set_game_rating,
    set_game_tags,
    set_table_rating,
    set_table_source,
    table_play_record,
    table_rating,
    table_source,
    vpinfe_section,
    vps_details_differ,
)
from common.games.game_repository import (
    all_games,
    collections_by_game_id,
    game_to_row,
)
from common.games.game_service import find_vps_release
from common.games.info_file import VPINFE_SECTION, MetaConfig
from common.games.tables import (
    ABSENT_SINCE_KEY,
    TABLE_ID_KEY,
    default_table,
    entry_filename,
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
from common.online import obtainability, vps_kinds
from common.paths import get_ini_config

from . import filesystem, models, scopes
from .auth import ForbiddenError, requires
from .errors import ConflictError, FeatureUnavailableError, InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.games")

router = APIRouter(prefix="/games", tags=["games"])

# What the script was seen to use, named for the thing rather than for the .info key
# it sits under. Scorbit is spelled the way the product is - the Manager UI's
# "Scorebit" label is the typo, not the key.
FEATURE_KEYS = {
    "nfozzy": "detect_nfozzy", "fleep": "detect_fleep", "ssf": "detect_ssf",
    "lut": "detect_lut", "scorbit": "detect_scorbit",
    "fastflips": "detect_fastflips", "flexdmd": "detect_flex",
    "pinmame": "detect_pinmame",
}


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
        # The effective id, not the discovered one: `alt_vpsid` is somebody saying the
        # match was wrong, and every other field here is already the value in force -
        # `name` is the alt title the moment one is set. `discovered` below is what an
        # undo reverts to, and is the only place the superseded id belongs.
        "vps_id": row.get("alt_vpsid", "") or row.get("vpsid", ""),
        "name": row.get("name", ""),
        "manufacturer": row.get("manufacturer", ""),
        "year": str(row.get("year") or ""),
        "type": row.get("type", ""),
        "themes": row.get("themes") or [],
        "authors": row.get("authors") or [],
        "rom": row.get("rom", ""),
        "version": row.get("version", ""),
        # How many tables this game offers, so a client can tell a row that collapses
        # six from one that collapses one. `rom` and `version` above are read off the
        # default table; this is what says whether there was a choice to make.
        "table_count": int(row.get("table_count") or 0),
        "rating": row.get("rating", 0),
        "collections": row.get("collections") or [],
        "folder": str(row.get("game_dir", "") or ""),
        "overrides": {
            "alt_title": row.get("alt_title", ""),
            "alt_vps_id": row.get("alt_vpsid", ""),
            "frontend_dof_event": row.get("frontend_dof_event", ""),
        },
        # Surfacing it, never resolving through it: `tests/invariants/test_parked_override`
        # asserts the difference, and this file is on its allowlist for that reason.
        "parked_vps_id": _parked_match(row),
        "discovered": {
            "name": row.get("found_name", ""),
            "vps_id": row.get("vpsid", ""),
        },
        # Assets, not media: these are what the game needs to play as intended.
        # Media is the artwork VPinFE shows while browsing - see docs/conventions.md.
        # Summary from the scan; the detail endpoint recomputes and attributes files.
        "assets": _asset_summary(row),
        "user": row.get("user") or {},
        "links": {
            "self": prefix,
            "tables": f"{prefix}/tables",
            "media": f"{prefix}/media",
            "archive": f"{prefix}/archive",
            "launch": f"{prefix}/launch",
            "rating": f"{prefix}/rating",
        },
    }


def _table_overrides(entry: dict, folder: dict) -> dict:
    """One table's overrides, falling back to the folder's for a 2.x library."""
    own = entry.get(VPINFE_SECTION) or {}

    def pick(key, default=""):
        value = own.get(key, folder.get(key, default))
        return default if value in ("", None) else value

    return {
        "alt_launcher": str(pick("alt_launcher")),
        "plugin_profile": str(pick("plugin_profile")),
        "delete_nvram_on_close": bool(pick("delete_nvram_on_close", False)),
    }


def _parked_match(row: dict) -> dict | None:
    """A superseded manual match, for the surface that offers it back."""
    parked = row.get("alt_vpsid_previous")
    if not isinstance(parked, dict) or not str(parked.get("value") or "").strip():
        return None
    return {"value": str(parked["value"]).strip(),
            "table": str(parked.get("table") or ""),
            "set_aside": str(parked.get("set_aside") or "")}


def _asset_summary(row: dict) -> dict:
    """Presence per kind, as objects so a kind can grow attributes without a
    breaking change. alt_color keeps its formats - the flat boolean lost them."""
    formats = [name for name, flag in (("serum", "serum_exists"), ("vni", "vni_exists"))
               if row.get(flag)]
    return {
        "backglass": {"present": bool(row.get("b2s_exists"))},
        # `ini`, not `settings`: hubui has a Settings section, and one word for a
        # nav destination and a file kind is two things sharing a name.
        "ini": {"present": bool(row.get("ini_exists"))},
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


def _named_source(described_entry: dict) -> dict | None:
    """A table's binding with the release named, or None where there is no binding.

    The catalog is already loaded here and the client's alternative is asking for the
    whole release list to resolve one id, so the naming happens on this side.
    """
    source = table_source(described_entry)
    if not source.get("vps_file_id"):
        return source or None
    release = find_vps_release(str(source["vps_file_id"]))
    if release:
        source["version"] = str(release.get("version") or "")
        source["authors"] = [str(name) for name in (release.get("authors") or [])]
    return source


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
    recorded = recorded_default(vpinfe_section(game.meta_config), described)
    default = default_table(files or names, game_dir.name, recorded)
    # Why this one, not only which one. `default_table` falls through a recorded choice,
    # a filename matching the folder, then first alphabetically - which its own docstring
    # calls "deterministic rather than correct". A reader does not care which of the last
    # two happened; they care whether they chose it or we did (HUBUI section 13).
    #
    # "user" only where the recorded choice is what actually won: a recorded name whose
    # table has since gone falls through to a derived pick, and calling that a choice
    # would be a lie.
    default_kind = "user" if recorded and recorded == default else "auto"
    hidden = hidden_tables(described)

    # Dependency context, once per request: the alias map and the rom listing are
    # shared by every table in the folder.
    aliases = asset_resolver.read_alias_map(str(game_dir))
    rom_files = asset_resolver.list_rom_files(str(game_dir))

    # 2.x wrote these three at the folder, when a folder was one file. They are the
    # table's now; a folder value is still read as the fallback, so a library written
    # by 2.x keeps working and the one-table case - which is what 2.x had - is
    # unchanged. Writes only ever land on the table.
    folder_vpinfe = vpinfe_section(game.meta_config)

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
            # Which program plays it, from the registry rather than assumed. Today
            # every table is Visual Pinball's; the point is that the next one is a
            # registry entry and not a search for where ".vpx" was hard-coded.
            "format": (apps.app_for(name) or apps.DEFAULT_APP).id,
            "app": (apps.app_for(name) or apps.DEFAULT_APP).id,
            "filename": name,
            "version": str(described_entry.get("version", "") or ""),
            "authors": [str(a) for a in (described_entry.get("authors") or [])],
            "file_hash": str(described_entry.get("file_hash", "") or ""),
            "vbs_hash": str(described_entry.get("vbs_hash", "") or ""),
            # Tri-state throughout: a table nobody has parsed answers null for every
            # feature, which is not the same as answering no to all of them.
            "features": {name: _tristate(described_entry.get(key))
                         for name, key in FEATURE_KEYS.items()},
            "overrides": _table_overrides(described_entry, folder_vpinfe),
            # Which upstream release this file is, where anything has established it.
            # Absent on almost every table and that is the honest answer: nothing has
            # looked, which is a different state from having looked and found nothing.
            # Named, not just identified - a client showing the bare id would be putting
            # an id on screen, and would need a second round trip to avoid it.
            "source": _named_source(described_entry),
            "default": name == default,
            # Empty on every table that is not the default: the kind is a fact about
            # the one that is, not a field every row carries a blank for.
            "default_kind": default_kind if name == default else "",
            "hidden": name in hidden,
            # The table's own rating, which this lens has to carry as well as the play
            # lens - a hub reads tables here and would otherwise see every one unrated.
            "rating": table_rating(described_entry),
            "user": table_play_record(described_entry),
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
        # One answer to "will this run", from the kinds declared required rather than
        # from the two a client happens to be shown.
        entry["launchable"] = asset_registry.launchable(
            entry["available"], bool(chain.get("declared")), chain.get("installed"))
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


@router.get("/{game_id}/media/overrides",
            summary="Kinds where a table has art of its own",
            dependencies=[requires(scopes.GAMES_READ)])
def get_media_overrides(game_id: str) -> models.MediaOverrideList:
    """Where the game's art is not the whole story.

    Asked from the game's own lens, which otherwise cannot see a table-specific file at
    all: resolving without a table stem never looks at that tier. A curator scanning a
    folder wants the odd one out, and the odd one out is invisible without this.

    One walk for every kind and every table, because the caller is drawing a map of all
    of them and twenty round trips to answer one question would be worse.
    """
    from common.media_specs import MEDIA_SPECS, media_candidates

    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    files, medias = _media_contents(game_dir)
    variant, active_sets = _media_settings()

    # What the game itself resolves, to compare against. A .vpx named after its folder
    # makes its own tier and the game's the same filename, and then the same file - so
    # without this it is reported as overriding itself, which is most single-table
    # folders and the commonest shape there is.
    shared = {spec.kind: next((item.path for item in media_candidates(
        game_dir, files, medias, spec.kind, variant, None, active_sets)), None)
        for spec in MEDIA_SPECS}

    found: dict[str, list[dict]] = {}
    for table in _tables(game, game_to_row(game)):
        stem = Path(str(table.get("filename") or "")).stem
        if not table.get("id") or not stem:
            continue
        for spec in MEDIA_SPECS:
            own = next((item for item in media_candidates(
                game_dir, files, medias, spec.kind, variant, stem, active_sets)
                if item.tier == "table"), None)
            if own is not None and own.path != shared.get(spec.kind):
                found.setdefault(spec.kind, []).append({
                    "table": table["id"],
                    "filename": table.get("filename") or "",
                    "version": table.get("version") or "",
                    "file": own.path.name,
                })
    return {"overrides": found}


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
            # `as_posix`, never `str`: a relative path on the wire is forward-slashed
            # whatever host built it. `str(WindowsPath)` gave clients "medias\\bg.png"
            # on Windows and "medias/bg.png" everywhere else, for the same library.
            "displaces": sorted(path.relative_to(game_dir).as_posix()
                                for path in going)}


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
    # Forward-slashed on the wire whatever host built it - see `_placements`.
    return {"displaced": sorted(path.relative_to(game_dir).as_posix()
                                for path in going)}


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


@router.put("/{game_id}/tables/{table_id}/hidden",
            summary="Offer this table in the frontend, or stop offering it",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_hidden(game_id: str, table_id: str,
                     body: models.TableVisibility) -> models.Table:
    """Take a table out of play without taking it off disk.

    The two are different acts and only one is reversible by itself: a hidden table is
    still there with its stats and its match, and a patch base that stopped being
    offered is exactly what this is for.
    """
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    meta = MetaConfig(str(meta_file_path(game)))
    meta.set_table_hidden(filename, bool(body.hidden))
    game.meta_config = load_game_meta(game)
    return _table_or_404(game, table_id)


@router.post("/{game_id}/tables/{table_id}/script",
             summary="Extract this table's script beside it",
             dependencies=[requires(scopes.GAMES_WRITE)])
def extract_table_script(game_id: str, table_id: str) -> models.Table:
    """Write the table's script out as a `<table>.vbs` next to the .vpx.

    **This changes which script the table runs.** VPX loads a sidecar in place of the
    one inside the .vpx, so extracting is how a table is patched - and it is why the
    hub reports the script as internal or external rather than as merely extracted.

    Runs the configured launcher with `-extractvbs`, so it answers for the machine it
    is called on, the same as `/launch`: a hub with no VPX installed cannot do this.
    """
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    if not (game_dir / filename).is_file():
        raise NotFoundError("That table's file is not on disk",
                            details={"table": table_id})
    launcher = _table_overrides(
        entry_for_filename(table_entries(game.meta_config), filename)[1] or {},
        vpinfe_section(game.meta_config)).get("alt_launcher", "")
    # Asked before the work rather than read out of the failure: with the table's file
    # accounted for, every remaining launcher error means this machine cannot do it,
    # which is 501 and the answer /launch already gives - not a missing resource.
    from common.config_access import SettingsConfig
    binary, _source, configured = launch.get_effective_launcher(
        SettingsConfig.from_config(get_ini_config()).vpx_bin_path,
        {VPINFE_SECTION: {"alt_launcher": launcher}})
    if not binary or not Path(binary).exists():
        # The label a person reads in Settings, and the section it is really in: the
        # key is `general.vpx_bin_path`, and `Settings` is its 2.x alias.
        raise FeatureUnavailableError(
            "Extracting a script runs Visual Pinball, and this machine has none. "
            + (f"General - VPX Executable Path points at {configured or binary}, "
               "which is not there." if (configured or binary)
               else "Set General - VPX Executable Path in Settings."))
    try:
        game_service.extract_vbs(game_dir, filename, launcher)
    except Exception as exc:
        raise InvalidRequestError(f"Could not extract the script: {exc}") from exc
    return _table_or_404(game, table_id)


@router.delete("/{game_id}/tables/{table_id}/script",
               summary="Remove the script beside this table",
               dependencies=[requires(scopes.GAMES_WRITE)])
def delete_table_script(game_id: str, table_id: str) -> models.Table:
    """Take the sidecar away, which puts the table back on the script inside its .vpx.

    Whatever the sidecar held goes with it - a patch, an edit - and nothing else knows
    what was in it, which is why the surface asks first.
    """
    game = _game_or_404(game_id)
    game_dir = Path(getattr(game, "fullPathGame", "") or "")
    script = game_dir / f"{_table_stem_or_404(game, table_id)}.vbs"
    if not script.is_file():
        raise NotFoundError("This table has no script beside it",
                            details={"table": table_id})
    script.unlink()
    return _table_or_404(game, table_id)


@router.put("/{game_id}/tables/{table_id}/rating", summary="Rate one table",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_rating(game_id: str, table_id: str,
                     payload: models.RatingRequest) -> models.Table:
    """A table's own rating, which refines the game's rather than replacing it.

    INFO-SCHEMA section 8.1 left this open on one question - how a user sets a table's
    rating when the wheel shows one entry per game. The hub's Tables grid is the answer:
    the row you rate is the file. Additive on both lenses, as that section says.

    Returns the table rather than the rating, because a client that just rated one is
    about to redraw the row.
    """
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    set_table_rating(game, filename, payload.rating)
    game.meta_config = load_game_meta(game)
    return _table_or_404(game, table_id)


@router.put("/{game_id}/tables/{table_id}/source", summary="Say which release a table is",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_source(game_id: str, table_id: str,
                     payload: models.TableSourceRequest) -> models.Table:
    """Bind one table to the upstream release somebody says it is, or unbind it.

    A person picking from a list, never a guess: the identifier this records was
    retired at chance and is confidently wrong more often than not, so nothing here
    proposes an answer. An empty id takes the claim back.

    Returns the table, because a client that just bound one is about to redraw the row.
    """
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    set_table_source(game, filename, payload.vps_file_id)
    game.meta_config = load_game_meta(game)
    return _table_or_404(game, table_id)


def _entry_for(game) -> dict:
    """The catalog entry this game is matched to, effective id first."""
    from common.games.game_service import load_vpsdb

    wanted = game_vps_id(game)
    if not wanted:
        return {}
    return next((e for e in load_vpsdb() if str(e.get("id") or "") == wanted), {})


@lru_cache(maxsize=1)
def _crowded_links_for(size: int) -> frozenset[str]:
    """The links standing behind enough records to be somewhere to browse.

    Keyed on the catalog's length, which is a cheap stand-in for "the snapshot has been
    replaced" - the alternative is walking 17,000 URLs on every request to answer a
    question about the corpus that changes only when the corpus does.
    """
    from common.games.game_service import load_vpsdb

    return obtainability.crowded(
        link.get("url")
        for entry in load_vpsdb()
        for kind in vps_kinds.BY_LISTING
        for record in (entry.get(kind) or [])
        for link in (record.get("urls") or []))


def _crowded_links() -> frozenset[str]:
    from common.games.game_service import load_vpsdb

    return _crowded_links_for(len(load_vpsdb()))


# The inventory still answers for colour and sound under the flat names it used before
# the asset registry existed. Translated here rather than in the kind table, which
# names the registry's kinds because those are the real ones.
_INVENTORY_NAME = {"altcolor_serum": "alt_color", "altcolor_vni": "alt_color",
                   "altsound": "alt_sound"}


def _we_hold(kind, inventory: dict, media: dict) -> bool:
    """Whether this game has any of what the entry is offering.

    Any, not all: a kind maps to more than one of ours where VPS draws the line in a
    different place, and holding either Serum or VNI is holding a colourisation.
    """
    for name in kind.ours:
        if kind.held_in == vps_kinds.MEDIA:
            if (media.get(name) or {}).get("present"):
                return True
        elif (inventory.get(_INVENTORY_NAME.get(name, name)) or {}).get("present"):
            return True
    return False


@router.get("/{game_id}/vps_state", summary="What the catalog lists for this game, kind by kind",
            dependencies=[requires(scopes.GAMES_READ)])
def get_vps_state(game_id: str) -> models.VpsState:
    """Per kind: whether we hold one, how many the entry lists, and whether any of
    those is a file rather than a page.

    State, not findings. Which of these is worth telling somebody about is a judgement
    the surface makes with the library in front of it, and a producer deciding it here
    would be baking in the judgement the measurements say we make badly.

    `obtainable` is the honest word: it says the catalog lists a file, never that the
    file is yours to take. A host can hold something this account may not see, and
    nothing on this side can tell that without asking.
    """
    game = _game_or_404(game_id)
    entry = _entry_for(game)
    game_dir = Path(game.fullPathGame)
    inventory = _inventory_assets(game_dir)
    prefix = f"/api/v1/games/{game_id}/media"
    media = _media_entries(_resolved_media(game_dir, None), game_dir, prefix)
    shared = _crowded_links()

    kinds = []
    for kind in vps_kinds.KINDS:
        records = list(entry.get(kind.listed_as) or []) if entry else []
        answers = [obtainability.best_of(
            [link.get("url") for link in (record.get("urls") or [])], shared)
            for record in records]
        kinds.append({
            "kind": kind.listed_as,
            "ours": list(kind.ours),
            "held": _we_hold(kind, inventory, media),
            "listed": len(records),
            "obtainable": sum(1 for word in answers
                              if word == obtainability.AVAILABLE),
            "why_not": sorted({word for word in answers
                               if word != obtainability.AVAILABLE}),
        })
    return {"matched": bool(entry), "kinds": kinds}


@router.get("/{game_id}/vps_details", summary="Where the game's details and its entry disagree",
            dependencies=[requires(scopes.GAMES_READ)])
def get_vps_details(game_id: str) -> models.VpsDetails:
    """Empty for a game whose details came from the entry it is still matched to.

    Which is every game that has never been re-matched: the details were written from
    the entry, so they agree with it by construction. Correcting a match is what fills
    this, and it fills it completely - the details go on describing the machine the
    game used to be.
    """
    game = _game_or_404(game_id)
    entry = _entry_for(game)
    if not entry:
        return {"differs": []}
    found = vps_details_differ(load_game_meta(game), entry)
    return {"differs": [{"field": field, "ours": _said(ours), "theirs": _said(theirs)}
                        for field, (ours, theirs) in found.items()]}


def _said(value) -> str:
    """One line a person reads, whatever the field holds - a year is a number and
    themes are a list, and a caller rendering a comparison wants neither shape."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value if value is not None else "")


@router.put("/{game_id}/vps_details", summary="Take the entry's details",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_vps_details(game_id: str) -> models.VpsDetails:
    """Make the game's details describe the entry it is matched to.

    All of them together: they are one machine's facts, and a library holding this
    one's year beside that one's maker describes no machine at all. `Info.VPSId` is not
    among them - it is what VPS supplied, and the value a surface offers to revert a
    corrected match to.

    Returns the disagreement that is left, which is none - a client that just adopted
    is about to redraw the panel, and this is what it would ask for next.
    """
    game = _game_or_404(game_id)
    entry = _entry_for(game)
    if not entry:
        raise NotFoundError("This game is matched to no VPS entry",
                            details={"game_id": game_id})
    adopt_vps_details(game, entry)
    return get_vps_details(game_id)


@router.put("/{game_id}/default_table", summary="Which table this game offers first",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_default_table(game_id: str, body: models.TableDefault) -> models.TableList:
    """Record the choice, or clear it by naming nothing.

    A game's default is the one a member naming only the game resolves to, so this is
    the difference between a collection playing the VR build and the desktop one.
    """
    game = _game_or_404(game_id)
    if body.table:
        _table_filename_or_404(game, body.table)
    meta = MetaConfig(str(meta_file_path(game)))
    try:
        meta.set_default_table(body.table)
    except ValueError as exc:
        raise InvalidRequestError(str(exc), details={"table": body.table}) from exc
    game.meta_config = load_game_meta(game)
    return {"tables": _tables(game, game_to_row(game))}


def _table_filename_or_404(game, table_id: str) -> str:
    """The .vpx an id names, or a 404. Distinct from the media lens's stem lookup:
    this one wants the name on disk, not the stem a file would be named after."""
    entry = table_entries(load_game_meta(game)).get(table_id)
    filename = entry_filename(entry) if isinstance(entry, dict) else ""
    if not filename:
        raise NotFoundError("This game has no such table",
                            details={"game": getattr(game, "gameDirName", ""),
                                     "table": table_id})
    return filename


def _table_or_404(game, table_id: str) -> dict:
    found = next((t for t in _tables(game, game_to_row(game))
                  if t.get("id") == table_id), None)
    if found is None:
        raise NotFoundError("This game has no such table", details={"table": table_id})
    return found


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


@router.put("/{game_id}/tags", summary="The tags on a game",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_tags(game_id: str, payload: models.TagsRequest) -> models.Tags:
    """Set the whole set, the way the rating sets a whole value.

    Not a bag: a repeat is dropped, so sending the same tag twice is the same request
    twice. Case is left alone - two spellings stay two tags until somebody merges them,
    and folding them here would hide the duplicate rather than let it be found.
    """
    game = _game_or_404(game_id)
    return {"tags": set_game_tags(game, payload.tags)}


@router.delete("/{game_id}/play_record", summary="Reset a game's play counters",
               dependencies=[requires(scopes.GAMES_WRITE)])
def reset_play_record(game_id: str) -> models.PlayRecord:
    """Put the counters back to nothing, leaving rating, favorite and tags alone.

    A DELETE, because what it removes is a record of what happened - and reset is the
    correction people actually want. A table launched twenty times while somebody was
    testing it reads as a favourite forever otherwise. Setting a count to a number is
    the migration case and is not this.
    """
    game = _game_or_404(game_id)
    return reset_game_play_record(game)


@router.delete("/{game_id}/tables/{table_id}/play_record",
               summary="Reset one table's play counters",
               dependencies=[requires(scopes.GAMES_WRITE)])
def reset_table_record(game_id: str, table_id: str) -> models.TablePlayRecord:
    """One table's counters. The game's total is not touched: they are two records of
    two things, and a game played on one build has still been played."""
    game = _game_or_404(game_id)
    filename = _table_filename_or_404(game, table_id)
    return reset_table_play_record(game, filename)


@router.put("/{game_id}/favorite", summary="Mark a game a favorite",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_favorite(game_id: str, payload: models.FavoriteRequest) -> models.Favorite:
    """Set `User.Favorite` on a game.

    A whole-value PUT, for the reason the rating gives: the flag is the resource, and
    sending it twice is the same request rather than a toggle that races itself.

    The field has been in the .info since the initial checkin with nothing ever writing
    it. This is the producer, and it writes a real boolean.
    """
    game = _game_or_404(game_id)
    return {"favorite": set_game_favorite(game, payload.favorite)}


# Which keys each level will accept. Declared rather than inferred, so sending a
# table's key to the game route is refused instead of silently doing nothing - a
# write that reports success and changes nothing is the worst of the options.
_GAME_OVERRIDES = {"alt_title": "alt_title", "alt_vps_id": "alt_vpsid",
                   "frontend_dof_event": "frontend_dof_event"}
_TABLE_OVERRIDES = ("alt_launcher", "plugin_profile", "delete_nvram_on_close")


def _sent(payload: models.OverridesPatch) -> dict:
    """Only the fields the client actually sent. `None` is "leave alone"; `""` and
    `false` are real values that clear an override."""
    return {name: value for name, value in payload.model_dump().items()
            if value is not None}


@router.put("/{game_id}/overrides", summary="Set a game's overrides",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_game_overrides(game_id: str,
                       payload: models.OverridesPatch) -> models.GameOverrides:
    """What the user says about the machine, kept beside what VPS said.

    A PATCH in effect: only what is sent is written, because the six overrides are
    edited one field at a time and restating the others would make every save a race
    with whatever another surface changed meanwhile.
    """
    game = _game_or_404(game_id)
    changes = _sent(payload)
    unknown = set(changes) - set(_GAME_OVERRIDES)
    if unknown:
        raise InvalidRequestError(
            f"Not the game's to set: {', '.join(sorted(unknown))}. "
            "These belong to a table - PUT the table's overrides instead.")

    game_dir = Path(game.fullPathGame)
    for name, value in changes.items():
        if not game_service.update_vpinfe_setting(game_dir, _GAME_OVERRIDES[name],
                                                  value):
            raise ConflictError(f"Could not write {name}")
    return _resource(game_to_row(_game_or_404(game_id)), game_id)["overrides"]


@router.put("/{game_id}/tables/{table_id}/overrides",
            summary="Set one table's overrides",
            dependencies=[requires(scopes.GAMES_WRITE)])
def put_table_overrides(game_id: str, table_id: str,
                        payload: models.OverridesPatch) -> models.TableOverrides:
    """What the user says about one launchable file.

    Written onto the table's own entry, never onto the folder - a folder value is read
    as a fallback for a 2.x library but is not where anything lands now.
    """
    game = _game_or_404(game_id)
    changes = _sent(payload)
    unknown = set(changes) - set(_TABLE_OVERRIDES)
    if unknown:
        raise InvalidRequestError(
            f"Not a table's to set: {', '.join(sorted(unknown))}. "
            "These belong to the game - PUT the game's overrides instead.")

    game_dir = Path(game.fullPathGame)
    entries = table_entries(load_game_meta(game))
    if table_id not in entries:
        raise NotFoundError(f"No table with id {table_id} in game {game_id}")
    for name, value in changes.items():
        if not game_service.update_table_vpinfe_setting(game_dir, table_id, name,
                                                        value):
            raise ConflictError(f"Could not write {name}")
    fresh = table_entries(load_game_meta(_game_or_404(game_id)))
    return _table_overrides(fresh.get(table_id) or {},
                            vpinfe_section(_game_or_404(game_id).meta_config))


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
