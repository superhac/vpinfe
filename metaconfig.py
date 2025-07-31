import configparser
import os

class MetaConfig:

    sections = {}

    def __init__(self, configfilepath):

        self.defaults = {}
        self.config = configparser.ConfigParser(defaults=self.defaults)
        
        # check if the file exists
        if os.path.exists(configfilepath):
            self.config.read(configfilepath)
        else: # must be a new file we are going to write
            pass
            #raise FileNotFoundError(f"The config file '{configfilepath}' was not found.")
        
        self.configFilePath = configfilepath
     
        
    def writeConfigMeta(self, configdata):
        config = {}
        config['VPSdb'] = {}
        config['VPXFile'] = {}
        
        # Remove all sections.. may not need this but if you want to remove keys already in file you have to!
        #for section in list(self.config.sections()):
            #self.config.remove_section(section)
        
        #print(configdata)
        
        try:
            # VPSdb
            config['VPSdb']['id'] = configdata.get('vpsdata', {}).get('id', '')
            config['VPSdb']['name'] = configdata.get('vpsdata', {}).get('name', '')
            config['VPSdb']['type'] = configdata.get('vpsdata', {}).get('type', '')
            config['VPSdb']['manufacturer'] = configdata.get('vpsdata', {}).get('manufacturer', '')
            config['VPSdb']['year'] = configdata.get('vpsdata', {}).get('year', '')
            config['VPSdb']['theme'] = configdata.get('vpsdata', {}).get('theme', '')
            
            print( config['VPSdb']['type'])
            
            
            # vpx file data
            config['VPXFile']['filename'] = configdata['vpxdata']['filename']
            config['VPXFile']['filehash'] = configdata['vpxdata']['fileHash']
            config['VPXFile']['version'] = configdata['vpxdata']['tableVersion']
            config['VPXFile']['author'] = configdata['vpxdata']['authorName']
            config['VPXFile']['releaseDate'] = configdata['vpxdata']['releaseDate']
            config['VPXFile']['blurb'] = self.strip_all_newlines(configdata['vpxdata']['tableBlurb'])
            #config['VPXFile']['rules'] = configdata['vpxdata']['tableRules']
            config['VPXFile']['saveDate'] = configdata['vpxdata']['tableSaveDate']
            config['VPXFile']['saveRev'] = configdata['vpxdata']['tableSaveRev']
            config['VPXFile']['manufacturer'] = configdata['vpxdata']['companyName']
            config['VPXFile']['year'] = configdata['vpxdata']['companyYear']
            config['VPXFile']['type'] = configdata['vpxdata']['tableType']
            #config['VPXFile']['description'] = configdata['vpxdata']['tableDescription']
            config['VPXFile']['vbsHash'] = configdata['vpxdata']['codeSha256Hash']
            config['VPXFile']['rom'] = configdata['vpxdata']['rom']
            config['VPXFile']['detectNfozzy'] = configdata['vpxdata']['detectNfozzy']
            config['VPXFile']['detectFleep'] = configdata['vpxdata']['detectFleep']
            config['VPXFile']['detectSSF'] = configdata['vpxdata']['detectSSF']
            config['VPXFile']['detectLUT'] = configdata['vpxdata']['detectLut']
            config['VPXFile']['detectScorebit'] = configdata['vpxdata']['detectScorebit']
            config['VPXFile']['detectFastflips'] = configdata['vpxdata']['detectFastflips']
            config['VPXFile']['detectFlex'] = configdata['vpxdata']['detectFlex']
        except AttributeError:
            print("Attribute error.. in meta")
            
        
         
        # write it
        self.config.read_dict(config)
        # Write the configuration to a file
        with open(self.configFilePath, 'w') as configfile:
            self.config.write(configfile)

    def writeConfig(self):
         with open(self.configFilePath, 'w') as configfile:
            self.config.write(configfile)

    def getConfig(self):
        return self.config
    
    def getDictConfig(self):
        return {section: dict(self.config[section]) for section in self.config.sections()}
    
    def strip_all_newlines(self,text):
        #Strips all newlines (Unix and MS-DOS) from a string.
        text = text.replace('\r\n', '')  # Remove MS-DOS newlines
        text = text.replace('\n', '')    # Remove Unix newlines
        return text
    
    def actionDeletePinmameNVram(self):
        try:
            basepathfolder = os.path.dirname(self.configFilePath)
            nvramPath = basepathfolder + "/pinmame/nvram/" + self.config['VPXFile']['rom'] + ".nv"
            if self.config['Pinmame']['deleteNVramOnClose'] == "true":
                if os.path.exists(nvramPath):
                    os.remove(nvramPath)
                    print(f"File '{nvramPath}' deleted successfully.")
                else:
                    print(f"File '{nvramPath}' does not exist.")
        except KeyError:  # theres no pinmame setting for this action
            pass
        
    def addFavorite(self):
        self.config['VPinFE']['favorite'] = 'true'
        self.writeConfig(self)
    
    def removeFavorite(self):
        self.config['VPinFE']['favorite'] = 'false'
        self.writeConfig(self)