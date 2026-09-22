"""VPinFE's settings, stored as JSON and read from an ini once.

The file is `vpinfe.json`; a `vpinfe.ini` beside it is read on the first run that finds
one, converted, and kept. Every other config file VPinFE owns is already JSON, and this
was the only one that was both hand-edited and machine-written - which is exactly why it
was the only one whose comments `configparser.write()` destroyed.

In memory it is still a ConfigParser, so nothing above this module changed. What is on
disk carries real booleans and integers, and a schema version.
"""

from __future__ import annotations

import configparser
import json
import logging
import os
from pathlib import Path
from typing import Any

from common import config_schema, input_registry
from common.atomic_write import write_atomic
from common.deprecations import announce
from common.games.info_migration import copy_aside
from common.values import is_truthy

logger = logging.getLogger("vpinfe.common.config_store")

SCHEMA_KEY = "schema"
SETTINGS_KEY = "settings"

# Generations of the settings file, counting from the first one that shipped.
#   1  the ini. Implied - it is recognized by being an ini, not by anything written in
#      it, so a schema key never appears in one.
#   2  JSON. Keys are snake_case and each window has a section of its own.
#
# The JSON side counted 1, 2, 3 during 3.0 development, one bump per shape change while
# the format was being designed. None of those shipped, so they collapse into the single
# generation users will actually receive.
CONFIG_SCHEMA = 2

# (from, to, key) for options that changed section. Applied on every read, so an ini
# written by any earlier build lands in the right place.
_MOVED_OPTIONS = (
    # What the frontend shows, not what a screen is. Two hops because a 3.0 build already
    # relocated it once, and the more recent location is listed first: `_move_option`
    # keeps what it finds at the destination, so whichever runs first wins.
    ('Displays', 'presentation', 'cabmode'),
    ('Settings', 'presentation', 'cabmode'),
    ('Settings', 'DOF', 'enabledof'),
    ('Displays', 'Settings', 'splashscreen'),
    # `input` is which button does what; how far a press moves the wheel is what the
    # frontend does when one is pressed. Moved rather than declared afresh: a file
    # already holding these keeps its values, and the old entries go rather than
    # lingering as a second copy the settings page would render beside the new one.
    ('input', 'behavior', 'paging_group'),
    ('input', 'behavior', 'paging_size'),
    ('lifecycle', 'behavior', 'confirm'),
)


# The values that changed vocabulary, not just the key that holds them. Renaming a key
# is handled below; renaming what it may contain was not, so a file kept the retired word
# and the schema's own choices said otherwise. One entry today - `paging_group` is the
# only choice option of twelve whose values moved - so this is a lookup, not a framework.
_RENAMED_VALUES = {
    ('behavior', 'paging_group'): config_schema.PAGING_GROUP_ALIASES,
}

# The same, for a setting that holds several values at once. Separate because a list is
# rewritten item by item and a choice is replaced whole, and because an unmigrated item
# here is not a stale spelling that still resolves - `roles` is filtered against a known
# set, so a retired word is dropped and the install stops claiming what it dropped.
# A retired word inside a list. `player` named the install that launches games before
# `device` did; both are now the `frontend` feature, which the roles migration below
# expands - this pass only normalizes the spelling first so one map handles it.
_RENAMED_LIST_VALUES = {
    ('install', 'roles'): {'player': 'device'},
}


# (section, old key, new key) - see the migration in _migrate below.
_RENAMED_KEYS = (
    ('Displays', 'tablescreenid', 'playfieldscreenid'),
    ('Displays', 'tableorientation', 'playfieldorientation'),
    ('Displays', 'tablerotation', 'playfieldrotation'),
    ('Settings', 'tablerootdir', 'gamerootdir'),
    ('Media', 'tabletype', 'playfieldvariant'),
    ('Media', 'tableresolution', 'playfieldresolution'),
    ('Media', 'tablevideoresolution', 'playfieldvideoresolution'),
    ('Media', 'tablemediapriority', 'playfieldmediapriority'),
    # `console` is the web UI now, so the log destination says which one it means.
    ('logger', 'console', 'terminal'),
)

def _nest(sections: dict) -> dict:
    """`windows.playfield` becomes a playfield object inside a windows object.

    A ConfigParser section is a flat string, so the hierarchy is spelled with dots in
    memory and is real on disk - which is the point of giving each window a section.
    """
    out: dict = {}
    for name, values in sections.items():
        node = out
        parts = name.split('.')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = values
    return out


def _flatten(tree: dict, prefix: str = '') -> dict:
    """The inverse of _nest: nested objects back to dotted section names."""
    out: dict = {}
    for name, value in (tree or {}).items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict) and any(isinstance(v, dict) for v in value.values()):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


class ConfigStore:
    """The settings file, read once and written atomically."""

    def _move_option(self, old_section: str, new_section: str, key: str) -> bool:
        """Move one option to the section it lives in now, keeping the user's value.

        The destination section may not exist yet: this runs before the defaults are
        filled in, and filling them in is what creates sections.
        """
        if not self.config.has_option(old_section, key):
            return False
        announce('ini-moved-options', f'{old_section}.{key}')
        if not self.config.has_section(new_section):
            self.config.add_section(new_section)
        if not self.config.has_option(new_section, key):
            self.config.set(new_section, key, self.config.get(old_section, key))
        self.config.remove_option(old_section, key)
        return True

    def __init__(self, configfilepath: str | Path) -> None:

        self.defaults = config_schema.defaults()

        self.config = configparser.ConfigParser()
        # Callers pass whichever name they know; both are derived so none had to change.
        base = Path(configfilepath)
        self.json_path = base.with_suffix('.json')
        self.ini_path = base.with_suffix('.ini')
        self.configfilepath = str(self.json_path)
        self._schema = CONFIG_SCHEMA
        self._converted_from_ini = False

        self.is_new = False
        if os.path.exists(self.json_path):
            self._load_json()
        elif os.path.exists(self.ini_path):
            logger.info("Converting %s to %s", self.ini_path, self.json_path)
            self.config.read(self.ini_path)
            self._converted_from_ini = True
        else:
            logger.info("Generating default settings at: %s", self.json_path)
            self.is_new = True
            self.format_defaults()
            self.save()

        changed = self._converted_from_ini

        # Both of these run BEFORE the defaults are filled in. Each copies only when the
        # target key is absent, and these keys have defaults - so with a default already
        # written the guard finds one, copies nothing, and remove_option then drops what
        # the user actually set. cabmode and enabledof shipped doing exactly that.

        # A table folder is a game, and the table screen is the playfield. Read the old
        # key once and write the new one, so an existing vpinfe.ini is corrected in place.
        for section, old, new in _RENAMED_KEYS:
            if self.config.has_option(section, old):
                announce('ini-renamed-keys', old)
                if not self.config.has_option(section, new):
                    self.config.set(section, new, self.config.get(section, old))
                self.config.remove_option(section, old)
                changed = True

        # Options that changed section rather than name.
        for old_section, new_section, key in _MOVED_OPTIONS:
            changed |= self._move_option(old_section, new_section, key)

        # [Input] is a merge, not a move: an action had one key per input, and both
        # become entries in its single binding list, so the generic pass below - which
        # moves one value at a time - would have the second overwrite the first.
        if self.config.has_section('Input'):
            for action in input_registry.actions():
                found = []
                for old in action.legacy:
                    if not self.config.has_option('Input', old):
                        continue
                    found += input_registry.binding_for_legacy(
                        old, self.config.get('Input', old))
                    self.config.remove_option('Input', old)
                    changed = True
                if not found:
                    continue
                # Keyboard first, then pads, and never the same binding twice.
                ordered = ([b for b in found if b.startswith(input_registry.KEY_PREFIX)]
                           + [b for b in found if not b.startswith(input_registry.KEY_PREFIX)])
                if not self.config.has_section(input_registry.SECTION):
                    self.config.add_section(input_registry.SECTION)
                self.config.set(input_registry.SECTION, action.name,
                                ','.join(dict.fromkeys(ordered)))

        # Every spelling a key has ever had lands on the one we store. This runs after the
        # 2.x renames above, so tablerootdir -> gamerootdir -> game_root_dir is one chain,
        # and before the defaults are filled in, so nothing is added under an old name.
        for section in list(self.config.sections()):
            for key in list(self.config.options(section)):
                new_section, new_key = config_schema.locate(section, key)
                if (new_section, new_key) == (section, key):
                    continue
                if not self.config.has_section(new_section):
                    self.config.add_section(new_section)
                self.config.set(new_section, new_key, self.config.get(section, key))
                self.config.remove_option(section, key)
                changed = True

        # A retired spelling of a *value*. It resolves on read either way, so this is
        # about what the file says rather than what it does - and the file is what the
        # settings are served as, so it should not contradict the schema's choices.
        for (section, key), aliases in _RENAMED_VALUES.items():
            if not self.config.has_option(section, key):
                continue
            current = self.config.get(section, key).strip().lower()
            if current in aliases:
                announce('ini-renamed-values', f'{section}.{key}={current}')
                self.config.set(section, key, aliases[current])
                changed = True

        # A retired word inside a list. Unlike the choice above this one does not resolve
        # on read: `roles` is filtered against a known set, so an install written before
        # the rename silently stopped claiming the role rather than claiming it under the
        # old name. Order is kept, because the schema's default reads library first.
        for (section, key), aliases in _RENAMED_LIST_VALUES.items():
            if not self.config.has_option(section, key):
                continue
            items = [v.strip() for v in self.config.get(section, key).split(',')]
            renamed = [aliases.get(v.lower(), v) for v in items if v]
            if renamed != [v for v in items if v]:
                announce('ini-renamed-values', f'{section}.{key}')
                self.config.set(section, key, ','.join(renamed))
                changed = True

        # `install.roles` became `install.features`, and one role expands into two
        # features - the old `hub` was the library and the device list together, `device`
        # frontend - so neither _RENAMED_KEYS nor _RENAMED_LIST_VALUES can carry it.
        #
        # Written against the *value* rather than the old key on purpose. `roles` is an
        # alias, so the pass above has already moved it under `features` by the time this
        # runs, and matching on the key would silently never fire. An install that said
        # only `device` must not fall through to the default, which is everything - that
        # would hand a cab a library it never had.
        if self.config.has_option('install', 'features'):
            was = [v.strip().lower()
                   for v in self.config.get('install', 'features').split(',') if v.strip()]
            spread = {'hub': ('library', 'devices'), 'device': ('frontend',),
                      'player': ('frontend',)}
            if any(role in spread for role in was):
                now: list[str] = []
                for role in was:
                    for feature in spread.get(role, (role,)):
                        if feature not in now:
                            now.append(feature)
                announce('ini-roles-to-features', ','.join(was))
                # Every feature, in the order the install declares them. Overview is in
                # the list so that an install already asking for it keeps it, and no
                # role expands into it, so migrating never acquires one.
                order = ('library', 'frontend', 'devices', 'overview')
                self.config.set('install', 'features',
                                ','.join(f for f in order if f in now))
                changed = True

        # `behavior.confirm` was a list of scopes and is a switch now. Anything naming a
        # scope meant "ask me", so it becomes on; empty meant "never", so it becomes off.
        # Read rather than coerced: a stored "app,system" is not a boolean, and letting the
        # type conversion have it would answer no to someone who asked to be asked.
        if self.config.has_option('behavior', 'confirm'):
            raw = self.config.get('behavior', 'confirm').strip()
            if raw.lower() not in ('', 'true', 'false'):
                announce('confirm-scopes-to-switch', raw)
                self.config.set('behavior', 'confirm', 'true')
                changed = True
            elif not raw:
                self.config.set('behavior', 'confirm', 'false')
                changed = True

        # Add any missing default options
        for section, defaults in self.defaults.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
                changed = True
            for key, value in defaults.items():
                if not self.config.has_option(section, key):
                    self.config.set(section, key, value)
                    changed = True

        # Remove legacy Logger.file option; logs always go to the standard config dir file.
        if self.config.has_option('logger', 'file'):
            self.config.remove_option('logger', 'file')
            changed = True

        # Normalize blank theme values back to the configured default.
        current_theme = self.config.get('themes', 'active', fallback='').strip()
        if not current_theme:
            self.config.set('themes', 'active', self.defaults['themes']['active'])
            changed = True

        # Migrate misspelled vpinplay.initals to vpinplay.initials if present.
        if self.config.has_option('vpinplay', 'initals'):
            legacy_initials = self.config.get('vpinplay', 'initals', fallback='').strip()
            current_initials = self.config.get('vpinplay', 'initials', fallback='').strip()
            if legacy_initials and not current_initials:
                self.config.set('vpinplay', 'initials', legacy_initials)
            self.config.remove_option('vpinplay', 'initals')
            changed = True

        # A section the migration emptied - [Input] once its keys merge into [input], or
        # one whose every key moved elsewhere - would sit in the file forever as a husk.
        # Defaults are filled in above, so anything still empty has no values and none
        # coming.
        for section in list(self.config.sections()):
            if not self.config.options(section):
                self.config.remove_section(section)
                changed = True

        if changed:
            self.save()

    def _typed(self, section: str, key: str, raw: str) -> Any:
        """The value as JSON should hold it. Unknown keys stay strings.

        An empty string stays empty rather than becoming 0 or null: several int settings
        use blank to mean "no window on this one", and that is not the same as zero.
        """
        entry = config_schema.option(section, key)
        text = '' if raw is None else str(raw)
        if entry is None:
            return text
        # Before the blank rule below: an empty list is [], which a user editing the file
        # by hand can add to. "" would leave them guessing what shape it wanted.
        if entry.type == 'list':
            return [part.strip() for part in text.split(',') if part.strip()]
        if text.strip() == '':
            return text
        if entry.type == 'bool':
            return is_truthy(text)
        if entry.type == 'int':
            try:
                return int(float(text))
            except (TypeError, ValueError):
                return text
        return text

    @staticmethod
    def _as_text(value: Any) -> str:
        """Back to what a ConfigParser holds, so nothing above this module changes."""
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (list, tuple)):
            return ','.join(str(v) for v in value)
        return '' if value is None else str(value)

    def _load_json(self) -> None:
        with open(self.json_path, encoding='utf-8') as handle:
            payload = json.load(handle) or {}
        self._schema = int(payload.get(SCHEMA_KEY, CONFIG_SCHEMA) or CONFIG_SCHEMA)
        for section, values in _flatten(payload.get(SETTINGS_KEY) or {}).items():
            if not self.config.has_section(section):
                self.config.add_section(section)
            for key, value in (values or {}).items():
                # Any spelling a file has ever used lands under the name we store now.
                self.config.set(section, config_schema.canonical(section, key),
                                self._as_text(value))

    def value(self, section: str, key: str) -> Any:
        """One setting, typed the way this store would write it back.

        Public because the HTTP API needs what the Manager UI reached inside for. The
        fallback is the schema's default rather than blank: a setting the file omits is
        still what the install is running on, and answering "" would say the opposite.
        """
        from common.config_access import cfg_get
        entry = config_schema.option(section, key)
        raw = cfg_get(self, section, key, fallback=entry.default if entry else "")
        return self._typed(section, key, raw)

    def set_value(self, section: str, key: str, value: Any) -> None:
        """Stage one setting under its canonical name. `save()` writes the file."""
        section = config_schema.canonical_section(section)
        key = config_schema.canonical(section, key)
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, self._as_text(value))

    def save(self) -> None:
        # The first save after reading an ini keeps a copy and leaves the original alone:
        # a downgrade needs the file the older build reads.
        if self._converted_from_ini and os.path.exists(self.ini_path):
            logger.info("Kept the pre-JSON settings at %s", copy_aside(str(self.ini_path)))
            self._converted_from_ini = False
        settings = _nest({section: {key: self._typed(section, key, value)
                                    for key, value in self.config.items(section)}
                          for section in self.config.sections()})
        # Never stamp a newer file down to what this build writes - that number belongs to
        # whichever VPinFE wrote it, and claiming it would say we understood the file.
        payload = {SCHEMA_KEY: max(getattr(self, '_schema', CONFIG_SCHEMA), CONFIG_SCHEMA),
                   SETTINGS_KEY: settings}
        write_atomic(self.json_path,
                     lambda handle: json.dump(payload, handle, indent=2, ensure_ascii=False))

    def format_defaults(self) -> None:
        for section, defaults in self.defaults.items():
            self.config.add_section(section)
            for key, value in defaults.items():
                if not self.config.has_option(section, key):  # Only set if not present
                    self.config.set(section, key, value)
