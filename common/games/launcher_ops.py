"""The configured ways this install runs a table.

A launcher is an object somebody creates, removes and duplicates, and what it names is a
program on this machine. Copying one to a cabinet keeps its id, which is why the id is the
caller's rather than something minted on every write.

The app it runs declares its own settings, so a caller can draw an editor without knowing
what a Visual Pinball launcher happens to hold.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from common import apps, path_checks, service_errors
from common.games import config_backups, game_repository, launchers
from common.games.config_backups import Backup
from common.games.table_identity import find_table_by_id
from common.i18n import t

logger = logging.getLogger("vpinfe.common.games.launcher_ops")


def launcher_or_refuse(launcher_id: str) -> launchers.Launcher:
    found = launchers.get_launcher_store().get(launcher_id)
    if found is None:
        raise service_errors.NotFoundError(
            t("error.launchers.no_launcher_called", launcher_id=(launcher_id)))
    return found


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
        # `lines`, `choices` and the bounds travel with the field because the control a
        # surface draws is decided from them - a field declared over three lines that
        # arrives without them renders as a one-line box.
        "fields": [{"key": f.key, "label": f.label, "type": f.type,
                    "default": f.default, "description": f.description, "path": f.path,
                    "lines": f.lines, "choices": dict(f.choices),
                    "min": f.minimum, "max": f.maximum}
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


def listing() -> dict[str, Any]:
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


def put(launcher_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Write one whole, under the id the caller names.

    Whole rather than a patch, and by the caller's id, because this is also how a
    launcher arrives from another machine: that copy is the launcher, and renumbering it
    on the way in would break every mapping that travelled with it.
    """
    wanted = str(launcher_id or "").strip()
    if not wanted:
        raise service_errors.RefusedError(t("error.launchers.launcher_needs_id"))
    app_id = str(body.get("app") or "").strip()
    if apps.get(app_id) is None:
        raise service_errors.RefusedError(
            t("error.launchers.no_app_called_build", app_id=(app_id),
                    join=(', '.join(app.id for app in apps.all_apps()))))

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


def _app_settings_surface(launcher: launchers.Launcher) -> Any:
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
    found = find_table_by_id(game_repository.all_games(), wanted)
    if found is None:
        raise service_errors.NotFoundError(t("error.launchers.no_table_called", wanted=(wanted)))
    game, filename = found
    return str(Path(str(game.full_path_game or "")) / filename)


def app_config(launcher_id: str, table: str = "",
               scope: str = "launcher") -> dict[str, Any]:
    """The declared groups, and every value as it stands at one scope.

    The groups come from the app, which reads them out of the program's own files, so a
    setting a later build of that program adds appears without anything here changing.
    """
    found = launcher_or_refuse(launcher_id)
    config = _app_settings_surface(found)
    if config is None:
        return {"groups": [], "values": {}, "scopes": []}

    settings = _launcher_settings(found)
    if scope not in config.scopes():
        raise service_errors.RefusedError(
            t("error.launchers.no_scope_called_app", scope=(scope),
                    join=(', '.join(config.scopes()))))
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


def reaching_from_folder(launcher_id: str, table: str = "") -> dict[str, Any]:
    """Asked before a table is given settings of its own.

    The two layers do not stack, so a table with its own file stops receiving the
    folder's other keys. What they are has to be shown before that happens, not
    discovered afterwards.
    """
    found = launcher_or_refuse(launcher_id)
    config = _app_settings_surface(found)
    reaching = getattr(config, "inherited_from_folder", None)
    if config is None or reaching is None:
        return {"reaching": {}}
    return {"reaching": reaching(_game_file(table), _launcher_settings(found))}


def write_config(launcher_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Values at one scope. The app writes them into its own file in place, and names
    under `cleared` the ones it cleared instead, for holding the launcher's own value."""
    found = launcher_or_refuse(launcher_id)
    config = _app_settings_surface(found)
    if config is None:
        raise service_errors.RefusedError(
            t("error.launchers.no_settings_own_write", app_name=(apps.app_name(found.app))))

    scope = str(body.get("scope") or "launcher")
    if scope not in config.scopes():
        raise service_errors.RefusedError(t("error.launchers.no_scope_called", scope=(scope)))
    values = body.get("values") or {}
    if not isinstance(values, dict) or not values:
        raise service_errors.RefusedError(t("error.launchers.name_least_one_setting"))
    settings = _launcher_settings(found)
    table = _game_file(str(body.get("table") or ""))
    writing = {str(k): str(v) for k, v in values.items()}

    # The two layers do not stack, so the write that gives a table its own file takes
    # the folder's other keys off it. Carrying them across is what keeps the table doing
    # what it did a moment ago. Asked for rather than always done, because a caller has
    # to have told whoever is doing this what it is about to happen - and after that
    # first write there is nothing left reaching, so it stops mattering.
    if body.get("seed"):
        reaching = getattr(config, "inherited_from_folder", None)
        if reaching is not None:
            # Under, not over: the value being set is the reason for the write.
            writing = {**reaching(table, settings), **writing}

    cleared = config.write(scope, table, writing, settings)
    return {"written": sorted(set(writing) - cleared), "cleared": sorted(cleared)}


def _config_files(launcher: launchers.Launcher) -> dict[str, str]:
    config = _app_settings_surface(launcher)
    naming = getattr(config, "files", None)
    return dict(naming(_launcher_settings(launcher))) if naming else {}


def _as_backup(one: Backup) -> dict[str, Any]:
    return {"name": one.name, "taken_at": one.taken_at, "reason": one.reason,
            "label": one.label, "size": one.size}


def backups(launcher_id: str) -> dict[str, Any]:
    found = launcher_or_refuse(launcher_id)
    return {
        "backups": [_as_backup(one) for one in
                    config_backups.held(launcher_id, found.display_name)],
        "files": _config_files(found),
        # Said rather than left to be discovered: somebody who wants one of these
        # outside VPinFE has to be told where they are.
        "kept_in": config_backups.home_for(launcher_id, found.display_name),
    }


def take_backup(launcher_id: str, label: str = "") -> dict[str, Any]:
    found = launcher_or_refuse(launcher_id)
    files = _config_files(found)
    if not files:
        raise service_errors.RefusedError(
            t("error.launchers.keeps_no_settings_file", app_name=(apps.app_name(found.app))))
    taken = config_backups.take(launcher_id, files,
                                label=label,
                                named=found.display_name)
    if not taken:
        raise service_errors.RefusedError(
            t("error.launchers.nothing_copy_yet_file"))
    return {"taken": [_as_backup(one) for one in taken]}


def restore_backup(launcher_id: str, name: str) -> dict[str, Any]:
    """A copy of what is there now is taken first. Restoring the wrong one is a mistake
    somebody makes once, and without that copy it is the last one they get to make."""
    found = launcher_or_refuse(launcher_id)
    try:
        safety = config_backups.restore(launcher_id, name, _config_files(found),
                                        named=found.display_name)
    except FileNotFoundError as exc:
        raise service_errors.NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise service_errors.RefusedError(str(exc)) from exc
    return {"restored": name,
            "safety_copy": _as_backup(safety) if safety else None}


def forget(launcher_id: str) -> dict[str, Any]:
    """Its mappings go with it. A table pointing at a launcher that was deleted is not a
    state anybody chose, so it goes back to the default."""
    store = launchers.get_launcher_store()
    if not store.remove(launcher_id):
        raise service_errors.NotFoundError(
            t("error.launchers.no_launcher", launcher_id=(launcher_id)))
    return {"launcher_id": launcher_id, "removed": True}


def assign(table_id: str, launcher_id: str) -> dict[str, Any]:
    """An empty `launcher_id` clears it, which is how a table goes back to the default.

    Cleared rather than stored blank: an absent mapping already means the default, and
    two spellings of one state is what makes a reader ask which is which.
    """
    wanted = str(launcher_id or "").strip()
    store = launchers.get_launcher_store()
    if wanted and store.get(wanted) is None:
        raise service_errors.NotFoundError(t("error.launchers.no_launcher", launcher_id=(wanted)))
    store.assign(table_id, wanted)
    return {"table_id": table_id, "launcher_id": store.mapped(table_id)}
