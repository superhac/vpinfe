"""VPinFE's settings, stored as JSON and read from an ini once.

The file is `vpinfe.json`; a `vpinfe.ini` beside it is read on the first run that finds
one, converted, and kept. Every other config file VPinFE owns is already JSON, and this
was the only one that was both hand-edited and machine-written - which is exactly why it
was the only one whose comments `configparser.write()` destroyed.

In memory it is still a ConfigParser, so nothing above this module changed. What is on
disk carries real booleans and integers, and a schema version.
"""

import configparser
import json
import logging
import os
import secrets
import string
from pathlib import Path

from common import config_schema
from common.deprecations import announce
from common.games.info_migration import copy_aside, write_atomic
from common.values import is_truthy

logger = logging.getLogger("vpinfe.common.config_store")

SCHEMA_KEY = "schema"
SETTINGS_KEY = "settings"

# 1 is the first JSON version. Schema 0 is the ini, which has no version at all - it is
# recognized by being an ini rather than by anything written in it.
CURRENT_SCHEMA = 1

# (from, to, key) for options that changed section. Applied on every read, so an ini
# written by any earlier build lands in the right place.
_MOVED_OPTIONS = (
	('Settings', 'Displays', 'cabmode'),
	('Settings', 'DOF', 'enabledof'),
	('Displays', 'Settings', 'splashscreen'),
)


def _generate_machine_id(length: int = 64) -> str:
	alphabet = string.ascii_letters + string.digits
	return ''.join(secrets.choice(alphabet) for _ in range(length))


# (section, old key, new key) - see the migration in _migrate below.
_RENAMED_KEYS = (
	('Displays', 'tablescreenid', 'playfieldscreenid'),
	('Displays', 'tableorientation', 'playfieldorientation'),
	('Displays', 'tablerotation', 'playfieldrotation'),
	('Settings', 'tablerootdir', 'gamerootdir'),
	('Settings', 'restorelasttable', 'restorelastgame'),
	('Media', 'tabletype', 'playfieldvariant'),
	('Media', 'tableresolution', 'playfieldresolution'),
	('Media', 'tablevideoresolution', 'playfieldvideoresolution'),
	('Media', 'tablemediapriority', 'playfieldmediapriority'),
	('State', 'lasttable', 'lastgame'),
)

class ConfigStore:

	def _move_option(self, old_section, new_section, key) -> bool:
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

	def __init__(self, configfilepath):
		
		self.defaults = config_schema.defaults()

		self.config = configparser.ConfigParser()
		# Callers pass whichever name they know; both are derived so none had to change.
		base = Path(configfilepath)
		self.json_path = base.with_suffix('.json')
		self.ini_path = base.with_suffix('.ini')
		self.configfilepath = str(self.json_path)
		self._schema = CURRENT_SCHEMA
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
			self.formatDefaults()
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
		if self.config.has_option('Logger', 'file'):
			self.config.remove_option('Logger', 'file')
			changed = True

		# Normalize blank theme values back to the configured default.
		current_theme = self.config.get('Settings', 'theme', fallback='').strip()
		if not current_theme:
			self.config.set('Settings', 'theme', self.defaults['Settings']['theme'])
			changed = True

		# Migrate misspelled vpinplay.initals to vpinplay.initials if present.
		if self.config.has_option('vpinplay', 'initals'):
			legacy_initials = self.config.get('vpinplay', 'initals', fallback='').strip()
			current_initials = self.config.get('vpinplay', 'initials', fallback='').strip()
			if legacy_initials and not current_initials:
				self.config.set('vpinplay', 'initials', legacy_initials)
			self.config.remove_option('vpinplay', 'initals')
			changed = True

		# Auto-generate vpinplay.machineid when not set.
		current_machine_id = self.config.get('vpinplay', 'machineid', fallback='').strip()
		if not current_machine_id:
			self.config.set('vpinplay', 'machineid', _generate_machine_id())
			changed = True

		if changed:
			self.save()

	def _typed(self, section: str, key: str, raw: str):
		"""The value as JSON should hold it. Unknown keys stay strings.

		An empty string stays empty rather than becoming 0 or null: several int settings
		use blank to mean "no window on this one", and that is not the same as zero.
		"""
		entry = config_schema.option(section, key)
		text = '' if raw is None else str(raw)
		if entry is None or text.strip() == '':
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
	def _as_text(value) -> str:
		"""Back to what a ConfigParser holds, so nothing above this module changes."""
		if isinstance(value, bool):
			return 'true' if value else 'false'
		return '' if value is None else str(value)

	def _load_json(self) -> None:
		with open(self.json_path, encoding='utf-8') as handle:
			payload = json.load(handle) or {}
		self._schema = int(payload.get(SCHEMA_KEY, CURRENT_SCHEMA) or CURRENT_SCHEMA)
		for section, values in (payload.get(SETTINGS_KEY) or {}).items():
			if not self.config.has_section(section):
				self.config.add_section(section)
			for key, value in (values or {}).items():
				self.config.set(section, key, self._as_text(value))

	def save(self):
		# The first save after reading an ini keeps a copy and leaves the original alone:
		# a downgrade needs the file the older build reads.
		if self._converted_from_ini and os.path.exists(self.ini_path):
			logger.info("Kept the pre-JSON settings at %s", copy_aside(str(self.ini_path)))
			self._converted_from_ini = False
		settings = {section: {key: self._typed(section, key, value)
		                      for key, value in self.config.items(section)}
		            for section in self.config.sections()}
		# Never stamp a newer file down to what this build writes - that number belongs to
		# whichever VPinFE wrote it, and claiming it would say we understood the file.
		payload = {SCHEMA_KEY: max(getattr(self, '_schema', CURRENT_SCHEMA), CURRENT_SCHEMA),
		           SETTINGS_KEY: settings}
		write_atomic(self.json_path,
		             lambda handle: json.dump(payload, handle, indent=2, ensure_ascii=False))
	
	def formatDefaults(self):
		for section, defaults in self.defaults.items():
			self.config.add_section(section)
			for key, value in defaults.items():
				if not self.config.has_option(section, key):  # Only set if not present
					self.config.set(section, key, value)
