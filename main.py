import webview
from pathlib import Path
from screeninfo import get_monitors
from httpserver import HTTPServer
from api import API
import threading
from tableparser import TableParser
from iniconfig import IniConfig
import sys
import os

html_file = Path(__file__).parent / "web/splash.html"
table_root_path = '/home/superhac/tables/'
webview_windows = [] # [ [window_name, window, api] ]
iniconfig = IniConfig("./vpinfe.ini")

def loadGamepadTest():
    global webview_windows
    api = API()
    html = Path(__file__).parent / "web/diag/gamepad.html"
    api.tables = TableParser(table_root_path).getAllTables()
    api.iniConfig = iniconfig
    win = webview.create_window(
            "BG Screen",
             url=f"file://{html.resolve()}",
            js_api=api,
            background_color="#000000",
            fullscreen=True  # Set to False since we're manually sizing it
        )
    api.myWindow.append(win)
    webview_windows.append(['table',win, api])
    api.webview_windows = webview_windows
    api.iniConfig = iniconfig
    api.finish_setup()

 # The last window created will be the one in focus.  AKA the controller for all the other windows!!!! Always "table"
def loadWindows():
    global webview_windows
    global api
    monitors = get_monitors()
    tables = TableParser(table_root_path).getAllTables()
    print(monitors)
    
    if iniconfig.config['Displays']['bgscreenid']:
        api = API()
        api.tables = tables
        api.iniConfig = iniconfig
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
        api.finish_setup()
        
    if iniconfig.config['Displays']['dmdscreenid']:
        print("found dmd screen id: ", iniconfig.config['Displays']['dmdscreenid'])
        screen_id = int(iniconfig.config['Displays']['dmdscreenid'])
        api = API()
        api.tables = tables
        api.iniConfig = iniconfig
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
        api.finish_setup()
        
    if iniconfig.config['Displays']['tablescreenid']:  # this always needs to be last to get the focus set.
        print("found table screen id: ", iniconfig.config['Displays']['tablescreenid'])
        screen_id = int(iniconfig.config['Displays']['tablescreenid'])
        api = API()
        api.tables = tables
        api.iniConfig = iniconfig
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
        api.finish_setup()
             
# Initialize webview windows
loadWindows()
#loadGamepadTest() # add to launch options

# Start an the HTTP server to serve the images from the "tables" directory
MOUNT_POINTS = {
        '/tables/': os.path.abspath(iniconfig.config['Settings']['tablerootdir']),
        '/web/': os.path.join(os.getcwd(), 'web'),
        }
http_server = HTTPServer(MOUNT_POINTS)
http_server.start_file_server()

#debug
#print(webview_windows[2][2].get_theme_index_page())
#threading.Timer(10.0, webview_windows[2][2].send_event_all_windows).start()

# block and start webview
webview.start(http_server=True, debug=True)

# shutdown 
http_server.on_closed()

################ debug stuff ################
#print(iniconfig.config['Settings']['tablerootdir'])

#print(webview_windows[2][2].get_tables())
#print(webview_windows[2][2].get_tables())