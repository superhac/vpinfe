import tkinter as tk
from screeninfo import get_monitors
from PIL import Image, ImageTk
from collections import OrderedDict

class Screen:
    screen = None
    window = None
    canvas = None
    image  = None
    photo  = None
    canvasPhotoID = None

    cache = None
    index_map = None
    current_index = 0
    maxImageCacheSize = 50
   
    #static
    firstWindow = True # tracks if this root or another top-level
    rootWindow = None

    def __init__(self, screen):
        self.text = None
        self.screen = screen
        self.cache = OrderedDict()
        self.index_map = {}  # Maps index numbers to image keys
        self.current_index = 0
        self.createWindow()
        self.canvas = tk.Canvas(self.window, width=self.window.winfo_width(), height=self.window.winfo_height())
   
    def createWindow(self):
        """Creates a fullscreen window on a specific screen."""

        if Screen.firstWindow:
            self.window = tk.Tk()
            Screen.firstWindow = False
            Screen.rootWindow = self.window
        else:
            self.window = tk.Toplevel()
        self.window.configure(bg="black")
        #win.overrideredirect(True)

        # Set window size and position
        self.window.geometry(f"{self.screen.width}x{self.screen.height}+{self.screen.x}+{self.screen.y}")
        self.window.attributes("-fullscreen", True)

    def loadImage(self, img_path, display=True ):
        if self.text != None: 
            self.removeText()

        key = img_path

        # If already in cache, move to end (most recently used) and return
        if key in self.cache:
            self.cache.move_to_end(key)
            self.displayImage(self.cache[key])
            return

        # Load and process the image
        img = Image.open(img_path).convert("RGBA") # not sure what the performance gain is here.
        img = self.resizeImageToScreen(img)
        img_tk = ImageTk.PhotoImage(img)

        # Store in cache
        self.cache[key] = img_tk
        self.cache.move_to_end(key)

        # If cache exceeds max size, remove the oldest entry
        if len(self.cache) > Screen.maxImageCacheSize:
            self.cache.popitem(last=False)  # Remove the first (oldest) item

        if display:
            self.displayImage(img_tk)

    def resizeImageToScreen(self, image):
        if image != None:
            image = image.resize((self.window.winfo_width(), self.window.winfo_height()), Image.Resampling.LANCZOS)
            return image
            #self.photo = ImageTk.PhotoImage(self.image)

    def displayImage(self, img_tk):
            if  self.canvasPhotoID == None:
                self.canvasPhotoID = self.canvas.create_image((0,0), anchor="nw", image=img_tk)
                self.canvas.config(highlightthickness=0, borderwidth=0)
            else:
                self.canvas.itemconfig(self.canvasPhotoID, image=img_tk)
            self.canvas.pack(fill="both", expand=True)
            #self.canvas.create_text(200, 150, text="Hello, Tkinter!", font=("Arial", 50), fill="white")

    def imageRotate(self,degrees):
         if self.image != None:
            self.image = self.image.rotate(90, expand=True)

    def addText(self, Text, pos):
        self.text = self.canvas.create_text(*pos, text="Hello, Tkinter!", font=("Arial", 50), fill="white")
    
    def removeText(self):
        self.canvas.delete(self.text)
