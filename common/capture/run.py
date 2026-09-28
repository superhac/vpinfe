"""A recording run: what it would do, and doing it as a job."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from common import jobs, service_errors
from common.failures import why
from common.games import asset_origin, game_lens, game_repository, media_lens, tables
from common.host import launch, launch_state, tools
from common.i18n import t
from common.paths import CONFIG_DIR

from . import adapters, preflight, session, settings

FILL = "fill"
REPLACE_DOWNLOADED = "replace_downloaded"
REPLACE_ALL = "replace_all"
CHOOSE = "choose"
EXISTING = (FILL, REPLACE_DOWNLOADED, REPLACE_ALL, CHOOSE)

# What becomes of a slot.
FILLED = "fill"
REPLACED = "replace"
LEFT = "leave"

# Seconds a table takes beyond Wait and Length.
START_SECONDS = 6
CLOSE_SECONDS = 3
ENCODE_SECONDS = 5

WORK = CONFIG_DIR / "capture" / "recording"


@dataclass(frozen=True)
class Request:
    games: Sequence[str] = ()
    tables: Sequence[tuple[str, str]] = ()
    kinds: Sequence[str] = ()
    existing: str = FILL
    settings: Mapping[str, Any] = field(default_factory=dict)
    sound: bool | None = None
    confirmed: int | None = None


def _named(request: Request) -> tuple[str, str]:
    named = [(game_id, "") for game_id in request.games] + list(request.tables)
    if not named:
        raise service_errors.RefusedError(t("error.capture.nothing_named"))
    if len(named) > 1:
        raise service_errors.RefusedError(t("error.capture.one_at_a_time"))
    return named[0]


def _launch_key(game: Any, table_id: str) -> str | None:
    """What the launch is asked to play: the table's own key, or None for the game's
    default."""
    if not table_id:
        return None
    entry = tables.table_entries(getattr(game, "meta_config", None) or {}).get(table_id)
    if entry is None:
        raise service_errors.NotFoundError(t("error.games.game_no_such_table"),
                                           details={"table": table_id})
    return tables.entry_native_key(entry)


def _kinds(request: Request, report: Mapping[str, Any], chosen: settings.Settings) -> list[str]:
    if request.kinds:
        unknown = sorted(set(request.kinds) - session.RECORDABLE)
        if unknown:
            raise service_errors.RefusedError(t("error.capture.not_recordable",
                                                kinds=", ".join(unknown)))
        return list(dict.fromkeys(request.kinds))
    found = []
    for screen in report["screens"]:
        picture, video = session.KINDS[screen["window"]]
        found += [kind for kind, ability in ((picture, "picture"), (video, "video"))
                  if screen[ability]["available"]]
    sound = chosen.sound if request.sound is None else request.sound
    return found + ([session.AUDIO] if sound and report["sound"]["available"] else [])


def _blocked(kind: str, report: Mapping[str, Any]) -> dict[str, Any] | None:
    """Why this device cannot record `kind`, or None where it can."""
    if kind == session.AUDIO:
        return report["sound"]["reason"]
    for screen in report["screens"]:
        picture, video = session.KINDS[screen["window"]]
        if kind in (picture, video):
            return screen["picture" if kind == picture else "video"]["reason"]
    return None


def before(game_id: str, table_id: str, kind: str) -> str | None:
    """Who placed the file serving this slot, or None where nothing does."""
    rows = [row for row in media_lens.listing(game=game_id, kind=kind)["media"]
            if row.get("present") and row.get("via") not in (media_lens.ORPHAN,
                                                            media_lens.UNUSED)]
    own = next((row for row in rows if table_id and row["table"] == table_id), None)
    shared = next((row for row in rows if not row["table"]), None)
    row = own or shared
    return None if row is None else str(row.get("origin") or asset_origin.UNKNOWN)


def _catalogs() -> set[str]:
    from common.online import asset_sources

    return {source.id for source in asset_sources.BUILT_IN}


def decide(existing: str, held: str | None) -> str:
    if held is None:
        return FILLED
    if existing == REPLACE_ALL or (existing == REPLACE_DOWNLOADED and held in _catalogs()):
        return REPLACED
    return LEFT


def _estimate(kinds: Sequence[str], at_once: bool, chosen: settings.Settings) -> int:
    screens = {window for window, pair in session.KINDS.items()
               if pair[1] in kinds or pair[0] in kinds}
    videos = sum(1 for pair in session.KINDS.values() if pair[1] in kinds)
    recording = chosen.length * (1 if at_once else max(1, videos))
    return (START_SECONDS + chosen.wait + recording + CLOSE_SECONDS
            + ENCODE_SECONDS * len(screens))


def _plan(request: Request, report: Mapping[str, Any],
          chosen: settings.Settings) -> dict[str, Any]:
    if request.existing not in EXISTING:
        raise service_errors.RefusedError(t("error.capture.existing_unknown",
                                            existing=request.existing))
    game_id, table_id = _named(request)
    game = game_lens.game_or_refuse(game_id)
    _launch_key(game, table_id)
    rows: list[dict[str, Any]] = []
    doing: list[str] = []
    for kind in _kinds(request, report, chosen):
        blocked = _blocked(kind, report)
        held = None if blocked else before(game_id, table_id, kind)
        what = LEFT if blocked else decide(request.existing, held)
        rows.append({"kind": kind, "does": what, "source": held, "reason": blocked})
        if what != LEFT:
            doing.append(kind)
    replacing: dict[str, int] = {}
    for row in rows:
        if row["does"] == REPLACED:
            source = str(row["source"])
            replacing[source] = replacing.get(source, 0) + 1
    return {"game_id": game_id, "table_id": table_id,
            "name": str(game_repository.game_to_row(game).get("name")
                        or getattr(game, "game_dir_name", "") or ""),
            "kinds": rows, "recording": doing,
            "replacing": sum(replacing.values()), "replacing_by_source": replacing,
            "launches": 1 if doing else 0, "at_once": bool(report["at_once"]),
            "estimate_seconds": _estimate(doing, bool(report["at_once"]), chosen)
            if doing else 0}


def plan(request: Request, report: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What `start` would do with the same request, doing nothing."""
    report = preflight.report() if report is None else report
    return _plan(request, report, settings.read(None, request.settings))


def _refuse_now(report: Mapping[str, Any], request: Request) -> None:
    if not report["available"]:
        raise service_errors.UnavailableError(preflight.words(report["reason"]))
    if request.existing == CHOOSE:
        raise service_errors.RefusedError(t("error.capture.choose_not_yet"))
    if launch_state.current().launching:
        raise service_errors.BlockedError(t("error.launch.already_launching"))


def start(request: Request, kit: session.Kit | None = None) -> jobs.Job:
    """Record one game or table as a job."""
    report = preflight.report()
    _refuse_now(report, request)
    chosen = settings.read(None, request.settings)
    planned = _plan(request, report, chosen)
    if planned["replacing"] and request.confirmed != planned["replacing"]:
        raise service_errors.RefusedError(
            t("error.capture.confirm_count", count=planned["replacing"]),
            details={"replacing": planned["replacing"],
                     "by_source": planned["replacing_by_source"]})
    game = game_lens.game_or_refuse(planned["game_id"])
    try:
        game = launch.this_devices_copy(game)
    except launch.LaunchUnavailableError as exc:
        raise service_errors.UnavailableError(why(exc)) from exc
    adapter = adapters.resolve()
    if isinstance(adapter, adapters.Unsupported):
        raise service_errors.UnavailableError(preflight.words(report["reason"]))
    found = {tool.id: tools.resolve(tool) for tool in adapter.requirements()}
    from common.host import display_service
    from common.paths import get_ini_config

    config = get_ini_config()
    outputs = adapter.outputs()
    monitors = display_service.get_display_monitors()
    screens = {window: screen.output for window in adapters.WINDOWS
               if (screen := adapters.screen_of(window, outputs, config, monitors)).output}
    target = session.Target(planned["game_id"], game, planned["table_id"],
                            _launch_key(game, planned["table_id"]),
                            tuple(planned["recording"]))
    codec = settings.video_codec(chosen.video_codec)

    def work(job: jobs.Job) -> dict[str, Any]:
        job.progress(0, 1, t("capture.progress.recording", game=planned["name"]))
        result = session.Session(
            target, chosen, adapter=adapter, screens=screens, found=found,
            at_once=planned["at_once"], codec=codec, work=WORK, config=config,
            kit=kit).run()
        return {"tables": [{"game_id": target.game_id, "table_id": target.table_id,
                            **result.as_dict()}],
                "at_once": result.at_once}

    return jobs.submit(jobs.KIND_MEDIA_CAPTURE, work)
