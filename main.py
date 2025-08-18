#!/usr/bin/env python3

import webview
from pathlib import Path
from screeninfo import get_monitors
from frontend.httpserver import HTTPServer
from frontend.api import API
import threading
from common.iniconfig import IniConfig
import sys
import os
from clioptions import parseArgs
from managerui.managerui import start_manager_ui
from nicegui import app as nicegui_app
#import managerui.managerui

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
            fullscreen=True  # Set to False since we're manually sizing it
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
            fullscreen=True  # Set to False since we're manually sizing it
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
            fullscreen=True  # Set to False since we're manually sizing it
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
#loadGamepadTestWindow() # add to launch options

# Start an the HTTP server to serve the images from the "tables" directory
MOUNT_POINTS = {
        '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
        '/web/': os.path.join(os.getcwd(), 'web'),
        '/static/': os.path.join(os.getcwd(), 'managerui/static/')
        }
http_server = HTTPServer(MOUNT_POINTS)
http_server.start_file_server()

def launch_nicegui():
    # IMPORTANT: make NiceGUI not try to reload or open a browser
    # managerui.start_nicegui should call ui.run(..., show=False, reload=False)
    start_manager_ui()
webview.start(launch_nicegui)

# start the manager UI
#nagerui.managerui.startServer()

# block and start webview
webview.start(http_server=True)

# shutdown items
http_server.on_closed()
nicegui_app.shutdown()
#managerui.managerui.stopServer()

################ debug stuff ################
#print(webview_windows[2][2].get_theme_index_page())
#threading.Timer(10.0, webview_windows[2][2].send_event_all_windows).start()
#print(iniconfig.config['Settings']['tablerootdir'])

#print(webview_windows[2][2].get_tables())
#print(webview_windows[2][2].get_tables())