import sys
from pathlib import Path
from screeninfo import get_monitors
from table import Table
import json
import time
import webview
import subprocess

class API:
    
    def __init__(self):
        self.tables = None
        self.webview_windows = None
        self.iniConfig = None
        self.myWindow = [] # this holds this instances webview window.  In array because of introspection of the window object
        self.tableDictData = None
    
    def sleep(self):
        print("entering sleep")
        time.sleep(2)  # Placeholder for sleep function, if needed
        print("exiting sleep")
        return "sleep"
    
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
        if self.tableDictData:
            return self.tableDictData
        tables = []
        if self.tables:
            for table in self.tables:
                table_data = {
                    'tableDirName': table.tableDirName,
                    'fullPathTable': table.fullPathTable,
                    'fullPathVPXfile': table.fullPathVPXfile,
                    'BGImagePath' : table.BGImagePath,
                    'DMDImagePath' : table.DMDImagePath,
                    'TableImagePath' : table.TableImagePath,
                    'WheelImagePath' : table.WheelImagePath,
                    'pupPackExists': table.pupPackExists,
                    'altColorExists': table.altColorExists,
                    'altSoundExists': table.altSoundExists,
                    'meta': {section: dict(table.metaConfig[section]) for section in table.metaConfig.sections()}
                }
                tables.append(table_data)
            self.tableDictData = json.dumps(tables)
        return self.tableDictData
    
    def get_theme_name(self):
        return self.iniConfig.config['Settings'].get('theme', 'default')
    
    def load_page(self, page_path):
        full_path = Path(__file__).parent / 'web' / page_path
        print("Loading:", full_path)
        self.myWindow[0].load_url(full_path.resolve().as_uri())
    
    def get_theme_index_page(self):
        theme_name = self.get_theme_name()
        theme_path = f'theme/{theme_name}'
        filename = f'index_{self.get_my_window_name()}.html'

        # Just return the relative path
        relative_path = f"{theme_path}/{filename}"
        print("Redirect path:", relative_path)
        return relative_path
        
    def console_out(self, output):
        print("Console Output:", output)
        return output
    
    def finish_setup(self): # incase we need to do anything after the windows are created and instanc evars are loaded.
            pass
        
    def get_joymaping(self):
        return {
            'joyleft': self.iniConfig.config['Settings'].get('joyleft', '0'),
            'joyright': self.iniConfig.config['Settings'].get('joyright', '0'),
            'joyselect': self.iniConfig.config['Settings'].get('joyselect', '0'),
            'joymenu': self.iniConfig.config['Settings'].get('joymenu', '0'),
            'joyback': self.iniConfig.config['Settings'].get('joyback', '0'),
            'joyexit': self.iniConfig.config['Settings'].get('joyexit', '0')
        }
        
    def launch_table(self, index):
        table = self.tables[index]
        vpx = table.fullPathVPXfile
        vpxbin = self.iniConfig.config['Settings'].get('vpxbinpath', '')
        cmd = [vpxbin, "-play", vpx]
        print("Launching: ", cmd)
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL)
        process.wait()
        self.send_event_all_windows_incself({"type": "TableLaunchComplete"})

    def get_html(self, path):
        with open(path, "r") as f:
            return f.read()
        
    def get_popup(self):
        return self.get_html()