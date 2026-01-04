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
from common.tablelistfilters import TableListFilters
from platformdirs import user_config_dir

class API:
    
    def __init__(self, iniConfig):
        self.webview_windows = None
        self.iniConfig = iniConfig
        self.allTables = TableParser(self.iniConfig.config['Settings']['tablerootdir']).getAllTables()
        self.filteredTables = self.allTables
        self.myWindow = [] # this holds this instances webview window.  In array because of introspection of the window object
        self.jsTableDictData = None
        # Track current filter state
        self.current_filters = {
            'letter': None,
            'theme': None,
            'type': None,
            'manufacturer': None,
            'year': None
        }

    ####################
    ## Private Functions
    ####################
    
    def _finish_setup(self): # incase we need to do anything after the windows are created and instanc evars are loaded.
        pass
    
        
    ###################
    ## Public Functions
    ###################
    
    def playSound(self, sound):
       self.myWindow[0].evaluate_js(
            f"""
            PIXI.sound.play("{sound}");
            """
            )
       
    
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

    def get_tables(self, reset=False): # reset go back to full table list!
        if reset:
            self.filteredTables = self.allTables
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
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        c = VPXCollections(config_dir / "collections.ini")
        return c.get_collections_name()

    def set_tables_by_collection(self, collection):
        """Set filtered tables based on collection from collections.ini."""
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        c = VPXCollections(config_dir / "collections.ini")

        # Check if this is a filter-based collection
        if c.is_filter_based(collection):
            # Get the filter parameters and apply them
            filters = c.get_filters(collection)
            table_filters = TableListFilters(self.allTables)
            self.filteredTables = table_filters.apply_filters(
                letter=filters['letter'],
                theme=filters['theme'],
                table_type=filters['table_type'],
                manufacturer=filters['manufacturer'],
                year=filters['year']
            )
            # Update current filter state to match the collection
            self.current_filters = {
                'letter': filters['letter'],
                'theme': filters['theme'],
                'type': filters['table_type'],
                'manufacturer': filters['manufacturer'],
                'year': filters['year']
            }
        else:
            # VPS ID-based collection
            self.filteredTables = c.filter_tables(self.allTables, collection)
            # Reset filter state since we're using VPS IDs
            self.current_filters = {
                'letter': None,
                'theme': None,
                'type': None,
                'manufacturer': None,
                'year': None
            }

    def save_filter_collection(self, name, letter="All", theme="All", table_type="All", manufacturer="All", year="All"):
        """Save current filter settings as a named collection."""
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        c = VPXCollections(config_dir / "collections.ini")
        try:
            c.add_filter_collection(name, letter, theme, table_type, manufacturer, year)
            c.save()
            return {"success": True, "message": f"Filter collection '{name}' saved successfully"}
        except ValueError as e:
            return {"success": False, "message": str(e)}

    def get_current_filter_state(self):
        """Return current filter state for UI synchronization."""
        return self.current_filters

    def get_filter_letters(self):
        """Get available starting letters from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_letters()

    def get_filter_themes(self):
        """Get available themes from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_themes()

    def get_filter_types(self):
        """Get available table types from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_types()

    def get_filter_manufacturers(self):
        """Get available manufacturers from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_manufacturers()

    def get_filter_years(self):
        """Get available years from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_years()

    def apply_filters(self, letter=None, theme=None, table_type=None, manufacturer=None, year=None):
        """
        Apply VPSdb filters to the full table list.
        These filters work independently of collections.
        """
        # Update filter state
        if letter is not None:
            self.current_filters['letter'] = letter
        if theme is not None:
            self.current_filters['theme'] = theme
        if table_type is not None:
            self.current_filters['type'] = table_type
        if manufacturer is not None:
            self.current_filters['manufacturer'] = manufacturer
        if year is not None:
            self.current_filters['year'] = year

        print(f"Applying filters: letter={self.current_filters['letter']}, theme={self.current_filters['theme']}, type={self.current_filters['type']}, manufacturer={self.current_filters['manufacturer']}, year={self.current_filters['year']}")

        # Always start from the full table list
        filters = TableListFilters(self.allTables)
        self.filteredTables = filters.apply_filters(
            letter=self.current_filters['letter'],
            theme=self.current_filters['theme'],
            table_type=self.current_filters['type'],
            manufacturer=self.current_filters['manufacturer'],
            year=self.current_filters['year']
        )

        print(f"Filtered tables count: {len(self.filteredTables)}")

    def reset_filters(self):
        """Reset all VPSdb filters back to full table list."""
        self.filteredTables = self.allTables
        self.current_filters = {
            'letter': None,
            'theme': None,
            'manufacturer': None,
            'type': None,
            'year': None
        }

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
            'joyexit': self.iniConfig.config['Settings'].get('joyexit', '0'),
            'joycollectionmenu': self.iniConfig.config['Settings'].get('joycollectionmenu', '0')
        }
        
    def launch_table(self, index):
        table = self.filteredTables[index]
        vpx = table.fullPathVPXfile
        vpxbin = self.iniConfig.config['Settings'].get('vpxbinpath', '')
        print("Launching: ", [vpxbin, "-play", vpx])
        cmd = [Path(vpxbin).expanduser(), "-play", vpx]
        self.myWindow[0].toggle_fullscreen()
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL)
        process.wait()
        self.myWindow[0].toggle_fullscreen()
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
        theme_path = f'http://127.0.0.1:8000/web/theme/{theme_name}/'
        url = theme_path +f'index_{self.get_my_window_name()}.html'
        print("url: " + url)
        return url