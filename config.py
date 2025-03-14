import configparser
import os
import sys

class Config:

	def __init__(self, configfilepath):
     
		self.defaults = {
			'Displays': {'bgscreenid': '', 'dmdscreenid': '', 'tablescreenid': ''},
			'Settings': {
				'vpxbinpath': '', 
				'tablerootdir': '', 
				'joyleft': '',
				'joyright': '',
				'joyselect': '',
				'joymenu': '',
				'joyback': '',
				'joyexit': '',
				},
			'VPSdb': {'last': ''},
		}

		self.config = configparser.ConfigParser()
		self.configfilepath = configfilepath

		# check if the file exists
		if not os.path.exists(configfilepath):
				print("Generating a default 'vpinfe.ini' in CWD.")
				self.formatDefaults()
				self.save()
				raise FileNotFoundError(f"The config file '{configfilepath}' was not found.")

		self.config.read(configfilepath)

	def save(self):
		with open(self.configfilepath, 'w') as configfile:
			self.config.write(configfile)
	
	def formatDefaults(self):
		for section, defaults in self.defaults.items():
			self.config.add_section(section)
			for key, value in defaults.items():
				if not self.config.has_option(section, key):  # Only set if not present
					self.config.set(section, key, value)