"""The configured ways this install runs a table, over the wire.

Its own resource rather than part of `/config`, because a launcher is an object somebody
creates, removes and duplicates - the config endpoints answer with a fixed set of settings
and have nowhere to put a list of things.

It keeps the config scopes all the same. These values were settings until they moved, so
reading and writing them is the same power it always was, and a token that can already
change what program plays a table should not need a new grant to keep doing it.

`common/games/launcher_ops.py` is what answers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from common.games import launcher_ops

from . import scopes
from .auth import requires

router = APIRouter(prefix="/launchers", tags=["launchers"])


@router.get("", summary="Every launcher this install has",
            dependencies=[requires(scopes.CONFIG_READ)])
def list_launchers() -> dict[str, Any]:
    """The launchers in order, the tables that deviate, and which one is the default."""
    return launcher_ops.listing()


@router.put("/{launcher_id}", summary="Add or replace a launcher",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_launcher(launcher_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Write one whole, under the id the caller names - which is also how a launcher
    arrives from another machine, mappings and all."""
    return launcher_ops.put(launcher_id, body)


@router.get("/{launcher_id}/config", summary="What the app it runs can be set to",
            dependencies=[requires(scopes.CONFIG_READ)])
def launcher_config(launcher_id: str, table: str = "",
                    scope: str = "launcher") -> dict[str, Any]:
    """The declared groups, and every value as it stands at one scope."""
    return launcher_ops.app_config(launcher_id, table, scope)


@router.get("/{launcher_id}/config/reaching",
            summary="What a folder currently gives one of its tables",
            dependencies=[requires(scopes.CONFIG_READ)])
def folder_settings_reaching(launcher_id: str, table: str = "") -> dict[str, Any]:
    """Asked before a table is given settings of its own: the two layers do not stack, so
    what the folder is giving it has to be shown before that happens."""
    return launcher_ops.reaching_from_folder(launcher_id, table)


@router.put("/{launcher_id}/config", summary="Set values on the app it runs",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def write_launcher_config(launcher_id: str,
                          body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Values at one scope. The app writes them into its own file in place, and names
    under `cleared` the ones it cleared instead, for holding the launcher's own value."""
    return launcher_ops.write_config(launcher_id, body)


@router.get("/{launcher_id}/config/backups", summary="Copies of its settings file",
            dependencies=[requires(scopes.CONFIG_READ)])
def list_config_backups(launcher_id: str) -> dict[str, Any]:
    return launcher_ops.backups(launcher_id)


@router.post("/{launcher_id}/config/backups", summary="Take a copy of it now",
             dependencies=[requires(scopes.CONFIG_WRITE)])
def take_config_backup(launcher_id: str,
                       body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return launcher_ops.take_backup(launcher_id, str(body.get("label") or ""))


@router.post("/{launcher_id}/config/backups/{name}/restore",
             summary="Put a copy back",
             dependencies=[requires(scopes.CONFIG_WRITE)])
def restore_config_backup(launcher_id: str, name: str) -> dict[str, Any]:
    """A copy of what is there now is taken first. Restoring the wrong one is a mistake
    somebody makes once, and without that copy it is the last one they get to make."""
    return launcher_ops.restore_backup(launcher_id, name)


@router.delete("/{launcher_id}", summary="Forget a launcher",
               dependencies=[requires(scopes.CONFIG_WRITE)])
def delete_launcher(launcher_id: str) -> dict[str, Any]:
    """Its mappings go with it. A table pointing at a launcher that was deleted is not a
    state anybody chose, so it goes back to the default."""
    return launcher_ops.forget(launcher_id)


@router.put("/mappings/{table_id}", summary="Point a table at a launcher",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_mapping(table_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """An empty `launcher_id` clears it, which is how a table goes back to the default."""
    return launcher_ops.assign(table_id, str(body.get("launcher_id") or ""))
