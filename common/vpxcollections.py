# collections.py
import configparser
from pathlib import Path

class VPXCollections:
    def __init__(self, ini_path: str):
        """Load and parse the ini file."""
        self.ini_path = Path(ini_path)
        self.config = configparser.ConfigParser()
        if self.ini_path.exists():
            self.config.read(self.ini_path)
            print("Found collections file...")

    def reload(self):
        """Reload the ini file from disk (discard unsaved changes)."""
        self.config = configparser.ConfigParser()
        if self.ini_path.exists():
            self.config.read(self.ini_path)

    def get_collections_name(self):
        """Return a list of section names."""
        return self.config.sections()

    def get_vpsids(self, section: str):
        """Return list of vpsids for a given section."""
        if section not in self.config:
            raise KeyError(f"Section '{section}' not found")
        raw_value = self.config[section].get("vpsids", "")
        return [v.strip() for v in raw_value.split(",") if v.strip()]

    def get_all(self):
        """Return dict of section -> list of vpsids."""
        return {s: self.get_vpsids(s) for s in self.get_collections_name()}

    def add_collection(self, section: str, vpsids=None):
        """Add a new collection (section)."""
        if self.config.has_section(section):
            raise ValueError(f"Section '{section}' already exists")
        self.config.add_section(section)
        if vpsids:
            self.config[section]["vpsids"] = ",".join(vpsids)
        else:
            self.config[section]["vpsids"] = ""

    def delete_collection(self, section: str):
        """Delete a collection (section)."""
        if not self.config.remove_section(section):
            raise KeyError(f"Section '{section}' not found")

    def add_vpsid(self, section: str, vpsid: str):
        """Add a vpsid to a section (ignores duplicates)."""
        vpsids = set(self.get_vpsids(section))
        vpsids.add(vpsid.strip())
        self.config[section]["vpsids"] = ",".join(sorted(vpsids))

    def remove_vpsid(self, section: str, vpsid: str):
        """Remove a vpsid from a section."""
        vpsids = self.get_vpsids(section)
        if vpsid not in vpsids:
            raise ValueError(f"vpsid '{vpsid}' not found in section '{section}'")
        vpsids.remove(vpsid)
        self.config[section]["vpsids"] = ",".join(vpsids)

    def save(self):
        """Write current state back to file."""
        with self.ini_path.open("w") as f:
            self.config.write(f)
            
    def filter_tables(self, tables, collection):
        filterList=[]
        filterIDs = self.get_vpsids(collection)
        for fid in filterIDs:
            print(fid)
            for table in tables:
                print(table.tableDirName)
                print("checking:", table.metaConfig.get('VPSdb', 'id', fallback='none'), "Against:", fid)
                if table.metaConfig.get('VPSdb', 'id', fallback='none') == fid:
                    filterList.append(table)
                    print("found", table.metaConfig.get('VPSdb', fid, fallback='none'))
        return filterList
    
# Debug
if __name__ == "__main__":
    c = VPXCollections("collections.ini")
    #tables = TableParser("vinfe.ini").getAllTables();

    print("Sections:", c.get_collections_name)
    print("All:", c.get_all())
    print(c.get_vpsids('Favorites'))
    
    #mylist = c.filter_tables(tables, 'Favorites')
    #print(mylist)
    # Example changes
    #c.add_collection("NewCollection", ["abc123", "xyz789"])
    #c.add_vpsid("Favorites", "NEWID")
    #c.remove_vpsid("Competition", "XQqwrauH")
    #c.save()

    # Force reload from disk
    c.reload()
    print("After reload:", c.get_all())
