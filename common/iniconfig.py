import configparser
import logging
import os
import secrets
import string


from common import config_schema
from common.deprecations import announce

logger = logging.getLogger("vpinfe.common.iniconfig")

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

class IniConfig:

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
		self.configfilepath = configfilepath

		# check if the file exists
		self.is_new = False
		if not os.path.exists(configfilepath):
				logger.info("Generating a default 'vpinfe.ini' at: %s", configfilepath)
				self.is_new = True
				self.formatDefaults()
				self.save()

		self.config.read(configfilepath)
		changed = False

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

	def save(self):
		with open(self.configfilepath, 'w') as configfile:
			self.config.write(configfile)
	
	def formatDefaults(self):
		for section, defaults in self.defaults.items():
			self.config.add_section(section)
			for key, value in defaults.items():
				if not self.config.has_option(section, key):  # Only set if not present
					self.config.set(section, key, value)
