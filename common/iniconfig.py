import configparser
import os

class IniConfig:

	def __init__(self, configfilepath):
		
		self.defaults = {
			'Displays': {
				'bgscreenid': '',
				'dmdscreenid': '',
				'tablescreenid': '0',
				'tableorientation': 'landscape',
				'tablerotation': '0',
				'cabmode': 'false'
			},
			'Settings': {
				'vpxbinpath': '',
				'tablerootdir': '',
				'vpxinipath': '',
				'theme': 'carousel-desktop',
				'startup_collection': '',
				'autoupdatemediaonstartup': 'false',
				},
			'Input': {
				'joyleft': '',
				'joyright': '',
				'joyup': '',
				'joydown': '',
				'joyselect': '',
				'joymenu': '',
				'joyback': '',
				'joyexit': '',
				'joycollectionmenu': '',
				},
			'Logger': {
				'level': 'info',
				'console': '1',
				'file': '',
				},
				'Media': {
					'tabletype': 'table',
					'tableresolution': '4k',
					'tablevideoresolution': '1k',
					'defaultmissingmediaimg': '',
					'thumbcachemaxmb': '500',
					},
			'VPSdb': {'last': ''},
			'Network': {
				'themeassetsport': '8000',
				'manageruiport': '8001',
				},
			'DOF': {
				'enabledof': 'false',
				'dofconfigtoolapikey': '',
				},
			'Mobile': {
				'deviceip': '',
				'deviceport': '2112',
				'chunksize': '1048576',
				},
		}

		self.config = configparser.ConfigParser()
		self.configfilepath = configfilepath

		# check if the file exists
		self.is_new = False
		if not os.path.exists(configfilepath):
				print(f"Generating a default 'vpinfe.ini' at: {configfilepath}")
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
