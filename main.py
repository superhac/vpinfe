#!/usr/bin/env python3

import webview
from pathlib import Path
from screeninfo import get_monitors
from frontend.customhttpserver import CustomHTTPServer
from frontend.api import API
import threading
from common.iniconfig import IniConfig
import sys
import os
from clioptions import parseArgs
from managerui.managerui import start_manager_ui, stop_manager_ui
from nicegui import app as nicegui_app
from platformdirs import user_config_dir

#debug
import sys
from common.vpxcollections import VPXCollections
from common.tableparser import TableParser

# Get the base path - works for both dev and PyInstaller
if getattr(sys, 'frozen', False):
    # Running in PyInstaller bundle
    base_path = sys._MEIPASS
else:
    # Running in normal Python environment
    base_path = os.path.dirname(os.path.abspath(__file__))

nicegui_app.add_static_files('/static', os.path.join(base_path, 'managerui/static'))
html_file = Path(base_path) / "web/splash.html"
webview_windows = [] # [ [window_name, window, api] ]

# Use platform-specific config directory
config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
config_dir.mkdir(parents=True, exist_ok=True)
config_path = config_dir / "vpinfe.ini"
iniconfig = IniConfig(str(config_path))

 # The last window created will be the one in focus.  AKA the controller for all the other windows!!!! Always "table"
def loadWindows():
    global webview_windows
    global api
    monitors = get_monitors()
    print(monitors)
    
    if iniconfig.config['Displays']['bgscreenid']:
        api = API(iniconfig)
        #print("found bg screen id: ", iniconfig.config['Displays']['bgscreenid'])
        screen_id = int(iniconfig.config['Displays']['bgscreenid'])
        win = webview.create_window(
            "BG Screen",
            url=f"file://{html_file.resolve()}",
            js_api=api,
            x=monitors[screen_id].x,
            y=monitors[screen_id].y,
            width=monitors[screen_id].width,
            height=monitors[screen_id].height,
            background_color="#000000",
            fullscreen=True  
        )
        api.myWindow.append(win)
        webview_windows.append(['bg',win, api])
        api.webview_windows = webview_windows
        api.iniConfig = iniconfig
        api._finish_setup()
        
    if iniconfig.config['Displays']['dmdscreenid']:
        #print("found dmd screen id: ", iniconfig.config['Displays']['dmdscreenid'])
        screen_id = int(iniconfig.config['Displays']['dmdscreenid'])
        api = API(iniconfig)
        win = webview.create_window(
            "DMD Screen",
            url=f"file://{html_file.resolve()}",
            js_api=api,
            x=monitors[screen_id].x,
            y=monitors[screen_id].y,
            width=monitors[screen_id].width,
            height=monitors[screen_id].height,
            background_color="#000000",
            fullscreen=True  
        )
        api.myWindow.append(win)
        webview_windows.append(['dmd',win, api])
        api.webview_windows = webview_windows
        api.iniConfig = iniconfig
        api._finish_setup()
        
    if iniconfig.config['Displays']['tablescreenid']:  # this always needs to be last to get the focus set.
        #print("found table screen id: ", iniconfig.config['Displays']['tablescreenid'])
        screen_id = int(iniconfig.config['Displays']['tablescreenid'])
        api = API(iniconfig)
        win = webview.create_window(
            "Table Screen",
            url=f"file://{html_file.resolve()}",
            js_api=api,
            x=monitors[screen_id].x,
            y=monitors[screen_id].y,
            width=monitors[screen_id].width,
            height=monitors[screen_id].height,
            background_color="#000000",
            fullscreen=True,  
            frameless=True # need this to restore the UI from VPX taking over fullscreen while its in the background and hanging our context
        )
        api.myWindow.append(win)
        webview_windows.append(['table',win, api])
        api.webview_windows = webview_windows
        api.iniConfig = iniconfig
        api._finish_setup()

if len(sys.argv) > 0:
    parseArgs()

# Initialize webview windows
loadWindows()

# Start an the HTTP server to serve the images from the "tables" directory
MOUNT_POINTS = {
        '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
        '/web/': os.path.join(base_path, 'web'),
        }
http_server = CustomHTTPServer(MOUNT_POINTS)
http_server.start_file_server()

# Start the NiceGUI HTTP server
start_manager_ui()

# block and start webview
webview.start(http_server=True)

# shutdown items
http_server.on_closed()
nicegui_app.shutdown()
stop_manager_ui()
