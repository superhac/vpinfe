import configparser
import os
import sys

from pinlog import get_logger

class Config:
	logger = None

	def __init__(self, configfilepath):
		global logger
		logger = get_logger()

		self.defaults = {
			'Displays': {'bgscreenid': '', 'dmdscreenid': '', 'tablescreenid': '0', "hudscreenid": '',  'messagesscreenid': '', 'tablerotangle': '0', 'hudrotangle': '0',
                'backgroundcolor': '#000000', 'windowmanager': 'gnome'},
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

	def get(self, section, option, default=None, type=str):
		try:
			value = self.config.get(section, option)
			converted_value = type(value)
			if not isinstance(converted_value, type):
				# When ini value is left blank and doesn't convert to the type we want
				return default
			return type(value)  # Convert to the specified type
		except (configparser.NoSectionError, configparser.NoOptionError):
			return default
		except ValueError:
			return default

	def get_int(self, section, option, default=None):
		return self.get(section, option, default, type=int)

	def get_float(self, section, option, default=None):
		return self.get(section, option, default, type=float)

	def get_bool(self, section, option, default=None):
		return self.get(section, option, default, type=bool)

	def get_string(self, section, option, default=None):
		string = self.get(section, option, default, type=str)
		return string if string != "" else default

