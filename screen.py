import tkinter as tk
from screeninfo import get_monitors
from PIL import Image, ImageTk
from collections import OrderedDict
import time

from tablemetahudcanvas import tableMetaHUDCanvas

class Screen:
    maxImageCacheSize = 100
    firstWindow = True # tracks if this root or another top-level
    rootWindow = None

    def __init__(self, screen, missingImage, vpinfeIniConfig):
        self.isThreeDotAnimate = False
        self.threeDotCount = 0
        
        self.missingImage = missingImage
        self.vpinfeIniConfig = vpinfeIniConfig
        self.text = None
        self.statusText = None
        self.screen = screen
        self.window = None
        
        self.cache = OrderedDict()
        self.index_map = {}  # Maps index numbers to image keys
        self.current_index = 0
        
        self.canvasPhotoID = None
        self.textPos = None
        self.originalText = None
        self.originalStatusText = None
        
        self.hudCanvas = None

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
        
        # Set window size and position
        self.window.geometry(f"{self.screen.width}x{self.screen.height}+{self.screen.x}+{self.screen.y}")
        self.window.attributes("-fullscreen", True)

    def loadImage(self, img_path, tableInfo=None, display=True):
        if self.text != None and display: 
             self.removeText()

        key = img_path
        
        # If already in cache, move to end (most recently used) and return
        if key in self.cache:
            self.cache.move_to_end(key)
            if display:
                self.addHUD(tableInfo)
                self.displayImage(self.cache[key])
            return

        # Load and process the image
        try:
            img = Image.open(img_path)#.convert("RGBA") # not sure what the performance gain is here.
        except:
            img = Image.open(self.missingImage)#.convert("RGBA") # not sure what the performance gain is here.
 
        width, height = img.size
        if width != self.window.winfo_width() and height != self.window.winfo_height():
            img = self.resizeImageToScreen(img)
        
        img_tk = ImageTk.PhotoImage(img)

        # Store in cache
        self.cache[key] = img_tk
        self.cache.move_to_end(key)

        # If cache exceeds max size, remove the oldest entry
        if len(self.cache) > Screen.maxImageCacheSize:
            self.cache.popitem(last=False)  # Remove the first (oldest) item

        if display:
            self.addHUD(tableInfo)
            self.displayImage(img_tk)

    def resizeImageToScreen(self, image):
        if image != None:
            image = image.resize((self.window.winfo_width(), self.window.winfo_height()), Image.Resampling.LANCZOS)
            return image
           
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

    def addText(self, text, pos, anchor="nw"):
        self.text = self.canvas.create_text(*pos, anchor=anchor, text=text, font=("Arial", 30), fill="white")
        self.originalText = text 
        self.textPos = pos
        self.canvas.update()
    
    def removeText(self):
        self.canvas.delete(self.text)
        self.originalText = None

    def update_text(self,text):
        self.canvas.itemconfig(self.text, text=text)
        self.originalText = text 

    def getText(self):
        return self.text
    
    def addStatusText(self, text, pos, anchor="nw"):
        self.statusText = self.canvas.create_text(*pos, anchor=anchor, text=text, font=("Arial", 30), fill="white")
        self.originalStatusText = text 
        self.textPos = pos
        self.canvas.update()
    
    def removeStatusText(self):
        self.canvas.delete(self.statusText)
        self.originalStatusText = None

    def updateStatusText(self,text):
        self.canvas.itemconfig(self.statusText, text=text)
        self.originalStatusText = text 

    def getStatusText(self):
        return self.statusText
    
    def textThreeDotAnimateCall(self):
        if self.isThreeDotAnimate:
            if self.threeDotCount < 3:
                self.threeDotCount = self.threeDotCount + 1
            else: # reset to zero
                self.threeDotCount = 0
            newText = self.originalStatusText+"."*self.threeDotCount
            self.canvas.itemconfig(self.statusText, text= newText)
            self.canvas.update()
            self.canvas.after(500, self.textThreeDotAnimateCall)
        else:
            self.threeDotCount = 0
    
    def textThreeDotAnimate(self, enabled=True):
        self.isThreeDotAnimate = enabled
        if enabled:
            self.textThreeDotAnimateCall()  # Only start if enabled
            
    def addHUD(self, tableInfo):
        if tableInfo:
            # hud size.  percent of total window size
            barLength = .70
            barHeight = .10
            if self.vpinfeIniConfig.config['Displays']['hudrotangle'] == '':
                self.hudCanvas = tableMetaHUDCanvas(self.window, int(self.window.winfo_width()*barLength), int(self.window.winfo_height()* (barHeight+.10)),tableInfo=tableInfo)
                self.hudCanvas.place(x=int(self.window.winfo_width()/2), y=self.window.winfo_height() - 50 , anchor="s")  # Adjust placement
            else: # swap width and height, add angle of rotation
                print("hud rotation set")
                self.hudCanvas = tableMetaHUDCanvas(self.window, int(self.window.winfo_width()*barHeight), int(self.window.winfo_height()*barLength),tableInfo=tableInfo, angle=int(self.vpinfeIniConfig.config['Displays']['hudrotangle']))
                self.hudCanvas.place(x=int(self.window.winfo_width() - 50 ), y=self.window.winfo_height() /2 , anchor="e")  # Adjust placement