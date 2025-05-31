#!/usr/bin/env python3

import sys
import os
import subprocess
import argparse
import threading
import multiprocessing
from queue import Queue 
#from inputs import devices
from thirdparty.inputs import devices, get_gamepad
import time

#from pinlog import init_logger, get_logger, update_logger_config, get_named_logger
import screennames
from tables import Tables
from config import Config
import metaconfig
from vpsdb import VPSdb
import vpxparser
import standaloneScripts
from filesutils import FilesUtils
from uithread.processmanager import ProcessManager

from PyQt6.QtWidgets import (
    QApplication, QWidget, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QObject, QTimer, QEvent, QT_VERSION_STR, PYQT_VERSION_STR

from ui.fullscreenimagewindow import FullscreenImageWindow
from ui.imagecacheworker import ImageCacheWorker
from ui.imageworkermanager import ImageWorkerManager
from inputcontroller import InputController
import logging


# OS Specific
if sys.platform.startswith('win'):
    os.environ['PYSDL2_DLL_PATH'] = FilesUtils.get_asset_path("SDL2.dll") # need to include the sdl2 runtime for windows

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
timerForGamepad = QTimer()
inputController = None

# qt
workers = []
imageCacheManagers = []
app = None
screens = []
uiThreadManager = ProcessManager()

class GlobalKeyListener(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Q:
                QApplication.instance().quit()
                return True  # event handled
            if event.key() == Qt.Key.Key_M:
                FullscreenImageWindow.menuWindow.toggle_menu(rotation_degree=-90)
                return True
            if event.key() == Qt.Key.Key_Shift and event.nativeScanCode() == 50: # left
                for win in FullscreenImageWindow.windows:
                    win.prevImage()
                return True
            if event.key() == Qt.Key.Key_Shift and event.nativeScanCode() == 62: # right
                for win in FullscreenImageWindow.windows:
                    win.nextImage()
                return True
            if event.key() == Qt.Key.Key_Return: # enter
                print("lanuch", event.nativeScanCode())
                launchTable()
                return True
        return False  # pass the event on

def load_stylesheet(path):
    with open(path, 'r') as f:
        return f.read()

def launchTable():
    launchVPX(tables.getTable(imageCacheManagers[0].current_index).fullPathVPXfile)
    
    logger.debug(f"Returning from playing the table. Resetting focus on us.")

    # check if we need to do postprocessing.  right now just check if we need to delete pinmame nvram
    meta = metaconfig.MetaConfig(tables.getTable(tableIndex).fullPathTable + "/" + "meta.ini")
    meta.actionDeletePinmameNVram()

    FullscreenImageWindow.deiconify_all()

    #Screen.rootWindow.after(350, tasks_manager.resume)

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
        vpx_logger = logging.getLogger()

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
        FullscreenImageWindow.iconify_all()

    # Wait for the process to exit before continuing
    logger.debug("Waiting for the table to exit.")
    process_exited.wait()
    logger.debug(f"Exited {table}")

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

def buildMetaData(downloadMedia = True):
        loadconfig(configfile)
        logger.info(f"Building meta.ini files for tables in {tableRootDir}")
        if downloadMedia:
            logger.info("Including media download when available.")
        else:
            logger.info("Skipping media download.")
        Tables(tableRootDir, vpinfeIniConfig)
        vps = VPSdb(Tables.tablesRootFilePath, vpinfeIniConfig)
        total = len(Tables.tables)
        logger.info(f"Found {total} tables")
        current = 0
        for table in Tables.tables:
            current = current + 1
            finalini = {}
            meta = metaconfig.MetaConfig(table.fullPathTable + "/" + "meta.ini") # check if we want it updated!!! TODO

            # vpsdb
            logger.info(f"Checking VPSdb for table {current}/{total}: {table.tableDirName}")
            vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
            vpsData = vps.lookupName(vpsSearchData["name"], vpsSearchData["manufacturer"], vpsSearchData["year"]) if vpsSearchData is not None else None
            if vpsData is None:
                logger.error(f"{RED_CONSOLE_TEXT}Not found in VPS{RESET_CONSOLE_TEXT}")
                continue

            # vpx file info
            logger.debug(f"Parsing VPX file for metadata")
            logger.debug(f"Extracting {table.fullPathVPXfile} for metadata.")
            vpxData = parservpx.singleFileExtract(table.fullPathVPXfile)

            # make the config.ini
            finalini['vpsdata'] = vpsData
            finalini['vpxdata'] = vpxData
            meta.writeConfigMeta(finalini)
            if downloadMedia:
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
    parser.add_argument("--listgpads", help="Gamepads detected and ID.", action="store_true")
    parser.add_argument("--configfile", help="Configure the location of your vpinfe.ini file.  Default is cwd.")
    parser.add_argument("--buildmeta", help="Builds the meta.ini file in each table dir", action="store_true")
    parser.add_argument("--no-media", help="When building meta.ini files don't download the images at the same time.", action="store_true")
    parser.add_argument("--vpxpatch", help="Using vpx-standalone-scripts will attempt to load patches automatically", action="store_true")
    parser.add_argument("--gpadtest", help="Find your button map labels", action="store_true")

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
    elif args.listgpads:
        showGamepads()
        sys.exit()
        
    elif args.gpadtest:
        gamepadTest()
        sys.exit()

    if args.configfile:
        configfile = args.configfile

    if args.buildmeta:
        buildMetaData(False if args.no_media else True)
        sys.exit()

    if args.vpxpatch:
        vpxPatches()
        sys.exit()
        
def showGamepads():     
    for i, device in enumerate(devices.gamepads):
        logger.info(f"Gamepad Detected: {i}:{device}")
           
def setupScreens():
    global workers
    global imageCacheManagers
    menu_screenid = vpinfeIniConfig.get_int("Menu", "screenid", 0)
    menu_rotation = vpinfeIniConfig.get_int("Menu", "rotation", 0)
    # setup the window on each screen
    for i, screen in enumerate(screens):
        if i == screennames.ScreenNames.BG:
            win = FullscreenImageWindow(screen, screennames.ScreenNames.BG, tables, menuRotation=menu_rotation)
        elif i == screennames.ScreenNames.DMD:
            win = FullscreenImageWindow(screen, screennames.ScreenNames.DMD, tables, menuRotation=menu_rotation)
        elif i == screennames.ScreenNames.TABLE:
            win = FullscreenImageWindow(screen, screennames.ScreenNames.TABLE, tables, menuRotation=menu_rotation)
            
        # Add menu  to first screen
        if i == menu_screenid:
            #win.toggle_menu()
            FullscreenImageWindow.menuWindow = win
     
    # setup the image cache workers and a manager  
    for win in FullscreenImageWindow.windows:
        command_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        worker = ImageCacheWorker(tables, win.screenName, command_queue, result_queue, win.assignedScreen.geometry())
        manager = ImageWorkerManager(win, tables,  command_queue, result_queue)
        win.addCacheManager(manager)
        manager.loadLogo()
        workers.append((worker, command_queue, result_queue))
        imageCacheManagers.append(manager) 
        worker.start()

def setFirstTableImages():
    for manager in imageCacheManagers:
        manager.set_image_by_index(0)
        
def startupMessages():
    logger.info(f"VPinFE {version} by Superhac & WildCoder")
    logger.info(f"Qt version: {QT_VERSION_STR}")
    logger.info(f"PyQt version: {PYQT_VERSION_STR}")
    logger.info(f"Using {vpinfeIniConfig.get_string('Media','tableresolution','4k')} {vpinfeIniConfig.get_string('Media','tabletype','')}")
    showGamepads()

def checkForUIThreadEvents():
    responses = uiThreadManager.get_responses()
    if responses:
        for resp in responses:
            if isinstance(resp, dict) and "error" in resp:
                logger.error(f"Worker error: {resp['error']}")
                continue
            # Otherwise expect it to be a list or tuple like [worker_id, ...]
            if isinstance(resp, (list, tuple)) and len(resp) > 0:
                match resp[0]:
                    case "gamepad":
                        msg = inputController.input(resp)
                        if msg == "Quit":
                            QApplication.instance().quit()
                        elif msg == "Launch":
                            launchTable()
                    case _:
                        logger.info(f"msg from a worker has no handler.")
            else:
                logger.warning(f"Unexpected response format: {resp}")
        
def setupMainUIThreads():
    global inputController
    uiThreadManager.start_worker("gamepad", "gamepadworker.GamepadWorker")
    inputController = InputController(imageCacheManagers, vpinfeIniConfig)
    timerForGamepad.timeout.connect(checkForUIThreadEvents)
    timerForGamepad.start(200)

def gamepadTest():
    print("Gamepad Test: CRTL-C to EXIT")
    while 1:
        events = get_gamepad()
        for event in events:
            if event.ev_type == "Key" or event.ev_type == "Absolute":
                print(event.ev_type, event.code, event.state)

if __name__ == "__main__":
    logger = logging.getLogger(name="VPinFE")
    logging.basicConfig(format=u"%(levelname)s - %(message)s")
    logger.setLevel(logging.INFO)
    parservpx = vpxparser.VPXParser()
    parseArgs()
    loadconfig(configfile)
    logging.basicConfig(format=u"(%(processName)s/%(filename)s) [%(funcName)s] %(message)s", force=True)
    logger.setLevel(vpinfeIniConfig.get_int('Logger','level', "INFO").upper())
    startupMessages()
    
    app = QApplication(sys.argv)
    icon_path = FilesUtils.get_asset_path("VPinFE-icon.png")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    screens = app.screens()
    listener = GlobalKeyListener()
    app.installEventFilter(listener)
    stylesheet = load_stylesheet("default-ui-template/style/dark_theme.qss")
    app.setStyleSheet(stylesheet)
    
    tables = Tables(tableRootDir, vpinfeIniConfig)
    
    setupScreens()
    QTimer.singleShot(5000, lambda: setFirstTableImages())  # load first image after 5 secs.. logo time      
    setupMainUIThreads()
    app.exec()
    
    ### shutdown ###
    
    logger.info("Shutting down UI Thread workers...")
    uiThreadManager.shutdown()
     
    #qt image caching
    for worker, command_queue, _ in workers:
        command_queue.put('quit')   # Tell worker to clean up and exit
    for worker, _, _ in workers:
        worker.join()
    
    logger.info("VPinFE shutdown complete.")
 

    
