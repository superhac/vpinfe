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
import managerui.managerui

html_file = Path(__file__).parent / "web/splash.html"
webview_windows = [] # [ [window_name, window, api] ]
iniconfig = IniConfig("./vpinfe.ini")

def is_wayland():
    return "WAYLAND_DISPLAY" in os.environ

 # The last window created will be the one in focus.  AKA the controller for all the other windows!!!! Always "table"
def loadWindows():
    global webview_windows
    global api
    monitors = get_monitors()
    wayland_mode = is_wayland()
    print("Detected Wayland:", wayland_mode)
    print("Monitors:", monitors)

def loadWindows():
    global webview_windows
    monitors = get_monitors()
    wayland_mode = is_wayland()
    print("Detected Wayland:", wayland_mode)
    print("Monitors:", monitors)

    def add_window(name, screen_id):
        print("found {name} Screen: {screen_id}")
        api = API(iniconfig)
        monitor = monitors[screen_id]
        if wayland_mode:
            # Wayland: fullscreen, compositor decides placement
            win = webview.create_window(
                f"{name} Screen",
                url=f"file://{html_file.resolve()}",
                js_api=api,
                fullscreen=True,
                background_color="#000000"
            )
        else:
            # X11: manual positioning
            win = webview.create_window(
                f"{name} Screen",
                url=f"file://{html_file.resolve()}",
                js_api=api,
                x=monitor.x,
                y=monitor.y,
                width=monitor.width,
                height=monitor.height,
                fullscreen=False,
                background_color="#000000"
            )
        api.myWindow.append(win)
        webview_windows.append([name.lower(), win, api])
        api.webview_windows = webview_windows
        api.iniConfig = iniconfig
        api._finish_setup()

    if iniconfig.config['Displays']['bgscreenid']:
        add_window("BG", int(iniconfig.config['Displays']['bgscreenid']))

    if iniconfig.config['Displays']['dmdscreenid']:
        add_window("DMD", int(iniconfig.config['Displays']['dmdscreenid']))

    if iniconfig.config['Displays']['tablescreenid']:
        add_window("Table", int(iniconfig.config['Displays']['tablescreenid']))

if len(sys.argv) > 0:
    parseArgs()

# Initialize webview windows
loadWindows()
#loadGamepadTestWindow() # add to launch options

# Start an the HTTP server to serve the images from the "tables" directory
MOUNT_POINTS = {
        '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
        '/web/': os.path.join(os.getcwd(), 'web'),
        }
http_server = HTTPServer(MOUNT_POINTS)
http_server.start_file_server()

# start the manager UI
managerui.managerui.startServer()

# block and start webview
webview.start(http_server=True)

# shutdown items
http_server.on_closed()
managerui.managerui.stopServer()

################ debug stuff ################
#print(webview_windows[2][2].get_theme_index_page())
#threading.Timer(10.0, webview_windows[2][2].send_event_all_windows).start()
#print(iniconfig.config['Settings']['tablerootdir'])

#print(webview_windows[2][2].get_tables())
#print(webview_windows[2][2].get_tables())