"""Getting a game the art it has no file for, and keeping the art we fetched current.

A slot is filled only when nothing serves it. What counts as wanted is Kinds and the
online sources that are on; the size is the one the display settings name.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from common import jobs, shutdown
from common.config_access import MediaConfig, cfg_bool
from common.games.game_metadata import effective_vps_id, normalize_meta
from common.i18n import t
from common.jobs import JobReporter
from common.media_specs import MEDIA_SPECS
from common.paths import get_ini_config

logger = logging.getLogger("vpinfe.common.games.media_fill")

_SPECS = {spec.kind: spec for spec in MEDIA_SPECS}

_lock = threading.Lock()
_pending: list[str] = []
_running = False


def enabled() -> bool:
    return cfg_bool(get_ini_config(), "updates", "get_art_for_new_games", True)


def kept_kinds() -> set[str]:
    """The kinds this library collects that some enabled source publishes."""
    from common.games.library_policy import get_library_policy
    from common.online import asset_sources

    hidden = set(get_library_policy().get("hidden_media_kinds"))
    offered: set[str] = set()
    for source in asset_sources.sources(asset_sources.enabled_ids()):
        offered |= source.kinds
    return {kind for kind in _SPECS if kind not in hidden and kind in offered}


def _reachable() -> tuple[str, ...]:
    """The enabled sources that answer now, asking each once and naming each that does
    not. Never empty for "all": an empty answer means nothing can be asked."""
    from common.online import asset_sources

    live = []
    for source in asset_sources.sources(asset_sources.enabled_ids()):
        if source.reachable():
            live.append(source.id)
        else:
            logger.warning("%s could not be reached, so nothing is fetched from it "
                           "this time", source.name)
    return tuple(live)


def _unanswered(live: tuple[str, ...]) -> list[str]:
    from common.online import asset_sources

    return [source.name for source in asset_sources.sources(asset_sources.enabled_ids())
            if source.id not in live]


def _asked_as(kind: str, variant: str) -> str | None:
    """The kind to ask a source for to fill `kind`'s slot, or None to leave it.

    Under the FSS variant the playfield window shows the FSS render, and nothing
    publishes an FSS video, so a table video there would play over the wrong picture.
    """
    if variant == "fss":
        if kind == "playfield":
            return "playfield_fss"
        if kind == "playfield_video":
            return None
    return kind


def _size(kind: str, media: MediaConfig) -> str:
    group = _SPECS[kind].asset_group or ""
    return {"table_resolution": media.playfield_resolution,
            "table_video_resolution": media.playfield_video_resolution}.get(group, group)


def is_gap(row: dict[str, Any]) -> bool:
    """A media row the fill would fetch for: no file serves the game's tables, and no
    set someone chose answers the slot."""
    return (not row.get("table") and not row.get("present")
            and not str(row.get("standing_in") or "").startswith("set:"))


def _gaps(game_id: str) -> list[str]:
    from common.games import media_lens

    return [row["kind"] for row in media_lens.listing(game=game_id)["media"]
            if is_gap(row)]


def _fetch(game_id: str, kind: str, asked: str, vps_id: str, size: str,
           live: tuple[str, ...]) -> bool:
    """Put the source's file in the slot. False when no source has one."""
    from common.games import media_ops
    from common.http_client import download_file
    from common.online import asset_sources

    offers = asset_sources.offers(asked, vps_id, live)
    if not offers:
        return False
    offer = next((one for one in offers if one.size == size), offers[0])
    with tempfile.TemporaryDirectory() as staging:
        staged = Path(staging) / Path(offer.url).name
        download_file(offer.url, staged)
        media_ops.place_file(game_id, kind, "", staged, offer.source, offer.md5)
    return True


def _folders_to_games() -> dict[str, tuple[str, Any]]:
    from common.games import game_repository

    return {str(Path(str(game.full_path_game)).resolve()): (game_id, game)
            for game_id, game in game_repository.catalog().items()}


# A game, and the kinds to fill for it.
Target = tuple[str, Any, set[str]]


def _fill_games(targets: list[Target], live: tuple[str, ...],
                reporter: JobReporter | None,
                proceed: Callable[[], bool]) -> dict[str, int]:
    """Fetch each target's gaps. `filled` and `failed` count files; `unmatched` counts
    games with no VPS id, which nothing can be looked up for."""
    from common.games import game_repository, media_service

    counts = {"games": len(targets), "filled": 0, "unmatched": 0, "failed": 0}
    if not targets or not live:
        return counts
    media = MediaConfig.from_config(get_ini_config())
    for index, (game_id, game, wanted) in enumerate(targets):
        if not proceed():
            break
        name = str(game.game_dir_name or "")
        if reporter:
            reporter.progress(index, len(targets), t("said.getting_art_for", game=name))
        vps_id = effective_vps_id(normalize_meta(game.meta_config or {}))
        if not vps_id:
            counts["unmatched"] += 1
            continue
        placed = 0
        try:
            gaps = _gaps(game_id) if wanted else []
        except Exception:
            logger.exception("Getting art: could not read what %s has", name)
            continue
        for kind in gaps:
            asked = _asked_as(kind, media.playfield_variant) if kind in wanted else None
            if asked is None:
                continue
            try:
                if _fetch(game_id, kind, asked, vps_id, _size(asked, media), live):
                    placed += 1
            except Exception as exc:
                counts["failed"] += 1
                logger.warning("Getting art: could not get %s for %s: %s", kind, name, exc)
        if placed:
            counts["filled"] += placed
            media_service.invalidate_media_cache()
            game_repository.refresh_game(Path(str(game.full_path_game)))
    return counts


def _fill(folders: list[str], wanted: set[str], live: tuple[str, ...],
          reporter: JobReporter | None, proceed: Callable[[], bool]) -> dict[str, int]:
    games = _folders_to_games()
    found = [games.get(str(Path(folder).resolve())) for folder in folders]
    return _fill_games([(game_id, game, wanted) for game_id, game in filter(None, found)],
                       live, reporter, proceed)


def fill(folders: Iterable[str | Path], kinds: Iterable[str] | None = None,
         reporter: JobReporter | None = None) -> dict[str, int]:
    """Fetch what each game in `folders` is missing, of `kinds` or else the kept kinds.
    Never replaces a file, and never fetches a kind the library does not keep."""
    wanted = kept_kinds() if kinds is None else kept_kinds() & set(kinds)
    return _fill([str(folder) for folder in folders], wanted, _reachable(), reporter,
                 lambda: True)


def _scope(game_ids: Iterable[str] | None) -> dict[str, Any]:
    """The library's games named by `game_ids`, or all of them. Ids it does not hold
    are left out."""
    from common.games import game_repository

    held = game_repository.catalog()
    if game_ids is None:
        return dict(held)
    return {one: held[one] for one in dict.fromkeys(game_ids) if one in held}


def plan(game_ids: Iterable[str] | None = None) -> dict[str, Any]:
    """What getting missing art for these games would do, fetching nothing.

    Per kind the library keeps: how many games have no file for it, and how many of
    those an enabled source has one for. Reads the catalog index, never a file.
    """
    from common.games import media_lens
    from common.online import asset_sources

    scope = _scope(game_ids)
    kinds = [kind for kind in _SPECS if kind in kept_kinds()]
    variant = MediaConfig.from_config(get_ini_config()).playfield_variant
    enabled = asset_sources.sources(asset_sources.enabled_ids())
    live = tuple(source.id for source in enabled if source.reachable())
    only = next(iter(scope)) if len(scope) == 1 else ""
    gaps: dict[str, list[str]] = {}
    for row in media_lens.listing(game=only)["media"] if scope else []:
        if row["game_id"] in scope and is_gap(row):
            gaps.setdefault(row["game_id"], []).append(row["kind"])
    missing = dict.fromkeys(kinds, 0)
    available = dict.fromkeys(kinds, 0)
    unmatched = 0
    for game_id, game in scope.items():
        vps_id = effective_vps_id(normalize_meta(game.meta_config or {}))
        unmatched += not vps_id
        for kind in gaps.get(game_id, []):
            if kind not in missing:
                continue
            missing[kind] += 1
            asked = _asked_as(kind, variant)
            if vps_id and asked and live and asset_sources.offers(asked, vps_id, live):
                available[kind] += 1
    return {"games": len(scope), "unmatched": unmatched,
            "sources": [source.name for source in enabled],
            "unreachable": _unanswered(live),
            "kinds": [{"kind": kind, "missing": missing[kind],
                       "available": available[kind]} for kind in kinds]}


def start(game_ids: Iterable[str] | None = None, kinds: Iterable[str] | None = None,
          slots: Iterable[tuple[str, str]] = ()) -> jobs.Job:
    """Get missing art as a job: these games' gaps of `kinds`, or exactly `slots`.

    `game_ids` None is the whole library and `kinds` None every kept kind. A kind the
    library does not keep is never fetched. Raises BlockedError while a fill runs.
    """
    from common import service_errors

    kept = kept_kinds()
    picked: dict[str, set[str]] = {}
    for game_id, kind in slots:
        picked.setdefault(game_id, set()).add(kind)
    if picked:
        targets = [(game_id, game, picked[game_id] & kept)
                   for game_id, game in _scope(picked).items()]
    else:
        chosen = kept if kinds is None else kept & set(kinds)
        targets = [(game_id, game, chosen) for game_id, game in _scope(game_ids).items()]

    def work(job: jobs.Job) -> dict[str, Any]:
        live = _reachable()
        return {**_fill_games(targets, live, job.reporter(), lambda: not shutdown.requested()),
                "unreachable": _unanswered(live)}

    try:
        return jobs.submit(jobs.KIND_MEDIA_FILL, work)
    except jobs.JobBusyError as exc:
        raise service_errors.BlockedError(t("error.media_fill.busy")) from exc


def request(folders: Iterable[str | Path]) -> None:
    """Queue these game folders for a fill, starting the job if none is running.

    A request while one runs joins that run. Does nothing when the switch is off.
    """
    global _running
    if not enabled():
        return
    wanted = [str(folder) for folder in folders if folder]
    if not wanted:
        return
    with _lock:
        _pending.extend(folder for folder in wanted if folder not in _pending)
        if _running:
            return
        _running = True
    _start()


def _start() -> None:
    try:
        jobs.submit(jobs.KIND_MEDIA_FILL, _work)
    except jobs.JobBusyError:
        # The run that just emptied the queue is still finishing, and holds the kind
        # until it does.
        retry = threading.Timer(1.0, _start)
        retry.daemon = True
        retry.start()


def _proceed() -> bool:
    return enabled() and not shutdown.requested()


def _work(job: jobs.Job) -> dict[str, int]:
    """Drain the queue. Kinds and the sources are read once for the whole run."""
    global _running
    reporter = job.reporter()
    wanted = kept_kinds()
    live = _reachable()
    totals = {"games": 0, "filled": 0, "unmatched": 0, "failed": 0}
    while True:
        with _lock:
            batch = list(_pending)
            _pending.clear()
            if not batch or not _proceed():
                _running = False
                logger.info("Art for new games: %s file(s) for %s game(s), %s not "
                            "matched, %s failed", totals["filled"], totals["games"],
                            totals["unmatched"], totals["failed"])
                return totals
        for key, value in _fill(batch, wanted, live, reporter, _proceed).items():
            totals[key] += value


def update_enabled() -> bool:
    return cfg_bool(get_ini_config(), "updates", "update_downloaded_art", True)


def _update_game(game_id: str, game: Any, wanted: set[str], live: tuple[str, ...],
                 media: MediaConfig) -> tuple[int, int]:
    """Replace this game's stale art. Answers (updated, failed).

    Files are hashed only where the recorded hash is gone from the catalog.
    """
    from common.games import asset_origin, media_lens, media_placement
    from common.online import asset_sources
    from common.online.vpsdb_media import file_md5, replace_file

    vps_id = effective_vps_id(normalize_meta(game.meta_config or {}))
    game_dir = Path(str(game.full_path_game))
    recorded = {path: source for path, source in asset_origin.sources(game_dir).items()
                if source.get("hash") and source.get("host") in live}
    if not vps_id or not recorded:
        return 0, 0
    hosts = tuple({str(source["host"]) for source in recorded.values()})
    published = {offer.md5 for kind in _SPECS
                 for offer in asset_sources.offers(kind, vps_id, hosts)}
    gone = {path for path, source in recorded.items() if source["hash"] not in published}
    if not gone:
        return 0, 0
    updated = failed = 0
    for row in media_lens.listing(game=game_id)["media"]:
        path = row.get("path") or ""
        kind = row["kind"]
        asked = _asked_as(kind, media.playfield_variant) if kind in wanted else None
        if path not in gone or not row["present"] or asked is None:
            continue
        gone.discard(path)
        host, held = str(recorded[path]["host"]), str(recorded[path]["hash"])
        mine = asset_sources.offers(asked, vps_id, (host,))
        if not mine or file_md5(game_dir / path) != held:
            continue
        size = _size(asked, media)
        offer = next((one for one in mine if one.size == size), mine[0])
        try:
            replace_file(offer.url, game_dir / path)
        except Exception as exc:
            failed += 1
            logger.warning("Updating art: could not replace %s for %s: %s", kind,
                           game.game_dir_name, exc)
            continue
        media_placement.record_origin(game_dir, game_dir / path, host, offer.md5)
        updated += 1
    return updated, failed


def update_downloaded(reporter: JobReporter | None = None,
                      proceed: Callable[[], bool] = lambda: True) -> dict[str, int]:
    """Replace art we downloaded that the catalog has since replaced.

    Only a file whose recorded hash still matches it, of a kind the library keeps, from
    a source that is on. `updated` and `failed` count files.
    """
    from common.games import game_repository, media_service
    from common.online import asset_sources

    counts = {"games": 0, "updated": 0, "failed": 0}
    asset_sources.refresh()
    live = _reachable()
    wanted = kept_kinds()
    if not live or not wanted:
        return counts
    media = MediaConfig.from_config(get_ini_config())
    games = list(game_repository.catalog().items())
    for index, (game_id, game) in enumerate(games):
        if not proceed():
            break
        name = str(game.game_dir_name or "")
        if reporter:
            reporter.progress(index, len(games), t("said.updating_art_for", game=name))
        try:
            updated, failed = _update_game(game_id, game, wanted, live, media)
        except Exception:
            logger.exception("Updating art: could not read what %s has", name)
            continue
        counts["games"] += 1
        counts["failed"] += failed
        if updated:
            counts["updated"] += updated
            media_service.invalidate_media_cache()
            game_repository.refresh_game(Path(str(game.full_path_game)))
    logger.info("Updating art: %s file(s) replaced across %s game(s), %s failed",
                counts["updated"], counts["games"], counts["failed"])
    return counts


def start_update() -> bool:
    """Run `update_downloaded` as a job. False when a fill holds the job kind."""
    def work(job: jobs.Job) -> dict[str, int]:
        return update_downloaded(job.reporter(),
                                 lambda: update_enabled() and not shutdown.requested())

    try:
        jobs.submit(jobs.KIND_MEDIA_FILL, work)
    except jobs.JobBusyError:
        return False
    return True


def reset_for_tests() -> None:
    global _running
    with _lock:
        _pending.clear()
        _running = False
