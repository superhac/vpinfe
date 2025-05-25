#!/usr/bin/env python3

from screeninfo import get_monitors
from PIL import Image, ImageTk
import sys
import os
import subprocess
import argparse
import sdl2.ext
import time
import threading
import multiprocessing
from queue import Queue 

from pinlog import init_logger, get_logger, update_logger_config, get_named_logger
import screennames
from imageset import ImageSet
from tables import Tables
from config import Config
import metaconfig
from vpsdb import VPSdb
import vpxparser
import standaloneScripts
from pauseabletask import PauseableTask
from pauseabletasksmanager import PauseableTasksManager
from joystickhandler import JoystickHandler
from autoclosemessagebox import AutocloseMessageBox
from assetsutils import AssetsUtils

from PyQt6 import uic
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget
)
from PyQt6.QtGui import QPixmap, QTransform, QIcon
from PyQt6.QtCore import Qt, QObject, QTimer, QEvent

from ui.fullscreenimagewindow import FullscreenImageWindow
from ui.imagecacheworker import ImageCacheWorker
from ui.imageworkermanager import ImageWorkerManager

# OS Specific
if sys.platform.startswith('win'):
    os.environ['PYSDL2_DLL_PATH'] = AssetsUtils.get_path("SDL2.dll") # need to include the sdl2 runtime for windows

# Assets
logoImage = AssetsUtils.get_path("VPinFE_logo_main.png")
missingImage = AssetsUtils.get_path("file_missing.png")

# Globals
version = "0.5 beta"
logger = None
parservpx = None
#screens = []
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
tasks_manager = None # Global instance for PauseableTasksManager
button_actions = {}
tables = None

# qt
workers = []
managers = []
app = None
screens = []

class GlobalKeyListener(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Q:
                QApplication.instance().quit()
                return True  # event handled
            if event.key() == Qt.Key.Key_M:
                FullscreenImageWindow.menuWindow.add_rotated_menu(rotation_degree=-90)
                return True
            if event.key() == Qt.Key.Key_Shift and event.nativeScanCode() == 50: # left
                print("left:", event.nativeScanCode())
                for manager in managers:
                    manager.load_previous()
                #tableIndex -= 1
                return True
            if event.key() == Qt.Key.Key_Shift and event.nativeScanCode() == 62: # right
                print("right:", event.nativeScanCode())
                for manager in managers:
                    manager.load_next()
                #tableIndex += 1
                return True
            if event.key() == Qt.Key.Key_Return: # enter
                print("lanuch", event.nativeScanCode())
                launchTable()
                return True
        return False  # pass the event on

def load_stylesheet(path):
    with open(path, 'r') as f:
        return f.read()

def setShutdownEvent():
    if shutdown_event.is_set():
        return
    logger.debug("Exit requested")
    shutdown_event.set()
    shutDownMsg()

def key_pressed(event):
    keysym = event.keysym # Get the symbolic name of the key
    #key = event.char # Get the character representation of the key
    #keycode = event.keycode # Get the numeric keycode
    #logger.debug(f"Key pressed: {key}, keysym: {keysym}, keycode: {keycode}")
    key_actions = {
        "Shift_R": screenMoveRight,
        "Shift_L": screenMoveLeft,
        "Escape": setShutdownEvent,
        "q": setShutdownEvent,
        "Return": launchTable,
        "a": launchTable
    }

    action = key_actions.get(keysym)
    if action:
        action()

def button_pressed(payload):
    global button_actions

    action = button_actions.get(payload['button'])
    if action:
        action()
    logger.debug(f"Button {payload['button']} Down on Gamepad: {payload['which']}")

def buttonActionsSetup():
    global button_actions

    def not_implemented(button):
        logger.debug(f"Button {button} Not implemented yet...")

    button_actions = {
        vpinfeIniConfig.get_int('Settings', 'joyright', -1): screenMoveRight,
        vpinfeIniConfig.get_int('Settings', 'joyleft', -2): screenMoveLeft,
        vpinfeIniConfig.get_int('Settings', 'joyselect', -3): launchTable,
        vpinfeIniConfig.get_int('Settings', 'joyexit', -4): setShutdownEvent,
        vpinfeIniConfig.get_int('Settings', 'joymenu', -5): lambda: not_implemented("joymenu"),
        vpinfeIniConfig.get_int('Settings', 'joyback', -6): lambda: not_implemented("joyback")
    }

    if len(button_actions) != 6:
        showError("Input Configuration Error", "It appears that you have some identical buttons defined multiple times. Please make sure they are unique or empty in vpinfe.ini.")

def processTkMsgEvent(event):
    while not tkMsgQueue.empty():
        msg = tkMsgQueue.get()

        if msg.msgType == TKMsgType.CACHE_BUILD_COMPLETED:
            disableStatusMsg
        elif msg.msgType == TKMsgType.SHUTDOWN:
            setShutdownEvent()
        elif msg.msgType == TKMsgType.JOY_BUTTON_DOWN:
            button_pressed(msg.payload)
        #elif msg.msgType == TKMsgType.JOY_BUTTON_UP:
            #logger.info(f"Received JOY_BUTTON_UP {msg.payload['button']} from joystick {msg.payload['which']}")
    pass

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

def resetFocus():
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

def launchTable():
    global background
    background = True  # Disable SDL gamepad events
    tasks_manager.pause()
    launchVPX(tables.getTable(tableIndex).fullPathVPXfile)
    logger.debug(f"Returning from playing the table. Resetting focus on us.")

    # check if we need to do postprocessing.  right now just check if we need to delete pinmame nvram
    meta = metaconfig.MetaConfig(tables.getTable(tableIndex).fullPathTable + "/" + "meta.ini")
    meta.actionDeletePinmameNVram()

    resetFocus()

    Screen.rootWindow.after(350, tasks_manager.resume)

def launchVPX(table):
    logger.info(f"Launching: {table}")

    def iconify_all_windows(reason):
        logger.debug(f"Iconifying windows due to {reason}")
        FullscreenImageWindow.iconify_all()

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

def showError(title, message):
    root = screens[vpinfeIniConfig.get_int('Displays','messagesscreenid', 0)].window
    logger.error(f"{RED_CONSOLE_TEXT}{message}{RESET_CONSOLE_TEXT}")
    msg_box = AutocloseMessageBox(root, title, message, delay_s=15)
    msg_box.show()
    resetFocus()

def showCriticalErrorAndExit(title, message, exitCode):
    root = screens[vpinfeIniConfig.get_int('Displays','messagesscreenid', 0)].window
    logger.critical(f"{RED_CONSOLE_TEXT}{message}{RESET_CONSOLE_TEXT}")
    msg_box = AutocloseMessageBox(Screen.rootWindow, title, message, delay_s=15)
    msg_box.show()
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
    screennames.ScreenNames.BG = vpinfeIniConfig.get_int('Displays','bgscreenid', None)
    screennames.ScreenNames.DMD = vpinfeIniConfig.get_int('Displays','dmdscreenid', None)
    screennames.ScreenNames.TABLE = vpinfeIniConfig.get_int('Displays','tablescreenid', None)
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

    if all(var is None for var in [screennames.ScreenNames.BG, screennames.ScreenNames.DMD, screennames.ScreenNames.TABLE]):
        showCriticalErrorAndExit("Path Error", "You must have at least one display set in your vpinfe.ini.", 1)

def buildMetaData():
        loadconfig(configfile)
        Tables(tableRootDir, vpinfeIniConfig)
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
    Tables(tableRootDir, vpinfeIniConfig)
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
        app = QApplication(sys.argv)
        screens = app.screens()
        
        for i, screen in enumerate(screens):
            logger.info(
                f"Screen {i}: Name={screen.name()}, "
                f"Size={screen.size().width()}x{screen.size().height()}, "
                f"Geometry={screen.geometry()}, "
                f"AvailableGeometry={screen.availableGeometry()}, "
                f"LogicalDPI={screen.logicalDotsPerInch():.2f}, "
                f"PhysicalDPI={screen.physicalDotsPerInch():.2f}, "
                f"RefreshRate={screen.refreshRate():.2f}Hz, "
                f"Depth={screen.depth()} bits, "
                f"DevicePixelRatio={screen.devicePixelRatio():.2f}"
            )
        sys.exit()

    if args.configfile:
        configfile = args.configfile

    if args.buildmeta:
        buildMetaData()
        sys.exit()

    if args.vpxpatch:
        vpxPatches()
        sys.exit()

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
    loadImageAllScreens(logoImage)
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].addStatusText("Caching Images", (10,1034))
        screens[ScreenNames.BG].textThreeDotAnimate()
    # Add the task to the manager
    tasks_manager.add(name="buildImageCache", target_func=buildImageCacheThread)
    tasks_manager.start("buildImageCache") # Start the task via the manager

def buildImageCacheThread():
    for i in range(Screen.maxImageCacheSize):
        if i == tables.getTableCount():
            tkMsgQueue.put(TkMsg(MsgType=TKMsgType.CACHE_BUILD_COMPLETED, func=disableStatusMsg))
            break
        if shutdown_event.is_set():
            break
        tasks_manager.wait("buildImageCache") # Use manager to wait
        if ScreenNames.BG is not None:
            screens[ScreenNames.BG].loadImage(tables.getTable(i).BGImagePath, display=False)
        if shutdown_event.is_set():
            break
        tasks_manager.wait("buildImageCache") # Use manager to wait
        if ScreenNames.DMD is not None:
            screens[ScreenNames.DMD].loadImage(tables.getTable(i).DMDImagePath, display=False)
        if shutdown_event.is_set():
            break
        tasks_manager.wait("buildImageCache") # Use manager to wait
        if ScreenNames.TABLE is not None:
            screens[ScreenNames.TABLE].loadImage(tables.getTable(i).TableImagePath, display=False)

    Screen.rootWindow.event_generate("<<vpinfe_tk>>")

    logger.debug("Exiting buildImageCacheThread")
    
def setupScreens():
    global workers
    global managers
    menu_screenid = vpinfeIniConfig.get_int("Menu", "screenid", 0)
    menu_rotation = vpinfeIniConfig.get_int("Menu", "rotation", 0)
    # setup the window on each screen
    for i, screen in enumerate(screens):
        if i == screennames.ScreenNames.BG:
            win = FullscreenImageWindow(screen, screennames.ScreenNames.BG, tables)
        elif i == screennames.ScreenNames.DMD:
            win = FullscreenImageWindow(screen, screennames.ScreenNames.DMD, tables)
        elif i == screennames.ScreenNames.TABLE:
            win = FullscreenImageWindow(screen, screennames.ScreenNames.TABLE, tables)
            
        # Add menu  to first screen
        if i == menu_screenid:
            win.add_menu(rotation_degree=menu_rotation)
            FullscreenImageWindow.menuWindow = win
     
    # setup the image cache workers and a manager  
    for win in FullscreenImageWindow.windows:
        command_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        worker = ImageCacheWorker(tables, win.screenName, command_queue, result_queue, win.screen.geometry())
        manager = ImageWorkerManager(win, tables,  command_queue, result_queue)
        manager.set_image_by_index(0)  # Show first image #############################################################################
        workers.append((worker, command_queue, result_queue))
        managers.append(manager) 
        worker.start()

if __name__ == "__main__":
    logger = init_logger("VPinFE")
    logger.info(f"VPinFE {version} by Superhac & WildCoder")
    parservpx = vpxparser.VPXParser()
    parseArgs()
    loadconfig(configfile)

    logger.info(f"Using {vpinfeIniConfig.get_string('Media','tableresolution','4k')} {vpinfeIniConfig.get_string('Media','tabletype','')}")

    update_logger_config(vpinfeIniConfig.config['Logger'])
    
    app = QApplication(sys.argv)
    icon_path = AssetsUtils.get_path("VPinFE-icon.png")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    screens = app.screens()
    listener = GlobalKeyListener()
    app.installEventFilter(listener)
    stylesheet = load_stylesheet("default-ui-template/style/dark_theme.qss")
    app.setStyleSheet(stylesheet)

    sdl2.ext.init()
    logger.debug("SDL2 initialized.")

    tables = Tables(tableRootDir, vpinfeIniConfig)
        
    buttonActionsSetup()
    tasks_manager = PauseableTasksManager()

    # Add and start the gamepad input task
    #joystick_handler = JoystickHandler(tkMsgQueue, shutdown_event, tasks_manager)
    #tasks_manager.add(name="gameControllerInput", target_func=joystick_handler.input_loop)
    #tasks_manager.start("gameControllerInput")
    
    setupScreens()      
    app.exec()
    
    ### shutdown ###
    
    # stop tasks
    logger.info("Stopping async tasks.")
    #tasks_manager.stop()

    # SDL 
    logger.info("SDL2 Quit.")
    sdl2.ext.quit()
    
    #qt image caching
    for worker, command_queue, _ in workers:
        command_queue.put('quit')   # Tell worker to clean up and exit
    for worker, _, _ in workers:
        worker.join()

    logger.info("VPinFE shutdown complete.")
 

    
