"""The configured ways this install runs a table, over the wire.

Its own resource rather than part of `/config`, because a launcher is an object somebody
creates, removes and duplicates - the config endpoints answer with a fixed set of settings
and have nowhere to put a list of things.

It keeps the config scopes all the same. These values were settings until they moved, so
reading and writing them is the same power it always was, and a token that can already
change what program plays a table should not need a new grant to keep doing it.

A launcher is per install: what it names is a program on this machine. Copying one to a
cabinet is a `PUT` on that machine with the id kept, which is why the id is the caller's
to send rather than something minted here on every write.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body

from common import apps, path_checks
from common.games import launchers

from . import scopes
from .auth import requires
from .errors import InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.launchers")

router = APIRouter(prefix="/launchers", tags=["launchers"])


def _described(launcher: launchers.Launcher) -> dict[str, Any]:
    """One launcher, with the shape of its own settings alongside the values.

    The fields travel with it so a client can draw an editor without knowing what a
    Visual Pinball launcher happens to hold - which is the whole point of the app
    declaring them.
    """
    return {
        "launcher_id": launcher.launcher_id,
        "app": launcher.app,
        "app_name": apps.app_name(launcher.app),
        "display_name": launcher.display_name,
        "enabled": launcher.enabled,
        "owns_ini": launcher.owns_ini,
        "settings": {field.key: launcher.value(field.key)
                     for field in launcher.fields()},
        "fields": [{"key": f.key, "label": f.label, "type": f.type,
                    "default": f.default, "description": f.description, "path": f.path}
                   for f in launcher.fields()],
        # Asked on every read, never stored: a launcher pointing at a program that has
        # been uninstalled otherwise looks exactly like one that works.
        "checks": _checks(launcher),
    }


def _checks(launcher: launchers.Launcher) -> dict[str, dict[str, str]]:
    """`{field: {state, reason}}`, for the fields that name a path and only those. A
    state on every field would be a mark on every row, which says nothing."""
    found = {}
    for field in launcher.fields():
        if not field.path:
            continue
        state, reason = path_checks.check(field.path,
                                          str(launcher.value(field.key) or ""))
        found[field.key] = {"state": state, "reason": reason}
    return found


@router.get("", summary="Every launcher this install has",
            dependencies=[requires(scopes.CONFIG_READ)])
def list_launchers() -> dict[str, Any]:
    """The launchers in order, the tables that deviate, and which one is the default.

    `default` is named rather than left to be worked out: the rule is the first enabled
    launcher for an app, and a client re-deriving that is a second place for it to be
    wrong.
    """
    store = launchers.get_launcher_store()
    held = store.launchers()
    return {
        "launchers": [_described(one) for one in held],
        "mappings": store.mappings(),
        "defaults": {app.id: getattr(launchers.default_for(app.id, held),
                                     "launcher_id", None)
                     for app in apps.all_apps()},
        "apps": [{"id": app.id, "name": app.name,
                  "suffixes": list(app.claim.suffixes)}
                 for app in apps.all_apps()],
    }


@router.put("/{launcher_id}", summary="Add or replace a launcher",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_launcher(launcher_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Write one whole, under the id the caller names.

    Whole rather than a patch, and by the caller's id, because this is also how a
    launcher arrives from another machine: that copy is the launcher, and renumbering it
    on the way in would break every mapping that travelled with it.
    """
    wanted = str(launcher_id or "").strip()
    if not wanted:
        raise InvalidRequestError("A launcher needs an id.")
    app_id = str(body.get("app") or "").strip()
    if apps.get(app_id) is None:
        raise InvalidRequestError(
            f"No app called {app_id!r}. This build knows "
            f"{', '.join(app.id for app in apps.all_apps())}.")

    store = launchers.get_launcher_store()
    written = store.put(launchers.Launcher(
        launcher_id=wanted,
        app=app_id,
        display_name=str(body.get("display_name") or "").strip() or apps.app_name(app_id),
        enabled=bool(body.get("enabled", True)),
        owns_ini=bool(body.get("owns_ini", False)),
        settings=dict(body.get("settings") or {}),
    ))
    return _described(written)


def _config_of(launcher: launchers.Launcher):
    """The app's own settings surface for this launcher, or None where its app has
    none. `generic` has none: it knows a program and arguments and nothing about what
    that program stores."""
    app = apps.get(launcher.app)
    return getattr(app, "config", None) if app is not None else None


def _launcher_settings(launcher: launchers.Launcher) -> dict[str, Any]:
    return {field.key: launcher.value(field.key) for field in launcher.fields()}


def _game_file(table_id: str) -> str:
    """The file behind a table id, resolved here rather than sent.

    A caller names the table, not the path. Where a game file sits is a fact about this
    machine, and the Console reads this API over the network - it has no business
    knowing, and on another machine it would be wrong.
    """
    wanted = str(table_id or "").strip()
    if not wanted:
        return ""
    from common.games.game_repository import all_games
    from common.games.table_identity import find_table_by_id

    found = find_table_by_id(all_games(), wanted)
    if found is None:
        raise NotFoundError(f"No table called {wanted!r}.")
    game, filename = found
    return str(Path(str(getattr(game, "fullPathGame", "") or "")) / filename)


@router.get("/{launcher_id}/config", summary="What the app it runs can be set to",
            dependencies=[requires(scopes.CONFIG_READ)])
def launcher_config(launcher_id: str, table: str = "",
                    scope: str = "launcher") -> dict[str, Any]:
    """The declared groups, and every value as it stands at one scope.

    The groups come from the app, which reads them out of the program's own files, so a
    setting a later build of that program adds appears without anything here changing.
    """
    found = launchers.get_launcher_store().get(launcher_id)
    if found is None:
        raise NotFoundError(f"No launcher called {launcher_id!r}.")
    config = _config_of(found)
    if config is None:
        return {"groups": [], "values": {}, "scopes": []}

    settings = _launcher_settings(found)
    if scope not in config.scopes():
        raise InvalidRequestError(
            f"No scope called {scope!r}. This app has "
            f"{', '.join(config.scopes())}.")
    values = config.read(scope, _game_file(table), settings)
    return {
        "scopes": list(config.scopes()),
        "groups": [{"key": g.key, "label": g.label,
                    "settings": [_described_field(f) for f in g.settings]}
                   for g in config.groups(settings)],
        "values": {key: {"value": one.value, "scope": one.scope,
                         "set_here": one.set_here, "in_effect": one.in_effect}
                   for key, one in values.items()},
    }


def _described_field(field: apps.Field) -> dict[str, Any]:
    return {"key": field.key, "label": field.label, "type": field.type,
            "default": field.default, "description": field.description,
            "choices": [list(pair) for pair in field.choices],
            "minimum": field.minimum, "maximum": field.maximum}


@router.get("/{launcher_id}/config/reaching",
            summary="What a folder currently gives one of its tables",
            dependencies=[requires(scopes.CONFIG_READ)])
def folder_settings_reaching(launcher_id: str, table: str = "") -> dict[str, Any]:
    """Asked before a table is given settings of its own.

    The two layers do not stack, so a table with its own file stops receiving the
    folder's other keys. What they are has to be shown before that happens, not
    discovered afterwards.
    """
    found = launchers.get_launcher_store().get(launcher_id)
    if found is None:
        raise NotFoundError(f"No launcher called {launcher_id!r}.")
    config = _config_of(found)
    reaching = getattr(config, "inherited_from_folder", None)
    if config is None or reaching is None:
        return {"reaching": {}}
    return {"reaching": reaching(_game_file(table), _launcher_settings(found))}


@router.put("/{launcher_id}/config", summary="Set values on the app it runs",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def write_launcher_config(launcher_id: str,
                          body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Values at one scope. The app writes them into its own file in place."""
    found = launchers.get_launcher_store().get(launcher_id)
    if found is None:
        raise NotFoundError(f"No launcher called {launcher_id!r}.")
    config = _config_of(found)
    if config is None:
        raise InvalidRequestError(
            f"{apps.app_name(found.app)} has no settings of its own to write.")

    scope = str(body.get("scope") or "launcher")
    if scope not in config.scopes():
        raise InvalidRequestError(f"No scope called {scope!r}.")
    values = body.get("values") or {}
    if not isinstance(values, dict) or not values:
        raise InvalidRequestError("Name at least one setting to write.")
    config.write(scope, _game_file(str(body.get("table") or "")),
                 {str(k): str(v) for k, v in values.items()},
                 _launcher_settings(found))
    return {"written": sorted(str(k) for k in values)}


@router.delete("/{launcher_id}", summary="Forget a launcher",
               dependencies=[requires(scopes.CONFIG_WRITE)])
def delete_launcher(launcher_id: str) -> dict[str, Any]:
    """Its mappings go with it. A table pointing at a launcher that was deleted is not a
    state anybody chose, so it goes back to the default."""
    store = launchers.get_launcher_store()
    if not store.remove(launcher_id):
        raise NotFoundError(f"No launcher {launcher_id}")
    return {"launcher_id": launcher_id, "removed": True}


@router.put("/mappings/{table_id}", summary="Point a table at a launcher",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_mapping(table_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """An empty `launcher_id` clears it, which is how a table goes back to the default.

    Cleared rather than stored blank: an absent mapping already means the default, and
    two spellings of one state is what makes a reader ask which is which.
    """
    wanted = str(body.get("launcher_id") or "").strip()
    store = launchers.get_launcher_store()
    if wanted and store.get(wanted) is None:
        raise NotFoundError(f"No launcher {wanted}")
    store.assign(table_id, wanted)
    return {"table_id": table_id, "launcher_id": store.mapped(table_id)}
