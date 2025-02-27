import configparser
import os

class Config:

	sections = {}

	def __init__(self, configfilepath):

		# check if the file exists
		if not os.path.exists(configfilepath):
			raise FileNotFoundError(f"The config file '{configfilepath}' was not found.")
		
		self.defaults = {}
		self.config = configparser.ConfigParser(defaults=self.defaults)
		self.config.read(configfilepath)
		self.readAllKeys()


	def readAllKeys(self):
		for section in self.config.sections():
			entries = {}
			#print(f"[{section}]")
			for key, value in self.config[section].items():
				entries[key] = value
				#print(f"{key} = {value}")
			Config.sections[section] = entries



