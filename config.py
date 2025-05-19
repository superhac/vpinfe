import configparser
import os
import sys

from log import get_logger

class Config:
	logger = None

	def __init__(self, configfilepath):
		global logger
		logger = get_logger()

		self.defaults = {
			'Displays': {'bgscreenid': '', 'dmdscreenid': '', 'tablescreenid': '', "hudscreenid": '',  'tablerotangle': '0', 'hudrotangle': '0', 'backgroundcolor': '#000000'},
			'Logger': { 'level': 'info', 'console': '1', 'file': ''},
			'Media': {"tabletype": '', 'tableresolution': '4k'},
			'Settings': {
				'vpxbinpath': '', 
				'tablerootdir': '',
				'defaultfilter': '', # abc, favorites, em, ss, pm  
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
				logger.info(f"Generating a default ini file {configfilepath}")
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
