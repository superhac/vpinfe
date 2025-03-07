import tkinter as tk
from screeninfo import get_monitors
from PIL import Image, ImageTk
import sys
import os
import subprocess
import argparse
import sdl2
import sdl2.ext
import time
import threading
from multiprocessing import Process
from queue import Queue
from enum import Enum, auto
from typing import Callable

from screennames import ScreenNames
from imageset import ImageSet
from screen import Screen
from tables import Tables
from config import Config
import metaconfig
from vpsdb import VPSdb
import vpxparser

class TKMsgType(Enum):
    ENABLE_STATUS_MSG  = auto
    DISABLE_STATUS_MSG = auto
    DISABLE_THREE_DOT  = auto
    CACHE_BUILD_COMPLETED = auto

class TkMsg():
    def __init__(self, MsgType: TKMsgType, func: Callable, msg: str):
        self.msgType = MsgType
        self.call = func
        self.msg = msg

# OS Specific
if sys.platform.startswith('win'):
    os.environ['PYSDL2_DLL_PATH'] = sys._MEIPASS+'/SDL2.dll' # need to include the sdl2 runtime for windows

# Assets
logoImage = sys._MEIPASS+"/assets/VPinFE_logo_main.png"
missingImage = sys._MEIPASS+"/assets/file_missing.png"

# Globals
version = "0.5 beta"
screens = []
ScreenNames = ScreenNames()
exitGamepad = False
background = False
tableRootDir = None
vpxBinPath = None
configfile = None
tableIndex = 0
tkMsgQueue = Queue()
RED_CONSOLE_TEXT = '\033[31m'
RESET_CONSOLE_TEXT = '\033[0m'

def key_pressed(event):
    global tableIndex
    global exitGamepad
    key = event.char # Get the character representation of the key
    keysym = event.keysym # Get the symbolic name of the key
    keycode = event.keycode # Get the numeric keycode
    #print(f"Key pressed: {key}, keysym: {keysym}, keycode: {keycode}")

    if keysym == "Shift_R":
        screenMoveRight()
    if keysym == "Shift_L":
        screenMoveLeft()
    if keysym == "Escape":
        exitGamepad = True # exit the gamepad loop
        Screen.rootWindow.destroy()

    # Lanuch Game
    if keysym == "a":
        for s in screens: 
            #s.window.withdraw()
            s.window.iconify()
        Screen.rootWindow.update_idletasks()
        #s.window.after(1, launchTable() )
        Screen.rootWindow.after(500, launchTable )
        
def screenMoveRight():
    global tableIndex

    if tableIndex != tables.getTableCount()-1:
        tableIndex += 1
        setGameDisplays(tables.getTable(tableIndex))
    else:
        tableIndex = 0;
        setGameDisplays(tables.getTable(tableIndex))

def screenMoveLeft():
    global tableIndex

    if tableIndex != 0:
        tableIndex -= 1
        setGameDisplays(tables.getTable(tableIndex))
    else:
        tableIndex = tables.getTableCount()-1
        setGameDisplays(tables.getTable(tableIndex))

def launchTable():
    global background
    background = True # # Disable SDL gamepad events
    launchVPX(tables.getTable(tableIndex).fullPathVPXfile)
    
    # check if we need to do postprocessing.  right now just check if we need to delete pinmame nvram
    meta = metaconfig.MetaConfig(tables.getTable(tableIndex).fullPathTable + "/" + "meta.ini")
    meta.actionDeletePinmameNVram()
    
    for s in screens:
        s.window.deiconify()
    Screen.rootWindow.update()
    
    Screen.rootWindow.focus_force()
    Screen.rootWindow.update()
    
def launchVPX(table):
    print("Lanuching: " + table)
    null = open(os.devnull, 'w')
    subprocess.call([vpxBinPath, '-play', table], bufsize=4096, stdout=null, stderr=null)

def setGameDisplays(tableInfo):
    # Load image BG
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].loadImage(tableInfo.BGImagePath)
        screens[ScreenNames.BG].addText(tableInfo.tableDirName, (screens[ScreenNames.BG].canvas.winfo_width() /2, 1080), anchor="s")


    # Load image DMD
    if ScreenNames.DMD is not None:
        screens[ScreenNames.DMD].loadImage(tableInfo.DMDImagePath)

    # load table image (rotated and we swap width and height around like portrait mode)
    if ScreenNames.TABLE is not None:
        screens[ScreenNames.TABLE].loadImage(tableInfo.TableImagePath)
       
def getScreens():
    print("Enumerating displays")
    # Get all available screens
    monitors = get_monitors()

    for i in range(len(monitors)):
        screen = Screen(monitors[i], missingImage)
        screens.append(screen)
        print("    ",i,":"+str(screen.screen))

def openJoysticks():
    print("Checking for gamepads")
    if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_JOYSTICK) < 0:
        print(f"     SDL_InitSubSystem Error: {sdl2.SDL_GetError()}")
        return

    num_joysticks = sdl2.SDL_NumJoysticks()
    print(f"     Found {num_joysticks} gamepads.")

    for i in range(num_joysticks):
        sdl2.SDL_JoystickOpen(i)

def loadconfig(configfile):
    global tableRootDir
    global vpxBinPath

    if configfile == None:
        configfile= "vpinfe.ini"
    try:
        config = Config(configfile)
    except Exception as e:
        print(f"{RED_CONSOLE_TEXT}Fatal: {e}{RESET_CONSOLE_TEXT}")
        sys.exit(1)

    current_dir = os.getcwd()
    print(f"Current working directory (using os.getcwd()): {current_dir}")

    # mandatory
    try:
        if Config.sections['Displays']["bgscreenid"] != "":
            ScreenNames.BG = int(Config.sections['Displays']["bgscreenid"])
        else:
             ScreenNames.BG = None
        if Config.sections['Displays']["dmdscreenid"] != "":
            ScreenNames.DMD = int(Config.sections['Displays']["dmdscreenid"])
        else:
            ScreenNames.DMD = None
        if Config.sections['Displays']["tablescreenid"] != "":
            ScreenNames.TABLE = int(Config.sections['Displays']["tablescreenid"])
        else:
             ScreenNames.TABLE
        tableRootDir = Config.sections['Settings']["tablerootdir"]
        vpxBinPath = Config.sections['Settings']["vpxbinpath"]
    except KeyError as e:
        print(f"{RED_CONSOLE_TEXT}Fatal: Missing mandatory '{e.args[0]}' entry in vpinfe.{RESET_CONSOLE_TEXT}")
        sys.exit(1)

    if not os.path.exists(vpxBinPath):
        print(f"{RED_CONSOLE_TEXT}Fatal: VPX binary not found.  Check your `vpxBinPath` value in vpinfe has correct path.{RESET_CONSOLE_TEXT}")
        sys.exit()
    
    if not os.path.exists(tableRootDir):
        print(f"{RED_CONSOLE_TEXT}Fatal: Table root dir not found.  Check your 'tableroot' value in vpinfe.ini has correct path.{RESET_CONSOLE_TEXT}")
        sys.exit()

    if  ScreenNames.BG == None and ScreenNames.DMD == None and ScreenNames.TABLE == None:
            print(f"{RED_CONSOLE_TEXT}Fatal: You must have at least one display set in your vpinfe.ini.{RESET_CONSOLE_TEXT}")
            sys.exit(1)

def buildMetaData():
        loadconfig(configfile)
        Tables(tableRootDir)
        vps = VPSdb(Tables.tablesRootFilePath)
        for table in Tables.tables:
            finalini = {}
            meta = metaconfig.MetaConfig(table.fullPathTable + "/" + "meta.ini") # check if we want it updated!!! TODO
            
            # vpsdb
            print(f"Checking VPSdb for {table.tableDirName}")
            vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
            vpsData = vps.lookupName(vpsSearchData["name"], vpsSearchData["manufacturer"], vpsSearchData["year"])
            #print(vpsData)
            
            # vpx file info
            print(f"Parsing VPX file for metadata")
            print(f"  Extracting {table.fullPathVPXfile} for metadata.")
            vpxData = vpxparser.singleFileExtract(table.fullPathVPXfile)
            
            # make the config.ini
            finalini['vpsdata'] = vpsData
            finalini['vpxdata'] = vpxData
            meta.writeConfig(finalini)

def parseArgs():
    global tableRootDir
    global vpxBinPath
    global configfile

    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--listres", help="ID and list your screens", action="store_true")
    parser.add_argument("--configfile", help="Configure the location of your vpinfe.ini file.  Default is cwd.")
    parser.add_argument("--buildmeta", help="Builds the meta.ini file in each table dir", action="store_true")
    args = parser.parse_args()

    if args.listres:
        # Get all available screens
        monitors = get_monitors()
        for i in range(len(monitors)):
            print(i,":"+str(monitors[i]))
        sys.exit()
        
    if args.configfile:
        configfile = args.configfile
        
    if args.buildmeta:
        buildMetaData()
        sys.exit()
    
def processTkMsgEvent(event):
        msg = tkMsgQueue.get()

        if msg.msgType == TKMsgType.CACHE_BUILD_COMPLETED:
            msg.call()
            
def disableStatusMsg():
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].textThreeDotAnimate(enabled=False)
        screens[ScreenNames.BG].removeStatusText()
   
def loadImageAllScreens(img_path):
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].loadImage(img_path)
    if ScreenNames.DMD is not None:
         screens[ScreenNames.DMD].loadImage(img_path)
    if ScreenNames.TABLE is not None:
        screens[ScreenNames.TABLE].loadImage(img_path)
    Screen.rootWindow.update()

def buildImageCache():
    loadImageAllScreens(logoImage)
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].addStatusText("Caching Images", (20,1000))
        screens[ScreenNames.BG].textThreeDotAnimate()
    thread = threading.Thread(target=buildImageCacheThread, daemon=True)
    thread.start()
  
def buildImageCacheThread():
    tkmsg = TkMsg(MsgType=TKMsgType.CACHE_BUILD_COMPLETED, func= disableStatusMsg, msg = "")
    tkMsgQueue.put(tkmsg)
    
    for i in range(Screen.maxImageCacheSize):
        if i == tables.getTableCount(): # breakout if theres less tables then cache max
            break
        if ScreenNames.BG is not None:
            screens[ScreenNames.BG].loadImage(tables.getTable(i).BGImagePath, display=False)
        if ScreenNames.DMD is not None:
            screens[ScreenNames.DMD].loadImage(tables.getTable(i).DMDImagePath, display=False)
        if ScreenNames.TABLE is not None:
            screens[ScreenNames.TABLE].loadImage(tables.getTable(i).TableImagePath, display=False)
    
    Screen.rootWindow.event_generate("<<vpinfe_tk>>")

def gameControllerInputThread():
    global exitGamepad
    global background
    # gamepad loop
    while not exitGamepad:
        #time.sleep(0.001)
        events = sdl2.ext.get_events()
     
        # SDL continues to queue events in the background while in vpx.  This loop eats those on return to vpinfe.
        if background:
            events = sdl2.ext.get_events()
            for event in events:
                pass
            background = False

        for event in events:
            if not background: # not coming back from vpx
                if event.type == sdl2.SDL_QUIT:
                    exitGamepad = True
                    break
                elif event.type == sdl2.SDL_JOYAXISMOTION:
                    axis_id = event.jaxis.axis

                    axis_value = event.jaxis.value / 32767.0  # Normalize to -1.0 to 1.0
                    #print(f"Axis {axis_id}: {axis_value}")
                elif event.type == sdl2.SDL_JOYBUTTONDOWN:
                    button_id = event.jbutton.button
                    if button_id == 5:
                        screenMoveRight()
                    elif button_id == 4:
                        screenMoveLeft()
                    elif button_id == 1:
                        for s in screens: 
                            s.window.withdraw()
                        #s.window.after(1, launchTable() )
                        launchTable()
                        break
                    print(f"Button {button_id} Down on Gamepad: {event.jbutton.which}")
                elif event.type == sdl2.SDL_JOYBUTTONUP:
                    button_id = event.jbutton.button
                    #print(f"Button {button_id} Up")
    
# Main Application
print("VPinFE "+version+" by Superhac (superhac007@gmail.com)")
parseArgs()
loadconfig(configfile)
sdl2.ext.init()
openJoysticks()
tables = Tables(tableRootDir)
getScreens()

# Ensure windows have updated dimensions
screens[0].window.update_idletasks()

# load logo and build cache
Screen.rootWindow.after(500, buildImageCache)

# load first screen after 5 secs letting the cache build
Screen.rootWindow.after(5000,setGameDisplays, tables.getTable(tableIndex))

# key trapping
Screen.rootWindow.bind("<Any-KeyPress>", key_pressed)

# our thread update callback on event
Screen.rootWindow.bind("<<vpinfe_tk>>", processTkMsgEvent)

# SDL gamepad input loop
gamepadThread = threading.Thread(target=gameControllerInputThread)
gamepadThread.start()

# tk blocking loop
Screen.rootWindow.mainloop()
    
# shutdown
sdl2.SDL_Quit()
#Screen.rootWindow.destroy()
