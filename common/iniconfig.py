import configparser
import os

class IniConfig:

	def __init__(self, configfilepath):
		
		self.defaults = {
			'Displays': {'bgscreenid': '', 'dmdscreenid': '', 'tablescreenid': '0' },
			'Settings': {
				'vpxbinpath': '',
				'tablerootdir': '',
				'vpxinipath': '',
				'theme': 'carousel-desktop',
				'startup_collection': '',
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
				'defaultmissingmediaimg': '',
				},
			'VPSdb': {'last': ''},
			'Network': {
				'themeassetsport': '8000',
				'manageruiport': '8001',
				},
		}

		self.config = configparser.ConfigParser()
		self.configfilepath = configfilepath

		# check if the file exists
		if not os.path.exists(configfilepath):
				print(f"Generating a default 'vpinfe.ini' at: {configfilepath}")
				self.formatDefaults()
				self.save()
				print(f"Please edit the config file and restart the application.")
				raise FileNotFoundError(f"Config file created at '{configfilepath}'. Please configure it and restart.")

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