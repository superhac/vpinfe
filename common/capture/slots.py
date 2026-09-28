"""The file a recording would take the place of, and whether placing it deletes that file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common.games import asset_origin, game_lens, media_lens


def _serving(rows: list[dict[str, Any]], table_id: str) -> dict[str, Any] | None:
    rows = [row for row in rows
            if row.get("present") and row.get("via") not in (media_lens.ORPHAN,
                                                            media_lens.UNUSED)]
    own = next((row for row in rows if table_id and row["table"] == table_id), None)
    shared = next((row for row in rows if not row["table"]), None)
    return own or shared


def serving(game_id: str, table_id: str, kind: str) -> dict[str, Any] | None:
    """The media row whose file serves this slot: a table's own file, else the file the
    game's tables share; None where nothing does."""
    return _serving(media_lens.listing(game=game_id, kind=kind)["media"], table_id)


def serving_each(game_id: str, table_id: str, kinds: list[str]
                 ) -> dict[str, dict[str, Any] | None]:
    """`serving` for each of `kinds`, from one read of the game's media."""
    rows = media_lens.listing(game=game_id)["media"]
    return {kind: _serving([row for row in rows if row.get("kind") == kind], table_id)
            for kind in kinds}


def source(row: dict[str, Any] | None) -> str | None:
    """Who placed a row's file, or None where there is no file."""
    return None if row is None else str(row.get("origin") or asset_origin.UNKNOWN)


def goes(row: dict[str, Any] | None, table_id: str) -> bool:
    """Whether a recording placed for this slot deletes the file serving it."""
    if row is None or not row.get("path"):
        return False
    return not table_id or row["table"] == table_id or int(row.get("serves") or 0) <= 1


def remove(game_id: str, row: dict[str, Any] | None, table_id: str,
           written: str) -> list[str]:
    """Delete the file `row` served the slot with, now that `written` serves it."""
    if not goes(row, table_id):
        return []
    assert row is not None
    folder = Path(str(game_lens.game_or_refuse(game_id).full_path_game))
    path = folder / str(row["path"])
    if path.name == written or not path.is_file():
        return []
    path.unlink()
    return [str(row["path"])]


def refreshed(game_id: str) -> None:
    """Everything that read this game's media reads it again."""
    from common.games import game_repository, media_service

    media_service.invalidate_media_cache()
    game = game_repository.game_by_id(game_id)
    folder = getattr(game, "full_path_game", None)
    if folder:
        game_repository.refresh_game(Path(str(folder)))
