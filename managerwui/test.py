from common.tableparser import TableParser
from common.iniconfig import IniConfig

def test():
    iniconfig = IniConfig("./vpinfe.ini")
    tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables()