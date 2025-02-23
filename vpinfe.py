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

from screennames import ScreenNames
from imageset import ImageSet
from screen import Screen
from tables import Tables

# OS Specific
if sys.platform.startswith('win'):
    os.environ['PYSDL2_DLL_PATH'] = sys._MEIPASS+'/SDL2.dll' # need to include the sdl2 runtime for windows

# Globals
screens = []
ScreenNames = ScreenNames()
exitGamepad = False
background = False
tableRootDir = None
vpxBinPath = None
tableIndex = 0

def key_pressed(event):
    global tableIndex
    global exitGamepad
    key = event.char # Get the character representation of the key
    keysym = event.keysym # Get the symbolic name of the key
    keycode = event.keycode # Get the numeric keycode
    print(f"Key pressed: {key}, keysym: {keysym}, keycode: {keycode}")

    if keysym == "Shift_R":
        screenMoveRight()
    if keysym == "Shift_L":
        screenMoveLeft()
    if keysym == "Escape":
        exitGamepad = True # exit the gamepad loop

    # testing stuff
    if keysym == "a":
        for s in screens: 
            s.window.withdraw()
        s.window.after(1, launchTable() )

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

# testing crap for minimizing windows to run vpinball
def launchTable():
    global background
    background = True # # Disable SDL gamepad events
    launchVPX(tables.getTable(tableIndex).fullPathVPXfile)
    for s in screens:
        s.window.deiconify()
        #print("loop")
        #s.window.attributes("-fullscreen", True)
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
        #screens[ScreenNames.BG].resizeImageToScreen()
        #screens[ScreenNames.BG].displayImage() 

    # Load image DMD
    if ScreenNames.DMD is not None:
        screens[ScreenNames.DMD].loadImage(tableInfo.DMDImagePath)
        #screens[ScreenNames.DMD].resizeImageToScreen()
        #screens[ScreenNames.DMD].displayImage()

    # load table image (rotated and we swap width and height around like portrait mode)
    if ScreenNames.TABLE is not None:
        screens[ScreenNames.TABLE].loadImage(tableInfo.TableImagePath)
        #screens[ScreenNames.TABLE].imageRotate(90)
        #screens[ScreenNames.TABLE].resizeImageToScreen()
        #screens[ScreenNames.TABLE].displayImage()

def getScreens():
    # Get all available screens
    monitors = get_monitors()

    for i in range(len(monitors)):
        screen = Screen(monitors[i])
        screens.append(screen)
        print(i,":"+str(screen.screen))

def openJoysticks():
    if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_JOYSTICK) < 0:
        print(f"SDL_InitSubSystem Error: {sdl2.SDL_GetError()}")
        return

    num_joysticks = sdl2.SDL_NumJoysticks()
    print(f"Number of joysticks connected: {num_joysticks}")

    for i in range(num_joysticks):
        sdl2.SDL_JoystickOpen(i)

def parseArgs():
    global tableRootDir
    global vpxBinPath

    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--listres", help="ID and list your screens", action="store_true")
    parser.add_argument("--bgid", help="The monitor id of the BG monitor", type=int)
    parser.add_argument("--dmdid", help="The monitor id of the DMD monitor", type=int)
    parser.add_argument("--tableid", help="The monitor id of the table monitor", type=int)
    parser.add_argument("--tableroot", help="Root table directory (mandatory)")
    parser.add_argument("--vpxbin", help="Full Path to your VPX binary (mandatory)")

    args = parser.parse_args()

    if args.listres:
        # Get all available screens
        monitors = get_monitors()
        for i in range(len(monitors)):
            print(i,":"+str(monitors[i]))
        sys.exit()

    if args.bgid is not None:
        ScreenNames.BG = args.bgid

    if args.tableid is not None:
        ScreenNames.TABLE = args.tableid

    if args.dmdid is not None:
        ScreenNames.DMD = args.dmdid
    
    if args.vpxbin is None:
        print("--vpxbin is required.  e.g. /home/yourdir/vpinball/build/VPinballX_BGFX")
        sys.exit()
    else:
        if not os.path.exists(args.vpxbin):
            print("VPX binary not found.  Check your --vpxbin argument has correct path")
            sys.exit()
        vpxBinPath = args.vpxbin
    if args.tableroot is None:
        print("--tableroot is required.  e.g. /home/yourdir/tables")
        sys.exit()
    else:
        if not os.path.exists(args.tableroot):
            print("Table root dir not found.  Check your --tableroot argument has correct path")
            sys.exit()
        tableRootDir = args.tableroot

def buildImageCache():
    maxImagesToCache = 10
    for i in range(maxImagesToCache):
        if i == tables.getTableCount(): # breakout if theres less tables then cache max
            break
        screens[ScreenNames.BG].loadImage(tables.getTable(i).BGImagePath, display=False)
        screens[ScreenNames.DMD].loadImage(tables.getTable(i).DMDImagePath, display=False)
        screens[ScreenNames.TABLE].loadImage(tables.getTable(i).TableImagePath, display=False)
    
# Main Application
sdl2.ext.init()
openJoysticks()
parseArgs()
tables = Tables(tableRootDir)
getScreens()
buildImageCache()

Screen.rootWindow.bind("<Any-KeyPress>", key_pressed)
#root.withdraw()  # Hide the root window

# Ensure windows have updated dimensions
screens[0].window.update_idletasks()

# load first tables images
setGameDisplays(tables.getTable(tableIndex))

# gamepad loop
while not exitGamepad:
    #time.sleep(0.001)
    if Screen.rootWindow.winfo_exists():
        Screen.rootWindow.update()
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
                print(f"Axis {axis_id}: {axis_value}")
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
                print(f"Button {button_id} Up")
    
# shutdown
sdl2.SDL_Quit()
Screen.rootWindow.destroy()
