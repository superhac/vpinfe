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
