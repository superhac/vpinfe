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

#debug
import sys
from common.vpxcollections import VPXCollections
from common.tableparser import TableParser

nicegui_app.add_static_files('/static', os.path.join(os.getcwd(), 'managerui/static'))
html_file = Path(__file__).parent / "web/splash.html"
webview_windows = [] # [ [window_name, window, api] ]
iniconfig = IniConfig("./vpinfe.ini")

 # The last window created will be the one in focus.  AKA the controller for all the other windows!!!! Always "table"
def loadWindows():
    global webview_windows
    global api
    monitors = get_monitors()
    print(monitors)
    
    if iniconfig.config['Displays']['bgscreenid']:
        api = API(iniconfig)
        print("found bg screen id: ", iniconfig.config['Displays']['bgscreenid'])
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
        print("found dmd screen id: ", iniconfig.config['Displays']['dmdscreenid'])
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
        print("found table screen id: ", iniconfig.config['Displays']['tablescreenid'])
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

#DEBUG

""" c = VPXCollections(Path(__file__).parent / "collections.ini")
tables = TableParser(iniconfig.config['Settings']['tablerootdir']).getAllTables();

print("Sections:", c.get_collections_name)
print("All:", c.get_all())
print(c.get_vpsids('Favorites'))

mylist = c.filter_tables(tables, 'Favorites')
print([item.tableDirName for item in mylist])

sys.exit() """


# Initialize webview windows
loadWindows()

# Start an the HTTP server to serve the images from the "tables" directory
MOUNT_POINTS = {
        '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
        '/web/': os.path.join(os.getcwd(), 'web'),
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

################ debug stuff ################
#print(webview_windows[2][2].get_theme_index_page())
#threading.Timer(10.0, webview_windows[2][2].send_event_all_windows).start()
#print(iniconfig.config['Settings']['tablerootdir'])

#print(webview_windows[2][2].get_tables())
#print(webview_windows[2][2].get_tables())