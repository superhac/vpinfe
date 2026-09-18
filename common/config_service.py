"""Every setting this install has, what it is set to, and what may be changed.

`common/config_schema.py` declares what a setting is called, what it accepts and what it
means. This answers the three questions a settings page asks of that: describe it, read
it, write it - once, so the config file, the Console and anything reading over HTTP
describe the same install the same way.

Values are typed the way the store types them - a bool arrives as a bool, a list as a
list - because a caller that has to know which strings mean true holds half a schema of
its own.
"""

from __future__ import annotations

import logging
from typing import Any

from common import config_schema, install_presence, path_checks
from common.paths import get_ini_config

logger = logging.getLogger("vpinfe.common.config_service")

# Theme sources are URLs VPinFE fetches code from. Reading them is fine; setting them is
# how a hostile write turns into code execution on the cabinet, so it stays a deliberate
# edit of the file. Enforced here rather than left to a caller to respect, because a rule
# only a caller enforces is not a rule.
READ_ONLY_SECTIONS = frozenset({"themes"})


class UnknownSettingsError(ValueError):
    """Keys no schema knows. `keys` names every one of them."""

    def __init__(self, keys: list[str]) -> None:
        self.keys = sorted(keys)
        super().__init__(", ".join(self.keys))


class SettingsWriteError(RuntimeError):
    """The settings file could not be written. The values are already in the store."""


class ReadOnlySettingsError(ValueError):
    """Keys this install will not take over the wire. `keys` names every one."""

    def __init__(self, keys: list[str]) -> None:
        self.keys = sorted(keys)
        super().__init__(", ".join(self.keys))


def _describe(option: config_schema.ConfigOption) -> dict[str, Any]:
    return {
        "section": option.section,
        "key": option.key,
        "type": option.type,
        "default": option.default,
        "label": option.label or option.key,
        "label_key": f"{option.keys}.label",
        "description": option.description,
        "choices": list(option.choices),
        "writable": option.section not in READ_ONLY_SECTIONS,
        # So a caller knows which strings name something on disk without matching on the
        # key. Empty for everything that is only text.
        "path": option.path,
        # Which live list is worth offering beside this setting, where one is. Named
        # rather than filled in here: the values change while the install runs, so a
        # caller asks for them when it draws rather than reading a snapshot taken when
        # the schema was described.
        "suggest": option.suggest,
        # What to gather it under on a page. Answered here rather than decided by each
        # surface, so the grouping is the schema's answer and not one each one invents.
        "group": option.group,
        "editor": option.editor,
        # How many rows a text field gets. A setting declared over three lines that
        # arrives without this renders as a one-line box - which is what a command list
        # did until it was served.
        "lines": option.lines,
    }


def schema() -> dict[str, Any]:
    """What a settings page is built from.

    Internal options are left out: they are runtime state that happens to live in the
    config file, and offering a last-played pointer as a setting invites someone to set
    it. `settable()` is the same predicate the config file's own docs use.
    """
    options = [_describe(option) for option in config_schema.settable()]
    sections = [{"name": name,
                 "writable": name not in READ_ONLY_SECTIONS,
                 "options": [o for o in options if o["section"] == name]}
                for name in dict.fromkeys(option["section"] for option in options)]
    return {"sections": sections, "count": len(options)}


def path_states() -> dict[str, Any]:
    """Every path setting, checked against this machine's disk.

    All of them in one answer rather than one call per field: a settings page wants the
    whole column at once, and the alternative is six requests that each stat one file.
    """
    store = get_ini_config()
    checks = [{"section": option.section, "key": option.key, "path": option.path,
               "state": state, "reason": reason}
              for option in path_checks.path_options()
              for state, reason in [path_checks.check_option(
                  option, store.value(option.section, option.key))]]
    return {"checks": checks}


def values() -> dict[str, Any]:
    """Current values, typed. A setting the file does not carry answers its default,
    because that is what the install is actually running on."""
    store = get_ini_config()
    found: dict[str, dict[str, Any]] = {}
    for option in config_schema.settable():
        found.setdefault(option.section, {})[option.key] = \
            store.value(option.section, option.key)
    return {"values": found}


def set_values(wanted: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """A patch: only the sections and keys given are written.

    Every key is checked against the schema first and the whole request is refused if any
    of them is unknown. Half-applying a settings save leaves an install in a state nobody
    asked for and no screen reflects.
    """
    store = get_ini_config()
    staged: list[tuple[str, str, Any]] = []
    unknown: list[str] = []
    refused: list[str] = []

    for section, entries in (wanted or {}).items():
        for key, value in (entries or {}).items():
            # Any spelling this setting has ever had, including a section it has since
            # moved out of. A caller written against an older name keeps working, which
            # is the contract every other reader of the config already honours.
            here, name = config_schema.locate(section, key)
            option = config_schema.option(here, name)
            if option is None or option.internal:
                unknown.append(f"{section}.{key}")
            elif option.section in READ_ONLY_SECTIONS:
                refused.append(f"{option.section}.{option.key}")
            else:
                staged.append((option.section, option.key, value))

    if unknown:
        raise UnknownSettingsError(unknown)
    if refused:
        raise ReadOnlySettingsError(refused)
    if not staged:
        return values()

    for section, key, value in staged:
        store.set_value(section, key, value)
    try:
        store.save()
    except Exception as exc:
        logger.exception("Could not write the settings file")
        raise SettingsWriteError(str(exc)) from exc

    if any(section == "install" and key == "display_name" for section, key, _ in staged):
        # The registry holds a copy of what each install reported. This one just changed
        # what it reports, and every screen listing devices reads the copy.
        install_presence.record_self()
    return values()
