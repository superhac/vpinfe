import tkinter as tk
from screeninfo import get_monitors
from PIL import Image, ImageTk
import sys
import os
import time
import subprocess
import argparse
import sdl2
import sdl2.ext

class ScreenNames():
    BG    = None
    DMD   = None
    TABLE = None

class ImageSet:
    bg_file_path    = None
    dmd_file_path   = None
    table_file_path = None

class Screen:
    screen = None
    window = None
    canvas = None
    image  = None
    photo  = None
    canvasPhotoID = None

    def __init__(self, screen):
        self.screen = screen
        self.createWindow()
        #self.canvas = tk.Canvas(self.window, width=self.window.winfo_width(), height=self.window.winfo_height())
        #self.canvas.config(highlightthickness=0, borderwidth=0)

    def createWindow(self):
        """Creates a fullscreen window on a specific screen."""

        global firstWindow
        global rootWindow

        if firstWindow:
            self.window = tk.Tk()
            firstWindow = False
            rootWindow = self.window
        else:
            self.window = tk.Toplevel()
        self.window.configure(bg="black")
        #win.overrideredirect(True)

        # Set window size and position
        #self.screen.x, self.screen.y, width, height = screen.x, screen.y, screen.width, screen.height
        self.window.geometry(f"{self.screen.width}x{self.screen.height}+{self.screen.x}+{self.screen.y}")
        self.window.attributes("-fullscreen", True)

    def loadImage(self, img_path):
        self.image = Image.open(img_path)
        self.photo = ImageTk.PhotoImage(self.image)

    def resizeImageToScreen(self):
        self.image = self.image.resize((self.window.winfo_width(), self.window.winfo_height()), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(self.image)

    def displayImage(self):
        #self.canvas.config(highlightthickness=0, borderwidth=0)
        #self.canvas.pack(fill="both", expand=True)
        if self.canvas == None:
            self.canvas = tk.Canvas(self.window, width=self.window.winfo_width(), height=self.window.winfo_height())
            self.canvasPhotoID = self.canvas.create_image((0,0), anchor="nw", image=self.photo)
            self.canvas.config(highlightthickness=0, borderwidth=0)
        else:
            print("update img")
            self.canvas.itemconfig(self.canvasPhotoID, image=self.photo)
        self.canvas.pack(fill="both", expand=True)
        #canvas.create_text(200, 150, text="Hello, Tkinter!", font=("Arial", 50), fill="white")

    def imageRotate(self,degrees):
        self.image = self.image.rotate(90, expand=True)

# Globals
firstWindow = True # tracks if this root or another top-level
rootWindow = None
screens = []
ScreenNames = ScreenNames()
exitGamepad = False

# OS Specific
if sys.platform.startswith('win'):
    os.environ['PYSDL2_DLL_PATH'] = sys._MEIPASS+'/SDL2.dll'


def key_pressed(event):
    global imageSetIndex
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

    if keysym == "a":
        for s in screens: 
            s.window.withdraw()
        s.window.after(1, test() )

    if keysym == "b":
        for s in screens:
            s.window.deiconify()

def screenMoveRight():
    global imageSetIndex
    global exitGamepad

    if imageSetIndex != len(imageSets)-1:
        imageSetIndex += 1
        setGameDisplays(imageSets[imageSetIndex])
    else:
        imageSetIndex = 0;
        setGameDisplays(imageSets[imageSetIndex])

def screenMoveLeft():
    global imageSetIndex
    global exitGamepad

    if imageSetIndex != 0:
        imageSetIndex -= 1
        setGameDisplays(imageSets[imageSetIndex])
    else:
        imageSetIndex = len(imageSets)-1;
        setGameDisplays(imageSets[imageSetIndex])

# testing crap for minimizing windows to run vpinball
def test():
    launchVPX("/home/superhac/ROMs/vpinball/Big Indian (Gottlieb 1974).vpx")
    #time.sleep(5)
    for s in screens:
        s.window.deiconify()
        #print("loop")
        #s.window.attributes("-fullscreen", True)
    rootWindow.update()
    rootWindow.focus_force()
    print("done")

def launchVPX(table):
    null = open(os.devnull, 'w')
    subprocess.call(['/home/superhac/working/vpinball/build/VPinballX_BGFX', '-play', table], bufsize=4096, stdout=null, stderr=null)

def setGameDisplays(imageSet):
    # Load image BG
    if ScreenNames.BG is not None:
        screens[ScreenNames.BG].loadImage(imageSet.bg_file_path)
        screens[ScreenNames.BG].resizeImageToScreen()
        screens[ScreenNames.BG].displayImage() 

    # Load image DMD
    if ScreenNames.DMD is not None:
        screens[ScreenNames.DMD].loadImage(imageSet.dmd_file_path)
        screens[ScreenNames.DMD].resizeImageToScreen()
        screens[ScreenNames.DMD].displayImage()

    # load table image (rotated and we swap width and height around like portrait mode)
    if ScreenNames.TABLE is not None:
        screens[ScreenNames.TABLE].loadImage(imageSet.table_file_path)
        screens[ScreenNames.TABLE].imageRotate(90)
        screens[ScreenNames.TABLE].resizeImageToScreen()
        screens[ScreenNames.TABLE].displayImage()

sdl2.ext.init()
if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_JOYSTICK) < 0:
    print(f"SDL_InitSubSystem Error: {sdl2.SDL_GetError()}")
    exit(1)

num_joysticks = sdl2.SDL_NumJoysticks()
print(f"Number of joysticks connected: {num_joysticks}")

for i in range(num_joysticks):
    sdl2.SDL_JoystickOpen(i)

# load files
imageSets = []
basepath = sys._MEIPASS+"/bg"
for fname in os.listdir(basepath):
    path = os.path.join(basepath, fname)
    if not os.path.isdir(path):
        # skip directories
        imageSet = ImageSet()
        imageSet.bg_file_path = path
        imageSet.dmd_file_path = sys._MEIPASS+"/dmd/"+fname
        imageSet.table_file_path = sys._MEIPASS+"/table/"+fname
        imageSets.append(imageSet)

# Main application
parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument("--listres", help="ID and list your screens", action="store_true")
parser.add_argument("--bgid", help="The monitor id of the BG monitor", type=int)
parser.add_argument("--dmdid", help="The monitor id of the DMD monitor", type=int)
parser.add_argument("--tableid", help="The monitor id of the table monitor", type=int)
args = parser.parse_args()

if args.listres:
    # Get all available screens
    monitors = get_monitors()
    for i in range(len(monitors)):
        print(i,":"+str(monitors[i]))
    sys.exit()

if args.bgid is None:
    print("You must have atleast a bg and table monitor specified.")
    sys.exit()
else:
    ScreenNames.BG = args.bgid

if args.tableid is None:
    print("You must have atleast a bg and table monitor specified.")
    sys.exit()
else:
    ScreenNames.TABLE = args.tableid

if args.dmdid is not None:
     ScreenNames.DMD = args.dmdid

# Get all available screens
monitors = get_monitors()

for i in range(len(monitors)):
    screen = Screen(monitors[i])
    #screen = Screen(monitors[i], create_fullscreen_window(monitors[i]))
    screens.append(screen)
    print(i,":"+str(screen.screen))

rootWindow.bind("<Any-KeyPress>", key_pressed)
#root.withdraw()  # Hide the root window

# Ensure windows have updated dimensions
screens[0].window.update_idletasks()

# load first imageset
imageSetIndex = 0
setGameDisplays(imageSets[imageSetIndex])

# gamepad loop
while not exitGamepad:
    #time.sleep(0.001)
    if rootWindow.winfo_exists():
        rootWindow.update()
    events = sdl2.ext.get_events()
    for event in events:
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
            print(f"Button {button_id} Down on Gamepad: {event.jbutton.which}")
        elif event.type == sdl2.SDL_JOYBUTTONUP:
            button_id = event.jbutton.button
            print(f"Button {button_id} Up")

sdl2.SDL_Quit()
rootWindow.destroy()
