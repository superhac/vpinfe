#!/usr/bin/env python3

import tkinter as tk
from tkinter import messagebox
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

from pinlog import init_logger, get_logger, update_logger_config, get_named_logger
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
       launchTable()

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
    background = True  # Disable SDL gamepad events
    buildImageCachePause()
    launchVPX(tables.getTable(tableIndex).fullPathVPXfile)
    logger.debug(f"Returning from playing the table. Resetting focus on us.")

    # check if we need to do postprocessing.  right now just check if we need to delete pinmame nvram
    meta = metaconfig.MetaConfig(tables.getTable(tableIndex).fullPathTable + "/" + "meta.ini")
    meta.actionDeletePinmameNVram()
    
    Screen.rootWindow.update_idletasks()
    
    if vpinfeIniConfig.get_string('Displays','windowmanager', "") == "kde":
        for s in screens:
            s.window.update_idletasks()
            s.window.deiconify()
            s.window.update_idletasks()
            s.window.update()
            s.window.lift()
            s.window.focus_force()
            s.window.update_idletasks()
    else: # gnome, win, mac, etc
        for s in screens:
            s.window.update_idletasks()
            s.window.withdraw()
            s.window.deiconify()
            s.window.update_idletasks()
            s.window.geometry(f"{s.screen.width}x{s.screen.height}+{s.screen.x}+{s.screen.y}")
            s.window.update()
          
        Screen.rootWindow.update()
        Screen.rootWindow.focus_force()
        Screen.rootWindow.update()

    Screen.rootWindow.after(350, buildImageCacheResume)

def launchVPX(table):
    logger.info(f"Launching: {table}")

    def iconify_all_windows(reason):
        logger.debug(f"Iconifying windows due to {reason}")
        for s in screens:
            s.window.iconify()
        
        Screen.rootWindow.update_idletasks()

    keyword_or_timeout = threading.Event()
    process_exited = threading.Event()
    timeout_duration = 10.0  # seconds to wait for keyword before iconifying anyway
    global reason
    reason = None

    # Thread to read output and look for keyword
    def output_reader():
        global reason

        # Use a different name of the logger while standalone is running
        vpx_logger = get_named_logger("VPinball")

        try:
            for line in iter(proc.stdout.readline, b''):
                if not line or process_exited.is_set():
                    break
                decoded = line.decode(errors="ignore").strip()
                vpx_logger.debug(decoded)
                if "Starting render thread" in decoded and not keyword_or_timeout.is_set():
                    reason = "keyword found"
                    keyword_or_timeout.set()
        except Exception as e:
            logger.error(f"Error reading process output: {e}")
            proc.stdout.close()

    # Thread for timeout monitoring
    def timeout_monitor():
        global reason
        try:
            # Wait for either keyword found or timeout elapsed
            keyword_found_or_timeout = keyword_or_timeout.wait(timeout_duration)
            if not keyword_found_or_timeout:
                # Timeout occurred without finding keyword
                reason = f"{timeout_duration}s timeout reached"
                keyword_or_timeout.set()
        except Exception as e:
            logger.error(f"Error in timeout monitoring: {e}")

    # Thread to monitor process completion
    def process_monitor():
        global reason
        try:
            # Wait for process to complete
            proc.wait()
            logger.debug(f"VPX process exited with code: {proc.returncode}")
        except Exception as e:
            logger.error(f"Error monitoring process: {e}")
        finally:
            reason = "process exited"
            process_exited.set() # Has to be set first so we don't iconify if we're already exiting
            keyword_or_timeout.set() # In case we exited before the keyword or the timeout happened
            logger.debug(f"Process monitoring complete for {table}")

    # Start the VPX process
    proc = subprocess.Popen(
        [vpxBinPath, '-play', table],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )

    # Start the monitoring threads
    output_thread = threading.Thread(target=output_reader, daemon=True)
    output_thread.start()

    timeout_thread = threading.Thread(target=timeout_monitor, daemon=True)
    timeout_thread.start()

    monitor_thread = threading.Thread(target=process_monitor, daemon=True)
    monitor_thread.start()

    # Wait for the keyword or timeout to be set to iconify the windows
    logger.debug(f"Waiting for the table to start rendering or {timeout_duration} seconds.")
    keyword_or_timeout.wait()
    if not process_exited.is_set():
        iconify_all_windows(reason)

    # Wait for the process to exit before continuing
    logger.debug("Waiting for the table to exit.")
    process_exited.wait()
    logger.debug(f"Exited {table}")

def setGameDisplays(tableInfo):
    hudscreenid = vpinfeIniConfig.get_int('Displays','hudscreenid', -1)

    # Load image BG
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].loadImage(tableInfo.BGImagePath, tableInfo=tableInfo if hudscreenid == ScreenNames.BG else None )
        #screens[ScreenNames.BG].addText(tableInfo.metaConfig.get('VPSdb','name'), (screens[ScreenNames.BG].canvas.winfo_width() /2, 1080), anchor="s")

    # Load image DMD
    if ScreenNames.DMD is not None:
        screens[ScreenNames.DMD].loadImage(tableInfo.DMDImagePath, tableInfo=tableInfo if hudscreenid == ScreenNames.DMD else None)

    # Load table image (rotated and we swap width and height around like portrait mode)
    if ScreenNames.TABLE is not None:
        screens[ScreenNames.TABLE].loadImage(tableInfo.TableImagePath, tableInfo=tableInfo if hudscreenid == ScreenNames.TABLE else None)
       
def getScreens():
    logger.info("Enumerating displays")
    # Get all available screens
    monitors = get_monitors()

    hudscreenid = vpinfeIniConfig.get_int('Displays','hudscreenid', -1)
    tablescreenid = vpinfeIniConfig.get_int('Displays','tablescreenid', -1)
    hudrotangle = vpinfeIniConfig.get_int('Displays','hudrotangle', 0)
    tablerotangle = vpinfeIniConfig.get_int('Displays','tablerotangle', 0)

    for i in range(len(monitors)):
        if i == hudscreenid:
            angle = hudrotangle
        elif i == tablescreenid:
            angle = tablerotangle
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

def showCriticalErrorAndExit(title, message, exitCode):
    logger.critical(f"{RED_CONSOLE_TEXT}{message}{RESET_CONSOLE_TEXT}")
    messagebox.showerror(title, message)
    sys.exit(exitCode)

def loadconfig(configfile):
    global tableRootDir
    global vpxBinPath
    global vpinfeIniConfig

    def checkAllConfigSections(iniConfig):
        required_sections = ["Displays", "Logger", "Media", "Settings"]
        missing_sections = [
            section for section in required_sections if section not in iniConfig
        ]
        if missing_sections:
            message_start = "The following section is" if len(missing_sections) == 1 else "The following sections are"
            error_message = (
                f"{message_start} missing from the INI "
                f"file '{configfile}': " + ",".join(missing_sections)
            )
            showCriticalErrorAndExit("Configuration Error", error_message, 1)

    if configfile is None:
        configfile = "vpinfe.ini"
    try:
        vpinfeIniConfig = Config(configfile)
    except Exception as e:
        showCriticalErrorAndExit("Config Loading Error",f"{e}", 1)

    checkAllConfigSections(vpinfeIniConfig.config)

    current_dir = os.getcwd()
    logger.debug(f"Current working directory (using os.getcwd()): {current_dir}")

    # mandatory
    ScreenNames.BG = vpinfeIniConfig.get_int('Displays','bgscreenid', None)
    ScreenNames.DMD = vpinfeIniConfig.get_int('Displays','dmdscreenid', None)
    ScreenNames.TABLE = vpinfeIniConfig.get_int('Displays','tablescreenid', None)
    tableRootDir = vpinfeIniConfig.get_string('Settings','tablerootdir', None)
    vpxBinPath = vpinfeIniConfig.get_string('Settings','vpxbinpath', None)
    if any(var is None for var in [tableRootDir, vpxBinPath]):
        missing_keys = []
        if tableRootDir is None:
            missing_keys.append("tableRootDir")
        if vpxBinPath is None:
            missing_keys.append("vpxBinPath")
        message_start = "The following key is" if len(missing_keys) == 1 else "The following keys are"
        error_message = (
            f"{message_start} missing from the INI "
            f"file '{configfile}': " + ",".join(missing_keys)
        )
        showCriticalErrorAndExit("Configuration Error", error_message, 1)

    vpxBinPath = os.path.expanduser(vpxBinPath)
    if not os.path.exists(vpxBinPath):
        showCriticalErrorAndExit("Path Error", "VPX binary not found. Check your `vpxBinPath` value in vpinfe has correct path.", 1)
    
    tableRootDir = os.path.expanduser(tableRootDir)
    if not os.path.exists(tableRootDir):
        showCriticalErrorAndExit("Path Error", "Table root dir not found. Check your 'tableroot' value in vpinfe.ini has correct path.", 1)

    if all(var is None for var in [ScreenNames.BG, ScreenNames.DMD, ScreenNames.TABLE]):
        showCriticalErrorAndExit("Path Error", "You must have at least one display set in your vpinfe.ini.", 1)

def buildMetaData():
        loadconfig(configfile)
        Tables(tableRootDir, vpinfeIniConfig.config)
        vps = VPSdb(Tables.tablesRootFilePath, vpinfeIniConfig)
        for table in Tables.tables:
            finalini = {}
            meta = metaconfig.MetaConfig(table.fullPathTable + "/" + "meta.ini") # check if we want it updated!!! TODO
            
            # vpsdb
            logger.info(f"Checking VPSdb for {table.tableDirName}")
            vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
            vpsData = vps.lookupName(vpsSearchData["name"], vpsSearchData["manufacturer"], vpsSearchData["year"]) if vpsSearchData is not None else None
            if vpsData is None:
                logger.error(f"{RED_CONSOLE_TEXT}Not found in VPS{RESET_CONSOLE_TEXT}")
                continue
            
            # vpx file info
            logger.info(f"Parsing VPX file for metadata")
            logger.info(f"Extracting {table.fullPathVPXfile} for metadata.")
            vpxData = parservpx.singleFileExtract(table.fullPathVPXfile)
            
            # make the config.ini
            finalini['vpsdata'] = vpsData
            finalini['vpxdata'] = vpxData
            meta.writeConfigMeta(finalini)
            vps.downloadMediaForTable(table, vpsData['id'])

def vpxPatches():
    loadconfig(configfile)
    Tables(tableRootDir, vpinfeIniConfig.config)
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

def buildImageCacheWait():
    if task_build_cache is None:
        logger.debug("buildImageCacheWait: task_build_cache is None")
        return
    task_build_cache.wait()

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
        buildImageCacheWait()
        if ScreenNames.BG is not None:
            screens[ScreenNames.BG].loadImage(tables.getTable(i).BGImagePath, display=False)
        if shutdown_event.is_set():
            break
        buildImageCacheWait()
        if ScreenNames.DMD is not None:
            screens[ScreenNames.DMD].loadImage(tables.getTable(i).DMDImagePath, display=False)
        if shutdown_event.is_set():
            break
        buildImageCacheWait()
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
                    if button_id == vpinfeIniConfig.get_int('Settings','joyright',-1):
                        screenMoveRight()
                    elif button_id == vpinfeIniConfig.get_int('Settings','joyleft',-1):
                        screenMoveLeft()
                    elif button_id == vpinfeIniConfig.get_int('Settings','joyselect',-1):
                        for s in screens: 
                            s.window.withdraw()
                        #s.window.after(1, launchTable() )
                        launchTable()
                        break
                    elif button_id == vpinfeIniConfig.get_int('Settings','joyexit',-1):
                        logger.debug("Exit requested")
                        setShutdownEvent()
                    elif button_id == vpinfeIniConfig.get_int('Settings','joymenu',-1):
                        logger.debug("Not implemented yet...")
                    elif button_id == vpinfeIniConfig.get_int('Settings','joyback',-1):
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
    logger.info(f"VPinFE {version} by Superhac & WildCoder")
    parservpx = vpxparser.VPXParser()
    parseArgs()
    loadconfig(configfile)

    logger.info(f"Using {vpinfeIniConfig.get_string('Media','tableresolution','4k')} {vpinfeIniConfig.get_string('Media','tabletype','')}")

    update_logger_config(vpinfeIniConfig.config['Logger'])
    sdl2.ext.init()
    openJoysticks()

    tables = Tables(tableRootDir, vpinfeIniConfig.config)
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
