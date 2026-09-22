"""Putting artwork in a game's slots, and describing a slot in the detail a curator wants.

A slot is a kind at a tier, and a tier is a filename - so choosing where a file lands is
choosing what it is called. Everything here answers with what now resolves rather than a
bare acknowledgement: a shared file is outranked by any table-specific one, so "written"
and "in use" are different facts and the caller should not have to guess which it got.

`media_service` resolves; this places, removes and renames.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from common import media_probe, service_errors
from common.games import asset_origin, game_lens, media_lookup, media_placement, media_service
from common.games.game import Game
from common.games.game_repository import game_to_row
from common.i18n import t
from common.media_specs import (
    MEDIA_SPECS,
    MediaSpec,
    canonical_kind,
    media_candidates,
    media_family,
)

logger = logging.getLogger("vpinfe.common.games.media_ops")

_KINDS = {spec.kind for spec in MEDIA_SPECS}


def kind_or_refuse(kind: str) -> str:
    """The canonical spelling of a media kind, or a refusal listing the ones there are."""
    kind = canonical_kind(kind)
    if kind not in _KINDS:
        raise service_errors.RefusedError(
            t("error.games.unknown_media_kind"),
            details={"unknown": kind, "known": sorted(_KINDS)})
    return kind


def stem_or_refuse(game: Game, table_id: str) -> str:
    """The stem a table's art is named after, or a refusal if that table is not this
    game's. Distinct from the filename lookup: this wants the name without its suffix."""
    filename = media_lookup.table_filename(game, table_id)
    if not filename:
        raise service_errors.NotFoundError(
            t("error.games.game_no_such_table"),
            details={"game": game.game_dir_name, "table": table_id})
    return Path(filename).stem


def _folder(game: Game) -> Path:
    return Path(game.full_path_game or "")


def _prefix(game_id: str, table_id: str = "") -> str:
    return (f"/api/v1/games/{game_id}/tables/{table_id}/media" if table_id
            else f"/api/v1/games/{game_id}/media")


def game_media(game_id: str) -> dict:
    """Every kind the folder resolves, which is what all its tables share.

    Art named for one build belongs to that build and answers under its table.
    """
    game = game_lens.game_or_refuse(game_id)
    return {"media": media_service.media_map(_folder(game), _prefix(game_id))}


def table_media(game_id: str, table_id: str) -> dict:
    """The same kinds, resolved for one build rather than for the folder.

    Two builds of a game can genuinely differ - a VR room and a desktop table are not the
    same picture - so each answers for itself.
    """
    game = game_lens.game_or_refuse(game_id)
    stem = stem_or_refuse(game, table_id)
    return {"media": media_service.media_map(_folder(game), _prefix(game_id, table_id),
                                             stem)}


def media_file(game_id: str, kind: str, table_id: str = "") -> Path:
    """The file a slot currently resolves to, or a refusal. The caller sends it."""
    game = game_lens.game_or_refuse(game_id)
    kind = kind_or_refuse(kind)
    stem = stem_or_refuse(game, table_id) if table_id else None
    hit = media_service.resolved_media(_folder(game), stem).get(kind)
    path = hit.path if hit is not None else None
    if path is None or not path.is_file():
        raise service_errors.NotFoundError(t("error.games.game_no_media", kind=(kind)))
    return path


def overrides(game_id: str) -> dict:
    """Where the game's art is not the whole story.

    Asked from the game's own lens, which otherwise cannot see a table-specific file at
    all: resolving without a table stem never looks at that tier. A curator scanning a
    folder wants the odd one out, and the odd one out is invisible without this.

    One walk for every kind and every table, because the caller is drawing a map of all of
    them and twenty round trips to answer one question would be worse.
    """
    from common.games import table_lens

    game = game_lens.game_or_refuse(game_id)
    game_dir = _folder(game)
    files, medias = media_service.media_contents(game_dir)
    variant, active_sets = media_service.media_settings()

    # What the game itself resolves, to compare against. A .vpx named after its folder
    # makes its own tier and the game's the same filename, and then the same file - so
    # without this it is reported as overriding itself, which is most single-table folders
    # and the commonest shape there is.
    shared = {spec.kind: next((item.path for item in media_candidates(
        game_dir, files, medias, spec.kind, variant, None, active_sets)), None)
        for spec in MEDIA_SPECS}

    found: dict[str, list[dict]] = {}
    for table in table_lens.table_rows(game, game_to_row(game)):
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


_NO_FACTS = {"size_bytes": None, "modified": None, "width": None, "height": None,
             "format": None, "duration_s": None}


def _file_facts(path: Path) -> dict:
    """Size, date, format, pixel size and running time - what tells two candidates for a
    slot apart.

    Every part is best-effort: a file that cannot be opened still has a name worth showing,
    and a slot that reports nothing at all is worse than one missing a number.
    """
    try:
        stat = path.stat()
    except OSError:
        return dict(_NO_FACTS)
    return {**media_probe.probe(path), "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()}


def detail(game_id: str, kind: str, table_id: str = "") -> dict:
    """One slot: the winner, what it is, and every tier that holds a file for it.

    What a curator needs and a frontend never asks for.
    """
    game = game_lens.game_or_refuse(game_id)
    kind = kind_or_refuse(kind)
    stem = stem_or_refuse(game, table_id) if table_id else None
    game_dir = _folder(game)
    hit = media_service.resolved_media(game_dir, stem).get(kind)
    path = hit.path if hit is not None else None

    files, medias = media_service.media_contents(game_dir)
    variant, active_sets = media_service.media_settings()
    candidates = media_candidates(game_dir, files, medias, kind, variant, stem,
                                  active_sets)
    recorded = asset_origin.sources(game_dir)
    hosts = {key: str(source.get("host", "") or "").strip()
             for key, source in recorded.items()
             if str(source.get("host", "") or "").strip()}
    prefix = _prefix(game_id, table_id)
    return {
        "kind": kind,
        "family": media_family(kind),
        "present": path is not None,
        "file": path.name if path is not None else None,
        "path": asset_origin.path_of(game_dir, path) or None,
        "via": hit.tier if hit is not None else None,
        "origin": (asset_origin.origin_of(hosts, game_dir, path)
                   or None) if path is not None else None,
        "matched_to": asset_origin.match_of(recorded, game_dir, path) or None,
        "tiers": [{"tier": item.tier, "file": item.path.name,
                   "wins": item.path == path}
                  for item in candidates],
        "links": {"self": f"{prefix}/{kind}" if path is not None else None},
        **(_file_facts(path) if path is not None else _NO_FACTS),
    }


def _placement(game_dir: Path, kind: str, spec: MediaSpec, table_id: str, stem: str,
               label: str) -> dict:
    """One destination: what the file would be called there, and what it would take.

    The extension is trimmed back off the name because the file decides it, and it is only
    supplied here to satisfy the family check.
    """
    suffix = spec.family[0]
    going = media_placement.displaced(game_dir, kind, stem, suffix)
    return {"table": table_id, "label": label,
            "base": media_placement.target_name(kind, stem, suffix)[:-len(suffix)],
            # `as_posix`, never `str`: a relative path on the wire is forward-slashed
            # whatever host built it. `str(WindowsPath)` gave clients "medias\\bg.png" on
            # Windows and "medias/bg.png" everywhere else, for the same library.
            "displaces": sorted(path.relative_to(game_dir).as_posix()
                                for path in going)}


def placements(game_id: str, kind: str) -> dict:
    """Every name this kind can take in this folder, with the cost of each.

    Answered without the file, because it can be: what a write displaces is the whole
    family at that tier, which does not depend on the extension arriving.
    """
    from common.games import table_lens

    spec = next((item for item in MEDIA_SPECS if item.kind == kind), None)
    if spec is None:
        raise service_errors.RefusedError(
            t("error.games.unknown_media_kind"),
            details={"unknown": kind, "known": sorted(_KINDS)})
    game = game_lens.game_or_refuse(game_id)
    game_dir = _folder(game)

    found = [_placement(game_dir, kind, spec, "", game_dir.name,
                        "Shared by every table")]
    for table in table_lens.table_rows(game, game_to_row(game)):
        stem = Path(table["filename"]).stem
        option = _placement(game_dir, kind, spec, table["id"], stem, table["filename"])
        # A .vpx named after its folder makes the two tiers the same filename, and they are
        # then the same file - the resolver finds it looking for either. Most single-table
        # folders are like that, so this is the common case rather than a corner, and
        # offering both would be two choices that do one thing.
        if table.get("id") and option["base"] not in {item["base"] for item in found}:
            found.append(option)
    return {"placements": found, "extensions": list(spec.family)}


def displaced(game_id: str, kind: str, filename: str, table_id: str = "") -> dict:
    """What placing `filename` at this tier would replace.

    Asked before an upload, so a confirmation can name the files rather than warn in the
    abstract - and so the bytes are not sent for a drop the user cancels.
    """
    game = game_lens.game_or_refuse(game_id)
    game_dir = _folder(game)
    stem = stem_or_refuse(game, table_id) if table_id else game_dir.name
    try:
        going = media_placement.displaced(game_dir, kind, stem, Path(filename).suffix)
    except media_placement.UnplaceableError as exc:
        raise service_errors.RefusedError(str(exc)) from exc
    # Forward-slashed on the wire whatever host built it - see `_placement`.
    return {"displaced": sorted(path.relative_to(game_dir).as_posix()
                                for path in going)}


def _wrote(game_dir: Path, kind: str, written: Path, game_id: str,
           table_id: str, table_stem: str | None) -> dict:
    entries = media_service.media_map(game_dir, _prefix(game_id, table_id), table_stem)
    return {"written": written.name, "media": {kind: entries[kind]}}


def place_file(game_id: str, kind: str, table_id: str, source: Path,
               origin: str = "user", md5: str = "") -> dict:
    """Copy a file into the slot and answer with what now resolves.

    Shared by every caller that fills a slot from a file that already exists somewhere -
    one on this machine, one an online catalog published. Where the source is allowed to be
    is each caller's own question; this one is only about the write.
    """
    game = game_lens.game_or_refuse(game_id)
    kind = kind_or_refuse(kind)
    if not Path(source).is_file():
        raise service_errors.RefusedError(t("error.games.not_file"),
                                          details={"path": str(source)})
    game_dir = _folder(game)
    table_stem = stem_or_refuse(game, table_id) if table_id else game_dir.name
    try:
        written = media_placement.place(game_dir, kind, table_stem, source)
    except media_placement.UnplaceableError as exc:
        raise service_errors.RefusedError(str(exc)) from exc
    # Recorded with who placed it, which is what lets a later media refresh tell its own
    # art from something hand-placed and leave the latter alone.
    media_placement.record_origin(game_dir, written, origin, md5)
    return _wrote(game_dir, kind, written, game_id, table_id,
                  table_stem if table_id else None)


def place_upload(game_id: str, kind: str, table_id: str, staged: Path,
                 stem: str) -> dict:
    """Store bytes that have already arrived at `stem`'s tier, then say what resolves.

    Split from `place_file` because the caller owns the staging: it holds the upload, it
    decides where the temporary file lives, and it removes it whatever happens here.
    """
    game = game_lens.game_or_refuse(game_id)
    kind = kind_or_refuse(kind)
    game_dir = _folder(game)
    try:
        written = media_placement.place(game_dir, kind, stem, str(staged))
    except media_placement.UnplaceableError as exc:
        raise service_errors.RefusedError(str(exc)) from exc
    media_placement.record_origin(game_dir, written)
    return _wrote(game_dir, kind, written, game_id, table_id,
                  stem if table_id else None)


def fetch_file(game_id: str, kind: str, table_id: str, source: str, vps_id: str,
               size: str) -> dict:
    """Download what an online catalog publishes and put it in the slot.

    A source and an id, never a URL: the only links this follows are ones a source produced
    for that id and kind, which is what stops it being a way to make this install fetch
    whatever a caller likes. The id does not have to be this game's - a mod, or a game the
    matcher got wrong, is exactly when the art has to come from another entry.
    """
    import tempfile

    from common.http_client import download_file
    from common.online import asset_sources

    offer = asset_sources.url_for(source, kind, vps_id, size,
                                  asset_sources.enabled_ids())
    if offer is None:
        raise service_errors.NotFoundError(
            t("error.games.source_no_such_art"),
            details={"source": source, "vps_id": vps_id, "kind": kind, "size": size})
    with tempfile.TemporaryDirectory() as staging:
        staged = Path(staging) / Path(offer.url).name
        try:
            download_file(offer.url, staged)
        except Exception as exc:
            raise service_errors.UnavailableError(
                t("error.games.could_not_reach", source=(source), exc=(exc))) from exc
        # Stamped with the source and the source's own hash. Without the hash this art is
        # indistinguishable from hand-placed later, so a refresh would leave it untouched
        # forever - the bulk downloader has always recorded one.
        return place_file(game_id, kind, table_id, staged, offer.source, offer.md5)


def retier(game_id: str, kind: str, from_table: str, to_table: str) -> dict:
    """Change who a file serves without sending it again.

    The tier is the filename, so this is a rename. Either table may be empty, which means
    the folder's shared name.
    """
    game = game_lens.game_or_refuse(game_id)
    game_dir = _folder(game)
    from_stem = stem_or_refuse(game, from_table) if from_table else game_dir.name
    to_stem = stem_or_refuse(game, to_table) if to_table else game_dir.name
    try:
        written = media_placement.retier(game_dir, kind, from_stem, to_stem)
    except media_placement.UnplaceableError as exc:
        raise service_errors.RefusedError(str(exc)) from exc
    return _wrote(game_dir, kind, written, game_id, to_table,
                  to_stem if to_table else None)


def remove(game_id: str, kind: str, table_id: str = "") -> dict:
    """Take a file out of one tier. A build's own art and the default both survive the
    folder's file going."""
    game = game_lens.game_or_refuse(game_id)
    game_dir = _folder(game)
    stem = stem_or_refuse(game, table_id) if table_id else game_dir.name
    try:
        return {"removed": media_placement.remove(game_dir, kind, stem)}
    except media_placement.UnplaceableError as exc:
        raise service_errors.RefusedError(str(exc)) from exc


__all__ = ["detail", "displaced", "fetch_file", "game_media", "kind_or_refuse",
           "media_file", "overrides", "place_file", "place_upload", "placements",
           "remove", "retier", "stem_or_refuse", "table_media"]
