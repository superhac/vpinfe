"""The configured ways this install runs a table.

A launcher is an object somebody creates, removes and duplicates, and what it names is a
program on this machine. Copying one to a cabinet keeps its id, which is why the id is the
caller's rather than something minted on every write.

The app it runs declares its own settings, so a caller can draw an editor without knowing
what a Visual Pinball launcher happens to hold.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

from common import apps, i18n, path_checks, service_errors
from common.apps.contract import SCOPE_ENTRY, SCOPE_FOLDER, SCOPE_LAUNCHER
from common.games import config_backups, game_repository, launchers, tables
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
    settings = _launcher_settings(launcher)
    left_empty = getattr(_app_settings_surface(launcher), "left_empty", None)
    blanks = left_empty(settings) if callable(left_empty) else {}
    return {
        "launcher_id": launcher.launcher_id,
        "app": launcher.app,
        "app_name": apps.app_name(launcher.app),
        "display_name": launcher.display_name,
        "enabled": launcher.enabled,
        "owns_ini": launcher.owns_ini,
        "has_config": _app_settings_surface(launcher) is not None,
        "settings": settings,
        # `lines`, `choices` and the bounds travel with the field because the control a
        # surface draws is decided from them - a field declared over three lines that
        # arrives without them renders as a one-line box.
        "fields": [{"key": f.key, **apps.field_words(launcher.app, f), "type": f.type,
                    "default": f.default, "path": f.path,
                    "lines": f.lines, "choices": dict(f.choices),
                    "min": f.minimum, "max": f.maximum,
                    "blank": apps.field_blank(launcher.app, f) or blanks.get(f.key, ""),
                    "left_empty": blanks.get(f.key, "")}
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
    mappings = store.mappings()
    plays = Counter(getattr(launchers.launcher_for_entry(app_id, table_id, held, mappings),
                            "launcher_id", "")
                    for app_id, table_id in _library_tables())
    return {
        "launchers": [_described(one) for one in held],
        "mappings": mappings,
        "defaults": {app.id: getattr(launchers.default_for(app.id, held),
                                     "launcher_id", None)
                     for app in apps.all_apps()},
        "tables": {one.launcher_id: plays[one.launcher_id] for one in held},
        "apps": [{"id": app.id, "name": apps.app_name(app.id),
                  "suffixes": list(app.claim.suffixes),
                  "has_config": app.config is not None,
                  "fields": [{"key": f.key, **apps.field_words(app.id, f), "path": f.path,
                              "blank": apps.field_blank(app.id, f)}
                             for f in app.fields]}
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
    name = str(body.get("display_name") or "").strip() or apps.app_name(app_id)
    if any(launchers.same_name(name, one.display_name) for one in store.launchers()
           if one.launcher_id != wanted):
        raise service_errors.RefusedError(t("error.launchers.name_taken", name=name))
    enabled = bool(body.get("enabled", True))
    before = store.get(wanted)
    if before is not None and before.enabled and not enabled:
        refused = _fallback(before)["refused"]
        if refused:
            raise service_errors.RefusedError(refused)
    written = store.put(launchers.Launcher(
        launcher_id=wanted,
        app=app_id,
        display_name=name,
        enabled=enabled,
        owns_ini=bool(body.get("owns_ini", False)),
        settings=dict(body.get("settings") or {}),
    ))
    return _described(written)


def fallback(launcher_id: str) -> dict[str, Any]:
    """What switching one off would do: the tables it plays, where each group of them
    would go, and the refusal `put` would give, or ""."""
    return _fallback(launcher_or_refuse(launcher_id))


def _fallback(leaving: launchers.Launcher) -> dict[str, Any]:
    store = launchers.get_launcher_store()
    held = store.launchers()
    mappings = store.mappings()
    without = [replace(one, enabled=False) if one.launcher_id == leaving.launcher_id
               else one for one in held]
    moving: dict[str, tuple[launchers.Launcher | None, int]] = {}
    for app_id, table_id in _library_tables():
        now = launchers.launcher_for_entry(app_id, table_id, held, mappings)
        if now is None or now.launcher_id != leaving.launcher_id:
            continue
        after = launchers.launcher_for_entry(app_id, table_id, without, mappings)
        key = after.launcher_id if after is not None else ""
        moving[key] = (after, moving.get(key, (after, 0))[1] + 1)
    return {
        "tables": sum(count for _one, count in moving.values()),
        "fallbacks": [{"launcher_id": key,
                       "display_name": one.display_name if one is not None else "",
                       "tables": count,
                       "has_program": one is not None and _has_program(one)}
                      for key, (one, count) in moving.items()],
        "refused": _refusal([one for one, _count in moving.values()]),
    }


def _refusal(fallbacks: list[launchers.Launcher | None]) -> str:
    for one in fallbacks:
        if one is None:
            return t("error.launchers.no_fallback")
        if not _has_program(one):
            return t("error.launchers.fallback_has_no_program", name=one.display_name)
    return ""


def _has_program(launcher: launchers.Launcher) -> bool:
    return all(str(launcher.value(field.key) or "").strip()
               for field in launcher.fields() if field.path == "exe")


def _library_tables() -> Iterator[tuple[str, str]]:
    """(app, table id) for every table in the library that has an id."""
    for game in game_repository.all_games():
        stored = (getattr(game, "meta_config", None) or {}).get(tables.TABLES_KEY)
        for entry in (stored.values() if isinstance(stored, dict) else ()):
            found = tables.table_id(entry)
            if found:
                yield tables.app_of(entry), found


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
        return {"groups": [], "values": {}, "scopes": [], "shared_with_game": False,
                "from_game": {}, "app_name": apps.app_name(found.app)}

    settings = _launcher_settings(found)
    if scope not in config.scopes():
        raise service_errors.RefusedError(
            t("error.launchers.no_scope_called_app", scope=(scope),
                    join=(', '.join(config.scopes()))))
    target = _game_file(table)
    values = config.read(scope, target, settings)
    scopes_for = _scopes_for(config)
    shares = getattr(config, "shared_with_game", None)
    reach = getattr(config, "from_game", None)

    def shown(field: apps.Field) -> bool:
        held = values.get(field.key)
        return scope in scopes_for(field.key) or (held is not None and held.set_here)

    blank = _blank_words(found.app, config)
    named = _named_values(found.app, config)
    reporting = getattr(config, "reported", None)
    reported = dict(reporting()) if reporting is not None else {}
    held = getattr(config, "held_groups", None)
    declared = (*config.groups(settings),
                *(held(target) if target and held is not None else ()))
    groups = [(g, [f for f in g.settings if shown(f)]) for g in declared]
    rows = getattr(config, "summary_rows", None)

    def drawn(group: apps.ConfigGroup, fields: list[apps.Field]) -> list[str]:
        keys = {f.key for f in fields}
        named = rows(group.key, values) if group.summarized and rows is not None else ()
        return [key for key in named if key in keys]

    return {
        "app_name": apps.app_name(found.app),
        "scopes": list(config.scopes()),
        "shared_with_game": bool(target and shares is not None and shares(target)),
        "from_game": (dict(reach(target, settings))
                      if scope == SCOPE_ENTRY and target and reach is not None else {}),
        "groups": [{"key": g.key, **apps.group_words(found.app, g),
                    "summarized": g.summarized, "rows": drawn(g, fields),
                    "read_only": g.read_only,
                    "curated": _curated(found.app, g, {f.key for f in fields}),
                    "settings": [{**_described_field(found.app, f), **blank(f.key),
                                  "named": named(f.key),
                                  "reported": list(reported.get(f.key, ())),
                                  "scopes": list(scopes_for(f.key))} for f in fields]}
                   for g, fields in groups if fields],
        "values": {key: {"value": one.value, "scope": one.scope,
                         "set_here": one.set_here, "in_effect": one.in_effect,
                         "fallback": one.fallback, "fallback_scope": one.fallback_scope}
                   for key, one in values.items()},
    }


def _scopes_for(config: Any) -> Callable[[str], tuple[str, ...]]:
    """An app that does not say otherwise offers every setting at every scope."""
    answer = getattr(config, "scopes_for", None)
    return answer if answer is not None else (lambda _key: tuple(config.scopes()))


def _blank_words(app_id: str, config: Any) -> Callable[[str], dict[str, str]]:
    """What a blank value does, in the app's own words, where the app says it is not the
    declared default: `blank` the word and `left_empty` its help. An app that does not
    say leaves every one empty."""
    naming = getattr(config, "blank_words", None)
    words = dict(naming()) if naming is not None else {}

    def said(key: str) -> dict[str, str]:
        word = f"app.{app_id}.{words[key]}" if key in words else ""
        return {"blank": i18n.literal_or("", word)[0] if word else "",
                "left_empty": i18n.literal_or("", f"{word}.help")[0] if word else ""}
    return said


def _named_values(app_id: str, config: Any) -> Callable[[str], list[list[str]]]:
    """The values a setting's app gives a meaning of their own, each `[value, label]` in
    the app's words. An app that does not say names none."""
    naming = getattr(config, "named_values", None)
    named = dict(naming()) if naming is not None else {}
    return lambda key: [[value, i18n.literal_or("", f"app.{app_id}.{word}")[0]]
                        for value, word in named.get(key, ())]


def _described_field(app_id: str, field: apps.Field) -> dict[str, Any]:
    return {"key": field.key, **apps.field_words(app_id, field),
            "help": apps.field_help(app_id, field), "type": field.type,
            "default": field.default,
            "choices": [list(pair) for pair in field.choices],
            "choice_help": apps.choice_help(app_id, field),
            "minimum": field.minimum, "maximum": field.maximum,
            "per_table": field.per_table}


def _curated(app_id: str, group: apps.ConfigGroup, shown: set[str]) -> list[dict[str, Any]]:
    """The group's curated headings, holding only rows this scope shows."""
    switches = {one.enabled_by for one in group.curated if one.enabled_by in shown}
    found = []
    for heading in group.curated:
        keys = [key for key in heading.keys if key in shown]
        if keys:
            switched = heading.enabled_by in keys
            found.append({"key": heading.key, **apps.heading_words(app_id, group.key,
                                                                   heading),
                          "keys": keys,
                          "enabled_by": heading.enabled_by if switched else "",
                          "rivals": [key for key in heading.rivals if key in switches]
                          if switched else [],
                          "kinds": list(heading.kinds),
                          "pairs": [{"key": pair.key,
                                     **apps.pair_words(app_id, group.key, pair),
                                     "keys": list(pair.keys)}
                                    for pair in heading.pairs if set(pair.keys) <= shown],
                          "switched": [{"enabled_by": one.enabled_by, "keys": rows,
                                        "on": one.on}
                                       for one in heading.switched if one.enabled_by in keys
                                       if (rows := [key for key in one.keys if key in keys])]})
    return found


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
    if scope == SCOPE_FOLDER:
        raise service_errors.RefusedError(t("error.launchers.game_file_read_only"))
    values = body.get("values") or {}
    if not isinstance(values, dict) or not values:
        raise service_errors.RefusedError(t("error.launchers.name_least_one_setting"))
    settings = _launcher_settings(found)
    table = _game_file(str(body.get("table") or ""))
    writing = {str(k): str(v) for k, v in values.items()}
    scopes_for = _scopes_for(config)
    refused = sorted(key for key, value in writing.items()
                     if value != "" and scope not in scopes_for(key))
    if refused:
        raise service_errors.RefusedError(t(
            "error.launchers.one_table_only" if scope == SCOPE_LAUNCHER
            else "error.launchers.all_tables_only", app_name=(apps.app_name(found.app)),
            keys=(", ".join(refused))))

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


def make_default(launcher_id: str) -> dict[str, Any]:
    """Make it the launcher its app's tables use unless they name another."""
    found = launcher_or_refuse(launcher_id)
    if not _has_program(found):
        raise service_errors.RefusedError(
            t("error.launchers.default_has_no_program", name=found.display_name))
    if not found.enabled:
        raise service_errors.RefusedError(
            t("error.launchers.default_switched_off", name=found.display_name))
    store = launchers.get_launcher_store()
    store.to_front(found.launcher_id)
    return {"launcher_id": found.launcher_id, "app": found.app}


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
