import configparser
import logging
import os
import secrets
import string


logger = logging.getLogger("vpinfe.common.iniconfig")


def _generate_machine_id(length: int = 64) -> str:
	alphabet = string.ascii_letters + string.digits
	return ''.join(secrets.choice(alphabet) for _ in range(length))

class IniConfig:

	def __init__(self, configfilepath):
		
		self.defaults = {
			'Displays': {
				'bgscreenid': '',
				'dmdscreenid': '',
				'bgwindowoverride': '',
				'dmdwindowoverride': '',
				'tablescreenid': '0',
				'tableorientation': 'landscape',
				'tablerotation': '0',
				'cabmode': 'false'
			},
			'Settings': {
				'vpxbinpath': '',
				'vpxlaunchenv': '',
				'globalinioverride': '',
				'globaltableinioverrideenabled': 'false',
				'globaltableinioverridemask': '',
				'tablerootdir': '',
				'vpxinipath': '',
				'theme': 'Revolution',
				'startup_collection': '',
				'autoupdatemediaonstartup': 'false',
				'splashscreen': 'true',
				'muteaudio': 'false',
				'MMhideQuitButton': 'false',
				},
			'Input': {
				'joyleft': '',
				'keyleft': 'ArrowLeft,ShiftLeft',
				'joyright': '',
				'keyright': 'ArrowRight,ShiftRight',
				'joyup': '',
				'keyup': 'ArrowUp',
				'joydown': '',
				'keydown': 'ArrowDown',
				'joypageup': '',
				'keypageup': 'PageUp',
				'joypagedown': '',
				'keypagedown': 'PageDown',
				'joyselect': '',
				'keyselect': 'Enter',
				'joymenu': '',
				'keymenu': 'm',
				'joyback': '',
				'keyback': 'b',
				'joytutorial': '',
				'keytutorial': 't',
				'joyexit': '',
				'keyexit': 'Escape,q',
				'joycollectionmenu': '',
				'keycollectionmenu': 'c',
				},
			'Logger': {
				'level': 'debug',
				'console': 'true',
				},
				'Media': {
					'tabletype': 'table',
					'tableresolution': '4k',
					'tablevideoresolution': '1k',
					'defaultmissingmediaimg': '',
					'thumbcachemaxmb': '500',
					},
			'VPSdb': {'last': ''},
			'pinmame-score-parser': {
				'romsupdatesha': '',
				},
			'Network': {
				'themeassetsport': '8000',
				'manageruiport': '8001',
				},
			'DOF': {
				'enabledof': 'false',
				'dofconfigtoolapikey': '',
				},
			'libdmdutil': {
				'enabled': 'false',
				'pin2dmdenabled': 'false',
				'pixelcadedevice': '',
				'zedmddevice': '',
				'zedmdwifiaddr': '',
				},
			'Mobile': {
				'deviceip': '',
				'deviceport': '2112',
				'chunksize': '1048576',
				'renamemasktodefaultini': 'false',
				'renamemasktodefaultinimask': '',
				},
				'vpinplay': {
					'synconexit': 'false',
					'apiendpoint': 'https://api.vpinplay.com:8888',
					'userid': '',
					'initials': '',
					'machineid': '',
					},
		}

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
		# Add any missing default options
		changed = False
		for section, defaults in self.defaults.items():
			if not self.config.has_section(section):
				self.config.add_section(section)
				changed = True
			for key, value in defaults.items():
				if not self.config.has_option(section, key):
					self.config.set(section, key, value)
					changed = True

		# Migrate cabmode from [Settings] to [Displays] if present.
		if self.config.has_option('Settings', 'cabmode'):
			if not self.config.has_option('Displays', 'cabmode'):
				self.config.set('Displays', 'cabmode', self.config.get('Settings', 'cabmode'))
			self.config.remove_option('Settings', 'cabmode')
			changed = True

		# Migrate enabledof from [Settings] to [DOF] if present.
		if self.config.has_option('Settings', 'enabledof'):
			if not self.config.has_option('DOF', 'enabledof'):
				self.config.set('DOF', 'enabledof', self.config.get('Settings', 'enabledof'))
			self.config.remove_option('Settings', 'enabledof')
			changed = True

		# Migrate splashscreen from [Displays] to [Settings] if present.
		if self.config.has_option('Displays', 'splashscreen'):
			if not self.config.has_option('Settings', 'splashscreen'):
				self.config.set('Settings', 'splashscreen', self.config.get('Displays', 'splashscreen'))
			self.config.remove_option('Displays', 'splashscreen')
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
