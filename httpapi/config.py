"""Every setting this install has, and what it is currently set to.

`common/config_schema.py` already declares what a setting is called, what it accepts and
what it means, and says in its own docstring that the config file, the Manager UI and
anything reading over HTTP should describe it the same way. This is the HTTP half of
that: the schema is served rather than restated, so a client renders a settings page
from what the install says about itself instead of from a list it carries.

Values are typed the way the store types them - a bool arrives as a bool, a list as a
list - because a client that has to know which strings mean true is a client that has
half a schema of its own.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body

from common import config_schema, path_checks
from common.paths import get_ini_config

from . import models, scopes
from .auth import requires
from .errors import ConflictError, InvalidRequestError

logger = logging.getLogger("vpinfe.httpapi.config")

router = APIRouter(prefix="/config", tags=["config"])

# Theme sources are URLs VPinFE fetches code from. Reading them over HTTP is fine;
# setting them is how a hostile write turns into code execution on the cabinet, so it
# stays a deliberate edit of the file. Declared here rather than left to a client to
# respect, because a rule only a client enforces is not a rule.
READ_ONLY_SECTIONS = frozenset({"themes"})


def _describe(option: config_schema.ConfigOption) -> dict[str, Any]:
    return {
        "section": option.section,
        "key": option.key,
        "type": option.type,
        "default": option.default,
        "label": option.label or option.key,
        "description": option.description,
        "choices": list(option.choices),
        "writable": option.section not in READ_ONLY_SECTIONS,
        # So a client knows which strings name something on disk without matching on the
        # key. Empty for everything that is only text.
        "path": option.path,
    }


@router.get("/schema", summary="Every setting this install has",
            dependencies=[requires(scopes.CONFIG_READ)])
def get_schema() -> models.ConfigSchema:
    """What a settings page is built from.

    Internal options are left out: they are runtime state that happens to live in the
    config file, and offering a last-played pointer as a setting invites someone to set
    it. `settable()` is the same predicate the config file's own docs use.
    """
    options = [_describe(option) for option in config_schema.settable()]
    sections = []
    for name in dict.fromkeys(option["section"] for option in options):
        sections.append({
            "name": name,
            "writable": name not in READ_ONLY_SECTIONS,
            "options": [o for o in options if o["section"] == name],
        })
    return {"sections": sections, "count": len(options)}


@router.get("/paths", summary="Whether each path setting finds anything",
            dependencies=[requires(scopes.CONFIG_READ)])
def get_path_checks() -> models.ConfigPathChecks:
    """Every path setting, checked against this machine's disk.

    All of them in one answer rather than one call per field: a settings page wants the
    whole column at once, and the alternative is six requests that each stat one file.

    The caller names no path. It asks about settings, and the install answers about the
    values it holds - so this cannot be used to ask whether a file exists somewhere a
    caller is not otherwise allowed to look.
    """
    store = get_ini_config()
    checks = []
    for option in path_checks.path_options():
        state, reason = path_checks.check_option(
            option, store.value(option.section, option.key))
        checks.append({"section": option.section, "key": option.key,
                       "path": option.path, "state": state, "reason": reason})
    return {"checks": checks}


@router.get("", summary="What this install is set to",
            dependencies=[requires(scopes.CONFIG_READ)])
def get_values() -> models.ConfigValues:
    """Current values, typed. A setting the file does not carry answers its default,
    because that is what the install is actually running on."""
    store = get_ini_config()
    values: dict[str, dict[str, Any]] = {}
    for option in config_schema.settable():
        values.setdefault(option.section, {})[option.key] = \
            store.value(option.section, option.key)
    return {"values": values}


@router.put("", summary="Change settings",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_values(values: dict[str, dict[str, Any]] = Body(...)) -> models.ConfigValues:
    """A patch: only the sections and keys sent are written.

    Every key is checked against the schema first and the whole request is refused if
    any of them is unknown. Half-applying a settings save leaves an install in a state
    nobody asked for and no screen reflects.
    """
    store = get_ini_config()
    staged: list[tuple[str, str, Any]] = []
    unknown: list[str] = []
    refused: list[str] = []

    for section, entries in (values or {}).items():
        for key, value in (entries or {}).items():
            # Any spelling this setting has ever had, including a section it has since
            # moved out of. A client written against an older name keeps working, which
            # is the contract every other reader of the config already honours.
            here, name = config_schema.locate(section, key)
            option = config_schema.option(here, name)
            if option is None or option.internal:
                unknown.append(f"{section}.{key}")
                continue
            if option.section in READ_ONLY_SECTIONS:
                refused.append(f"{option.section}.{option.key}")
                continue
            staged.append((option.section, option.key, value))

    if unknown:
        raise InvalidRequestError(
            "Not settings this install has: " + ", ".join(sorted(unknown))
            + ". GET /config/schema lists them.")
    if refused:
        raise InvalidRequestError(
            "Read-only over HTTP: " + ", ".join(sorted(refused))
            + ". Theme sources are code this install fetches; editing them stays a "
              "deliberate edit of the settings file.")
    if not staged:
        return get_values()

    for section, key, value in staged:
        store.set_value(section, key, value)
    try:
        store.save()
    except Exception as exc:  # noqa: BLE001 - the caller gets the reason, not a 500
        logger.exception("Could not write the settings file")
        raise ConflictError(f"Could not write the settings file: {exc}") from exc

    if any(section == "install" and key == "display_name" for section, key, _ in staged):
        # The registry holds a copy of what each install reported. This one just changed
        # what it reports, and every screen listing devices reads the copy.
        from .instance import record_self
        record_self()
    return get_values()
