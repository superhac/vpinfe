import configparser
import os

class MetaConfig:

    sections = {}

    def __init__(self, configfilepath):

        # check if the file exists
        if not os.path.exists(configfilepath):
            pass
            #raise FileNotFoundError(f"The config file '{configfilepath}' was not found.")
        self.configFilePath = configfilepath
        self.defaults = {}
        self.config = configparser.ConfigParser(defaults=self.defaults)
        self.config.read(configfilepath)
        
    def writeConfig(self, configdata):
        config = {}
        config['VPSdb'] = {}
        config['VPXFile'] = {}
        
        # Remove all sections.. may not need this but if you want to remove keys already in file you have to!
        for section in list(self.config.sections()):
            self.config.remove_section(section)
        
        #print(configdata)
        
        # VPSdb
        try:
            config['VPSdb']['id'] = configdata['vpsdata']['id']
            config['VPSdb']['name'] = configdata['vpsdata']['name']
            config['VPSdb']['type'] = configdata['vpsdata']['type']
            config['VPSdb']['manufacturer'] = configdata['vpsdata']['manufacturer']
            config['VPSdb']['year'] = configdata['vpsdata']['year']
            config['VPSdb']['theme'] = configdata['vpsdata']['theme']
        except TypeError as e: # it did not get a vpsdb entry
            pass
        
        # vpx file data
        config['VPXFile']['filename'] = configdata['vpxdata']['filename']
        config['VPXFile']['filehash'] = configdata['vpxdata']['fileHash']
        config['VPXFile']['version'] = configdata['vpxdata']['tableVersion']
        config['VPXFile']['author'] = configdata['vpxdata']['authorName']
        config['VPXFile']['releaseDate'] = configdata['vpxdata']['releaseDate']
        config['VPXFile']['blurb'] = configdata['vpxdata']['tableBlurb']
        #config['VPXFile']['rules'] = configdata['vpxdata']['tableRules']
        config['VPXFile']['saveDate'] = configdata['vpxdata']['tableSaveDate']
        config['VPXFile']['saveRev'] = configdata['vpxdata']['tableSaveRev']
        config['VPXFile']['manufacturer'] = configdata['vpxdata']['companyName']
        config['VPXFile']['year'] = configdata['vpxdata']['companyYear']
        config['VPXFile']['type'] = configdata['vpxdata']['tableType']
        #config['VPXFile']['description'] = configdata['vpxdata']['tableDescription']
        config['VPXFile']['vbsHash'] = configdata['vpxdata']['codeSha256Hash']
        config['VPXFile']['rom'] = configdata['vpxdata']['rom']
        
        # write it
        self.config.read_dict(config)
        # Write the configuration to a file
        with open(self.configFilePath, 'w') as configfile:
            self.config.write(configfile)
