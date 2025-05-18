#!/usr/bin/env python3

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
from tkmessages import TKMsgType, TkMsg

from logger import init_logger,get_logger,update_logger_config
from screennames import ScreenNames
from imageset import ImageSet
from screen import Screen
from tables import Tables
from config import Config
import metaconfig
from vpsdb import VPSdb
import vpxparser
import standaloneScripts
from pauseabletask import PauseableTask

# OS Specific
if sys.platform.startswith('win'):
    os.environ['PYSDL2_DLL_PATH'] = sys._MEIPASS+'/SDL2.dll' # need to include the sdl2 runtime for windows

# Assets
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    logoImage = sys._MEIPASS+"/assets/VPinFE_logo_main.png"
    missingImage = sys._MEIPASS+"/assets/file_missing.png"
else:
    logoImage = "assets/VPinFE_logo_main.png"
    missingImage = "assets/file_missing.png"

# Globals
version = "0.5 beta"
logger = None
parservpx = None
screens = []
ScreenNames = ScreenNames()
shutdown_event = threading.Event()
background = False
tableRootDir = None
vpxBinPath = None
configfile = None
vpinfeIniConfig = None
tableIndex = 0
tkMsgQueue = Queue()
RED_CONSOLE_TEXT = '\033[31m'
RESET_CONSOLE_TEXT = '\033[0m'
task_build_cache = None

def setShutdownEvent():
    if not shutdown_event.is_set():
        buildImageCacheStop()
        shutdown_event.set()

def key_pressed(event):
    keysym = event.keysym # Get the symbolic name of the key
    #key = event.char # Get the character representation of the key
    #keycode = event.keycode # Get the numeric keycode
    #logger.debug(f"Key pressed: {key}, keysym: {keysym}, keycode: {keycode}")

    if keysym == "Shift_R":
        screenMoveRight()
    elif keysym == "Shift_L":
        screenMoveLeft()
    elif keysym == "q" or keysym == "Escape":
        setShutdownEvent()
    elif keysym == "a" or keysym == "Return":
       # Launch Game
        for s in screens:
            s.window.iconify()
        Screen.rootWindow.update_idletasks()
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
    buildImageCachePause()
    launchVPX(tables.getTable(tableIndex).fullPathVPXfile)
    
    # check if we need to do postprocessing.  right now just check if we need to delete pinmame nvram
    meta = metaconfig.MetaConfig(tables.getTable(tableIndex).fullPathTable + "/" + "meta.ini")
    meta.actionDeletePinmameNVram()
    
    for s in screens:
        s.window.deiconify()
        s.window.lift()
        s.window.focus_force()
    Screen.rootWindow.update()
    Screen.rootWindow.focus_force()
    Screen.rootWindow.update()
    Screen.rootWindow.lift()
    Screen.rootWindow.focus_force()
    Screen.rootWindow.focus_set()
    Screen.rootWindow.update_idletasks()
    buildImageCacheResume()

def launchVPX(table):
    logger.info(f"Launching: {table}")
    null = open(os.devnull, 'w')
    subprocess.call([vpxBinPath, '-play', table], bufsize=4096, stdout=null, stderr=null)

def setGameDisplays(tableInfo):
    # Load image BG
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].loadImage(tableInfo.BGImagePath, tableInfo=tableInfo if int(vpinfeIniConfig.config['Displays']['hudscreenid']) == ScreenNames.BG else None )
        #screens[ScreenNames.BG].addText(tableInfo.metaConfig.get('VPSdb','name'), (screens[ScreenNames.BG].canvas.winfo_width() /2, 1080), anchor="s")

    # Load image DMD
    if ScreenNames.DMD is not None:
        screens[ScreenNames.DMD].loadImage(tableInfo.DMDImagePath, tableInfo=tableInfo if int(vpinfeIniConfig.config['Displays']['hudscreenid']) == ScreenNames.DMD else None)

    # load table image (rotated and we swap width and height around like portrait mode)
    if ScreenNames.TABLE is not None:
        screens[ScreenNames.TABLE].loadImage(tableInfo.TableImagePath, tableInfo=tableInfo if int(vpinfeIniConfig.config['Displays']['hudscreenid']) == ScreenNames.TABLE else None)
       
def getScreens():
    logger.info("Enumerating displays")
    # Get all available screens
    monitors = get_monitors()

    for i in range(len(monitors)):
        if not vpinfeIniConfig.config['Displays']['hudrotangle'] == "" and int(vpinfeIniConfig.config['Displays']['hudscreenid']) == i:
            angle = int(vpinfeIniConfig.config['Displays']['hudrotangle'])
        elif not vpinfeIniConfig.config['Displays']['tablerotangle'] == "" and int(vpinfeIniConfig.config['Displays']['tablescreenid']) == i:
            angle = int(vpinfeIniConfig.config['Displays']['tablerotangle'])
        else:
            angle = 0
        screen = Screen(monitors[i], angle, missingImage, vpinfeIniConfig)
        screens.append(screen)
        logger.info(f"Display {i}:{str(screen.screen)}")

def openJoysticks():
    logger.info("Checking for gamepads")
    if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_JOYSTICK) < 0:
        logger.error(f"SDL_InitSubSystem Error: {sdl2.SDL_GetError()}")
        return

    num_joysticks = sdl2.SDL_NumJoysticks()
    logger.info(f"Found {num_joysticks} gamepads.")

    for i in range(num_joysticks):
        joystick = sdl2.SDL_JoystickOpen(i)
        if joystick:
            name = sdl2.SDL_JoystickName(joystick)
            logger.info(f"Joystick {i}: {name.decode('utf-8')}")
            sdl2.SDL_JoystickClose(joystick)
        else:
            logger.error(f"Could not open joystick {i}")

def loadconfig(configfile):
    global tableRootDir
    global vpxBinPath
    global vpinfeIniConfig

    if configfile == None:
        configfile= "vpinfe.ini"
    try:
        vpinfeIniConfig = Config(configfile)
    except Exception as e:
        logger.critical(f"{RED_CONSOLE_TEXT}{e}{RESET_CONSOLE_TEXT}")
        sys.exit(1)

    current_dir = os.getcwd()
    logger.debug(f"Current working directory (using os.getcwd()): {current_dir}")

    # mandatory
    try:
        if vpinfeIniConfig.config['Displays']["bgscreenid"] != "":
            ScreenNames.BG = int(vpinfeIniConfig.config['Displays']["bgscreenid"])
        else:
             ScreenNames.BG = None
        if vpinfeIniConfig.config['Displays']["dmdscreenid"] != "":
            ScreenNames.DMD = int(vpinfeIniConfig.config['Displays']["dmdscreenid"])
        else:
            ScreenNames.DMD = None
        if vpinfeIniConfig.config['Displays']["tablescreenid"] != "":
            ScreenNames.TABLE = int(vpinfeIniConfig.config['Displays']["tablescreenid"])
        else:
             ScreenNames.TABLE
        tableRootDir = vpinfeIniConfig.config['Settings']["tablerootdir"]
        vpxBinPath = vpinfeIniConfig.config['Settings']["vpxbinpath"]
    except KeyError as e:
        logger.critical(f"{RED_CONSOLE_TEXT}Missing mandatory '{e.args[0]}' entry in vpinfe.{RESET_CONSOLE_TEXT}")
        sys.exit(1)

    if not os.path.exists(vpxBinPath):
        logger.critical(f"{RED_CONSOLE_TEXT}VPX binary not found.  Check your `vpxBinPath` value in vpinfe has correct path.{RESET_CONSOLE_TEXT}")
        sys.exit()
    
    if not os.path.exists(tableRootDir):
        logger.critical(f"{RED_CONSOLE_TEXT}Table root dir not found.  Check your 'tableroot' value in vpinfe.ini has correct path.{RESET_CONSOLE_TEXT}")
        sys.exit()

    if  ScreenNames.BG == None and ScreenNames.DMD == None and ScreenNames.TABLE == None:
            logger.critical(f"{RED_CONSOLE_TEXT}You must have at least one display set in your vpinfe.ini.{RESET_CONSOLE_TEXT}")
            sys.exit(1)

def buildMetaData():
        loadconfig(configfile)
        Tables(tableRootDir)
        vps = VPSdb(Tables.tablesRootFilePath, vpinfeIniConfig)
        for table in Tables.tables:
            finalini = {}
            meta = metaconfig.MetaConfig(table.fullPathTable + "/" + "meta.ini") # check if we want it updated!!! TODO
            
            # vpsdb
            logger.info(f"Checking VPSdb for {table.tableDirName}")
            vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
            try:
                vpsData = vps.lookupName(vpsSearchData["name"], vpsSearchData["manufacturer"], vpsSearchData["year"])
            except TypeError as e:
                logger.error(f"{RED_CONSOLE_TEXT}Not found in VPS{RESET_CONSOLE_TEXT}")
            
            # vpx file info
            logger.info(f"Parsing VPX file for metadata")
            logger.info(f"Extracting {table.fullPathVPXfile} for metadata.")
            vpxData = parservpx.singleFileExtract(table.fullPathVPXfile)
            
            # make the config.ini
            finalini['vpsdata'] = vpsData
            finalini['vpxdata'] = vpxData
            meta.writeConfigMeta(finalini)
            if not vpsData is None:
               vps.downloadMediaForTable(table, vpsData['id'])

def vpxPatches():
    loadconfig(configfile)
    Tables(tableRootDir)
    standaloneScripts.StandaloneScripts(Tables.tables)

def parseArgs():
    global tableRootDir
    global vpxBinPath
    global configfile

    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--listres", help="ID and list your screens", action="store_true")
    parser.add_argument("--configfile", help="Configure the location of your vpinfe.ini file.  Default is cwd.")
    parser.add_argument("--buildmeta", help="Builds the meta.ini file in each table dir", action="store_true")
    parser.add_argument("--vpxpatch", help="Using vpx-standalone-scripts will attempt to load patches automatically", action="store_true")
    
    args = parser.parse_args()

    if args.listres:
        # Get all available screens
        monitors = get_monitors()
        for i in range(len(monitors)):
            logger.info(f"{i}:{str(monitors[i])}")
        sys.exit()
        
    if args.configfile:
        configfile = args.configfile
        
    if args.buildmeta:
        buildMetaData()
        sys.exit()
        
    if args.vpxpatch:
        vpxPatches()
        sys.exit()
    
def processTkMsgEvent(event):
        msg = tkMsgQueue.get()

        if msg.msgType == TKMsgType.CACHE_BUILD_COMPLETED:
            msg.call()
        if msg.msgType == TKMsgType.SHUTDOWN:
            msg.call()
            
def disableStatusMsg():
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].textThreeDotAnimate(enabled=False)
        screens[ScreenNames.BG].removeStatusText()

def shutDownMsg():
    Screen.rootWindow.after(500, Screen.rootWindow.destroy)
    
def loadImageAllScreens(img_path):
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].loadImage(img_path)
    if ScreenNames.DMD is not None:
         screens[ScreenNames.DMD].loadImage(img_path)
    if ScreenNames.TABLE is not None:
        screens[ScreenNames.TABLE].loadImage(img_path)
    Screen.rootWindow.update()

def buildImageCache():
    global task_build_cache
    loadImageAllScreens(logoImage)
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].addStatusText("Caching Images", (10,1034))
        screens[ScreenNames.BG].textThreeDotAnimate()
    task_build_cache = PauseableTask(name="buildImageCache", target_func=buildImageCacheThread)
    if task_build_cache is None:
        logger.debug("buildImageCache: task_build_cache is None")
        return
    thread = threading.Thread(target=task_build_cache.start, daemon=True)
    thread.start()

def buildImageCachePause():
    if task_build_cache is None:
        logger.debug("buildImageCachePause: task_build_cache is None")
        return
    task_build_cache.pause()

def buildImageCacheResume():
    if task_build_cache is None:
        logger.debug("buildImageCacheResume: task_build_cache is None")
        return
    task_build_cache.resume()

def buildImageCacheStop():
    if task_build_cache is None:
        logger.debug("buildImageCacheStop: task_build_cache is None")
        return
    task_build_cache.stop()

def buildImageCacheSleep(duration):
    if task_build_cache is None:
        logger.debug("buildImageCacheSleep: task_build_cache is None")
        return
    task_build_cache.sleep(duration)

def buildImageCacheisPaused():
    if task_build_cache is None:
        logger.debug("buildImageCacheIsPaused: task_build_cache is None")
        return False
    return task_build_cache.is_paused()

def buildImageCacheThread():
    tkmsg = TkMsg(MsgType=TKMsgType.CACHE_BUILD_COMPLETED, func=disableStatusMsg, msg="")
    tkMsgQueue.put(tkmsg)

    for i in range(Screen.maxImageCacheSize):
        if i == tables.getTableCount():
            break
        if shutdown_event.is_set():
            break
        if buildImageCacheisPaused():
            buildImageCacheSleep(0.5)
            continue
        if ScreenNames.BG is not None:
            screens[ScreenNames.BG].loadImage(tables.getTable(i).BGImagePath, display=False)
        if shutdown_event.is_set():
            break
        if buildImageCacheisPaused():
            buildImageCacheSleep(0.5)
            continue
        if ScreenNames.DMD is not None:
            screens[ScreenNames.DMD].loadImage(tables.getTable(i).DMDImagePath, display=False)
        if shutdown_event.is_set():
            break
        if buildImageCacheisPaused():
            buildImageCacheSleep(0.5)
            continue
        if ScreenNames.TABLE is not None:
            screens[ScreenNames.TABLE].loadImage(tables.getTable(i).TableImagePath, display=False)

    Screen.rootWindow.event_generate("<<vpinfe_tk>>")

    logger.debug("Exiting buildImageCacheThread")

def gameControllerInputThread():
    global background
    # gamepad loop
    while not shutdown_event.is_set():
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
                    setShutdownEvent()
                    break
                elif event.type == sdl2.SDL_JOYAXISMOTION:
                    axis_id = event.jaxis.axis

                    axis_value = event.jaxis.value / 32767.0  # Normalize to -1.0 to 1.0
                    #logger.debug(f"Axis {axis_id}: {axis_value}")
                elif event.type == sdl2.SDL_JOYBUTTONDOWN:
                    button_id = event.jbutton.button
                    if button_id == int(vpinfeIniConfig.config['Settings']['joyright']):
                        screenMoveRight()
                    elif button_id == int(vpinfeIniConfig.config['Settings']['joyleft']):
                        screenMoveLeft()
                    elif button_id == int(vpinfeIniConfig.config['Settings']['joyselect']):
                        for s in screens: 
                            s.window.withdraw()
                        #s.window.after(1, launchTable() )
                        launchTable()
                        break
                    elif button_id == int(vpinfeIniConfig.config['Settings']['joyexit']):
                        logger.debug("Exit requested")
                        setShutdownEvent()
                    elif button_id == int(vpinfeIniConfig.config['Settings']['joymenu']):
                        logger.debug("Not implemented yet...")
                    elif button_id == int(vpinfeIniConfig.config['Settings']['joyback']):
                        logger.debug("Not implemented yet...")
                    logger.debug(f"Button {button_id} Down on Gamepad: {event.jbutton.which}")
                elif event.type == sdl2.SDL_JOYBUTTONUP:
                    button_id = event.jbutton.button
                    #logger.debug(f"Button {button_id} Up")

    logger.debug("Exiting gameControllerInputThread and requesting shutdown")
    tkmsg = TkMsg(MsgType=TKMsgType.SHUTDOWN, func=shutDownMsg, msg = "")
    tkMsgQueue.put(tkmsg)
    Screen.rootWindow.event_generate("<<vpinfe_tk>>")

if __name__ == "__main__":
    logger = init_logger("VPinFE")
    logger.info(f"VPinFE {version} by Superhac (superhac007@gmail.com)")
    parservpx = vpxparser.VPXParser()
    parseArgs()
    loadconfig(configfile)
    update_logger_config(vpinfeIniConfig.config['Logger'])
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
