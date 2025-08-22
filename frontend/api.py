import sys
from pathlib import Path
from screeninfo import get_monitors
from common.table import Table
import json
import time
import webview
import subprocess
from common.tableparser import TableParser
from common.vpxcollections import VPXCollections

class API:
    
    def __init__(self, iniConfig):
        self.webview_windows = None
        self.iniConfig = iniConfig
        self.allTables = TableParser(self.iniConfig.config['Settings']['tablerootdir']).getAllTables();
        self.filteredTables = self.allTables
        self.myWindow = [] # this holds this instances webview window.  In array because of introspection of the window object
        self.jsTableDictData = None

    ####################
    ## Private Functions
    ####################
    
    def _finish_setup(self): # incase we need to do anything after the windows are created and instanc evars are loaded.
        pass
    
    ###################
    ## Public Functions
    ###################
    
    def get_my_window_name(self):
        for window_name, window, api in self.webview_windows:
            if self.myWindow[0].uid == window.uid:
                return f'{window_name}'
        return "No window name found for this API instance"

    def close_app(self):
        print("Called by", self.myWindow[0].uid)
        for window_name, window, api in self.webview_windows:
            print("name: ", window.uid)
            window.destroy()
        sys.exit(0)
    
    def get_monitors(self):
        print("get_monitors called")
        monitors = get_monitors()
        # Return a list of dicts with relevant info
        return [{
            'name': f'Monitor {i}',
            'x': m.x,
            'y': m.y,
            'width': m.width,
            'height': m.height
        } for i, m in enumerate(monitors)]
        
    def send_event_all_windows(self, message):
        msg_json = json.dumps(message)  # safely convert Python dict to JS object literal
        for window_name, window, api in self.webview_windows:
            if self.myWindow[0].uid != window.uid:
                window.evaluate_js(f'receiveEvent({msg_json})')
    
    def send_event(self, window_name, message):
        msg_json = json.dumps(message)  # safely convert Python dict to JS object literal
        for win_name, window, api in self.webview_windows:
            if window_name == win_name:
                 window.evaluate_js(f'receiveEvent({msg_json})')
                 
    def send_event_all_windows_incself(self, message):
        msg_json = json.dumps(message)  # safely convert Python dict to JS object literal
        for window_name, window, api in self.webview_windows:
                window.evaluate_js(f'receiveEvent({msg_json})')

    def get_tables(self):
        tables = []
        for table in self.filteredTables:
            table_data = {
                'tableDirName': table.tableDirName,
                'fullPathTable': table.fullPathTable,
                'fullPathVPXfile': table.fullPathVPXfile,
                'BGImagePath' : table.BGImagePath,
                'DMDImagePath' : table.DMDImagePath,
                'TableImagePath' : table.TableImagePath,
                'WheelImagePath' : table.WheelImagePath,
                'CabImagePath' : table.CabImagePath,
                'pupPackExists': table.pupPackExists,
                'altColorExists': table.altColorExists,
                'altSoundExists': table.altSoundExists,
                'meta': {section: dict(table.metaConfig[section]) for section in table.metaConfig.sections()}
            }
            tables.append(table_data)
        self.jsTableDictData = json.dumps(tables)
        return self.jsTableDictData
    
    def get_collections(self):
        c = VPXCollections(Path(__file__).parent.parent / "collections.ini")
        return c.get_collections_name()
    
    def set_tables_by_collection(self, collection):
        c = VPXCollections(Path(__file__).parent.parent / "collections.ini")
        self.filteredTables = c.filter_tables(self.allTables, collection)      
    
    def console_out(self, output):
        print(f'Win: {self.myWindow[0].uid} - {output}')
        return output
           
    def get_joymaping(self):
        return {
            'joyleft': self.iniConfig.config['Settings'].get('joyleft', '0'),
            'joyright': self.iniConfig.config['Settings'].get('joyright', '0'),
            'joyup': self.iniConfig.config['Settings'].get('joyup', '0'),
            'joydown': self.iniConfig.config['Settings'].get('joydown', '0'),
            'joyselect': self.iniConfig.config['Settings'].get('joyselect', '0'),
            'joymenu': self.iniConfig.config['Settings'].get('joymenu', '0'),
            'joyback': self.iniConfig.config['Settings'].get('joyback', '0'),
            'joyexit': self.iniConfig.config['Settings'].get('joyexit', '0')
        }
        
    def launch_table(self, index):
        table = self.filteredTables[index]
        vpx = table.fullPathVPXfile
        vpxbin = self.iniConfig.config['Settings'].get('vpxbinpath', '')
        print("Launching: ", [vpxbin, "-play", vpx])
        cmd = [Path(vpxbin).expanduser(), "-play", vpx]
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL)
        process.wait()
        self.myWindow[0].show()
        self.send_event_all_windows_incself({"type": "TableLaunchComplete"})

    def get_theme_config(self):
        theme_name = self.get_theme_name()
        theme_path = f'web/theme/{theme_name}/config.json'
        print("theme config path: ", theme_path)
        try:
            with open(theme_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception as e:
            return None
    
    ###################
    ### For splash page
    ###################
    
    def get_theme_name(self):
        return self.iniConfig.config['Settings'].get('theme', 'default')
    
    def get_theme_index_page(self):
        theme_name = self.get_theme_name()
        theme_path = f'theme/{theme_name}/'
        url = theme_path +f'index_{self.get_my_window_name()}.html'
        print("url: " + url)
        return url