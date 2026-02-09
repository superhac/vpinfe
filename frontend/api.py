import sys
import os
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
        self.allTables = TableParser(self.iniConfig.config['Settings']['tablerootdir'], self.iniConfig).getAllTables()
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
        # Track current sort state
        self.current_sort = 'Alpha'
        # Track current collection
        self.current_collection = None
        # Check for startup collection
        startup_collection = self.iniConfig.config['Settings'].get('startup_collection', '').strip()
        if startup_collection:
            try:
                self.set_tables_by_collection(startup_collection)
            except Exception as e:
                print(f"Warning: Could not load startup collection '{startup_collection}': {e}")

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
        #print("Called by", self.myWindow[0].uid)
        for window_name, window, api in self.webview_windows:
            print("name: ", window.uid)
            window.destroy()
        sys.exit(0)
    
    def get_monitors(self):
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
                # Send to main window
                window.evaluate_js(f'if (typeof receiveEvent === "function") receiveEvent({msg_json})')
                # Also send to mainmenu iframe if it exists
                window.evaluate_js(f'''
                    const menuFrame = document.getElementById("menu-frame");
                    if (menuFrame && menuFrame.contentWindow && typeof menuFrame.contentWindow.receiveEvent === "function") {{
                        menuFrame.contentWindow.receiveEvent({msg_json});
                    }}
                ''')

    def get_tables(self, reset=False):
        if reset:
            self.filteredTables = self.allTables

        tables = []
        for table in self.filteredTables:
            # Normalize metaConfig
            meta = {}
            if table.metaConfig:
                if isinstance(table.metaConfig, dict):
                    meta = table.metaConfig
                elif hasattr(table.metaConfig, "getConfig"):
                    meta = table.metaConfig.getConfig()

            # Ensure detection flags are booleans
            vpx = meta.get("VPXFile", {})
            for key in [
                "detectNfozzy", "detectFleep", "detectSSF",
                "detectLUT", "detectScorebit", "detectFastflips", "detectFlex"
            ]:
                if key in vpx:
                    val = vpx[key]
                    # Convert strings "true"/"false" to booleans
                    if isinstance(val, str):
                        vpx[key] = val.lower() == "true"

            table_data = {
                "tableDirName": table.tableDirName,
                "fullPathTable": table.fullPathTable,
                "fullPathVPXfile": table.fullPathVPXfile,
                "BGImagePath": table.BGImagePath,
                "DMDImagePath": table.DMDImagePath,
                "TableImagePath": table.TableImagePath,
                "WheelImagePath": table.WheelImagePath,
                "CabImagePath": table.CabImagePath,
                "TableVideoPath": table.TableVideoPath,
                "BGVideoPath": table.BGVideoPath,
                "DMDVideoPath": table.DMDVideoPath,
                "pupPackExists": table.pupPackExists,
                "altColorExists": table.altColorExists,
                "altSoundExists": table.altSoundExists,
                "meta": meta
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
        self.current_collection = collection
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
            # Apply the sort order
            self.current_sort = filters['sort_by']
            self.apply_sort(filters['sort_by'])
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

    def save_filter_collection(self, name, letter="All", theme="All", table_type="All", manufacturer="All", year="All", sort_by="Alpha"):
        """Save current filter settings as a named collection."""
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        c = VPXCollections(config_dir / "collections.ini")
        try:
            c.add_filter_collection(name, letter, theme, table_type, manufacturer, year, sort_by)
            c.save()
            return {"success": True, "message": f"Filter collection '{name}' saved successfully"}
        except ValueError as e:
            return {"success": False, "message": str(e)}

    def get_current_filter_state(self):
        """Return current filter state for UI synchronization."""
        return self.current_filters

    def get_current_sort_state(self):
        """Return current sort state for UI synchronization."""
        return self.current_sort

    def get_current_collection(self):
        """Return current collection name for UI synchronization."""
        return self.current_collection or 'None'

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
        Returns the count of filtered tables.
        """
        self.current_collection = None
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

        count = len(self.filteredTables)
        print(f"Filtered tables count: {count}")
        return count

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

    def apply_sort(self, sort_type):
        """
        Sort the current filtered tables.
        sort_type: 'Alpha' or 'Newest'
        Returns the count of sorted tables.
        """
        self.current_sort = sort_type
        print(f"Applying sort: {sort_type}")

        if sort_type == 'Alpha':
            # Sort alphabetically by VPSdb.name
            self.filteredTables.sort(
                key=lambda t: (
                    (t.metaConfig or {})
                    .get("VPSdb", {})
                    .get("name", "")
                    .lower()
                )
            )
        elif sort_type == 'Newest':
            # Sort by creation_time (newest first)
            self.filteredTables.sort(
                key=lambda t: t.creation_time if t.creation_time is not None else 0,
                reverse=True
            )

        count = len(self.filteredTables)
        print(f"Sorted {count} tables by {sort_type}")
        return count

    def console_out(self, output):
        print(f'Win: {self.myWindow[0].uid} - {output}')
        return output
           
    def get_joymaping(self):
        return {
            'joyleft': self.iniConfig.config['Input'].get('joyleft', '0'),
            'joyright': self.iniConfig.config['Input'].get('joyright', '0'),
            'joyup': self.iniConfig.config['Input'].get('joyup', '0'),
            'joydown': self.iniConfig.config['Input'].get('joydown', '0'),
            'joyselect': self.iniConfig.config['Input'].get('joyselect', '0'),
            'joymenu': self.iniConfig.config['Input'].get('joymenu', '0'),
            'joyback': self.iniConfig.config['Input'].get('joyback', '0'),
            'joyexit': self.iniConfig.config['Input'].get('joyexit', '0'),
            'joycollectionmenu': self.iniConfig.config['Input'].get('joycollectionmenu', '0')
        }

    def set_button_mapping(self, button_name, button_index):
        """Set a gamepad button mapping and save to config."""
        valid_buttons = [
            'joyleft', 'joyright', 'joyup', 'joydown',
            'joyselect', 'joymenu', 'joyback', 'joyexit', 'joycollectionmenu'
        ]

        if button_name not in valid_buttons:
            return {"success": False, "message": f"Invalid button name: {button_name}"}

        try:
            # Set the value in the config
            self.iniConfig.config.set('Input', button_name, str(button_index))
            # Save to file
            self.iniConfig.save()
            return {"success": True, "message": f"Mapped {button_name} to button {button_index}"}
        except Exception as e:
            return {"success": False, "message": f"Error saving mapping: {str(e)}"}
        
    def launch_table(self, index):
        table = self.filteredTables[index]
        vpx = table.fullPathVPXfile
        vpxbin = self.iniConfig.config['Settings'].get('vpxbinpath', '')
        print("Launching: ", [vpxbin, "-play", vpx])

        # Track the table play
        self._track_table_play(table)

        cmd = [Path(vpxbin).expanduser(), "-play", vpx]
        self.myWindow[0].toggle_fullscreen()
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL)
        process.wait()
        self.myWindow[0].toggle_fullscreen()
        self.send_event_all_windows_incself({"type": "TableLaunchComplete"})

    def _track_table_play(self, table):
        """Track a table play by adding it to the Last Played collection."""

        meta = table.metaConfig or {}
        info = meta.get("Info", {})
        vpsid = info.get("VPSId")

        if not vpsid:
            print("Table has no VPSId, cannot track play")
            return

        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        c = VPXCollections(config_dir / "collections.ini")

        # Create Last Played collection if it doesn't exist
        if "Last Played" not in c.get_collections_name():
            print("Creating 'Last Played' collection")
            c.add_collection("Last Played", vpsids=[])

        last_played_ids = c.get_vpsids("Last Played")

        if vpsid in last_played_ids:
            last_played_ids.remove(vpsid)

        last_played_ids.insert(0, vpsid)
        last_played_ids = last_played_ids[:30]

        c.config["Last Played"]["vpsids"] = ",".join(last_played_ids)
        c.save()

        print(f"Tracked table play: {vpsid} (now {len(last_played_ids)} in Last Played)")


    def build_metadata(self, download_media=True, update_all=False):
        """
        Trigger buildMetaData from the frontend.
        This runs in a background thread and returns progress/log updates via window events.

        Args:
            download_media: Whether to download media files
            update_all: Whether to update all tables (even if meta.ini exists)

        Returns:
            dict with success status and message
        """
        from clioptions import buildMetaData
        import threading
        from queue import Queue

        # Use a queue to safely pass events from background thread
        event_queue = Queue()

        def progress_callback(current, total, message):
            """Queue progress updates."""
            print(f"[buildmeta] Progress: {current}/{total} - {message}")
            event_queue.put({
                'type': 'buildmeta_progress',
                'current': current,
                'total': total,
                'message': message
            })

        def log_callback(message):
            """Queue log messages."""
            print(f"[buildmeta] Log: {message}")
            event_queue.put({
                'type': 'buildmeta_log',
                'message': message
            })

        def run_build():
            """Run buildMetaData in background thread."""
            try:
                result = buildMetaData(
                    downloadMedia=download_media,
                    updateAll=update_all,
                    progress_cb=progress_callback,
                    log_cb=log_callback
                )
                # Queue completion event
                event_queue.put({
                    'type': 'buildmeta_complete',
                    'result': result
                })
                # Refresh table list after completion
                self.allTables = TableParser(self.iniConfig.config['Settings']['tablerootdir'], self.iniConfig).getAllTables()
                self.filteredTables = self.allTables
            except Exception as e:
                # Queue error event
                event_queue.put({
                    'type': 'buildmeta_error',
                    'error': str(e)
                })
                import traceback
                traceback.print_exc()
            finally:
                # Signal completion
                event_queue.put({'type': 'buildmeta_done'})

        def process_events():
            """Process queued events and send to windows."""
            try:
                print("[buildmeta] Event processor started")
                while True:
                    # Block until we get an event
                    event = event_queue.get(timeout=30)
                    print(f"[buildmeta] Processing event: {event['type']}")
                    if event['type'] == 'buildmeta_done':
                        print("[buildmeta] Build complete, stopping event processor")
                        break
                    # Send event to all windows
                    try:
                        self.send_event_all_windows_incself(event)
                        print(f"[buildmeta] Sent event to windows: {event['type']}")
                    except Exception as e:
                        print(f"Error sending event to windows: {e}")
                        import traceback
                        traceback.print_exc()
            except Exception as e:
                print(f"Error processing buildmeta events: {e}")
                import traceback
                traceback.print_exc()

        # Start build in background thread
        build_thread = threading.Thread(target=run_build, daemon=True)
        build_thread.start()

        # Start event processor in another background thread
        event_thread = threading.Thread(target=process_events, daemon=True)
        event_thread.start()

        return {'success': True, 'message': 'Build metadata started'}

    def _resolve_theme_dir(self, theme_name):
        """Returns the filesystem path to the theme directory."""
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        theme_dir = config_dir / "themes" / theme_name
        if theme_dir.is_dir():
            return theme_dir
        return None

    def get_theme_config(self):
        theme_name = self.get_theme_name()
        theme_dir = self._resolve_theme_dir(theme_name)
        if not theme_dir:
            return None

        theme_path = theme_dir / "config.json"
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

    def get_theme_assets_port(self):
        return int(self.iniConfig.config['Network'].get('themeassetsport', '8000'))

    def get_theme_index_page(self):
        theme_name = self.get_theme_name()
        port = self.get_theme_assets_port()
        window_name = self.get_my_window_name()
        url = f'http://127.0.0.1:{port}/themes/{theme_name}/index_{window_name}.html'
        return url