import tkinter as tk
from screeninfo import get_monitors
from PIL import Image, ImageTk

class Screen:
    screen = None
    window = None
    canvas = None
    image  = None
    photo  = None
    canvasPhotoID = None

    #static
    firstWindow = True # tracks if this root or another top-level
    rootWindow = None

    @staticmethod
    def a_method():
        pass

    def __init__(self, screen):
        self.screen = screen
        self.createWindow()
   
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

    def loadImage(self, img_path):
        self.image = Image.open(img_path)
        self.photo = ImageTk.PhotoImage(self.image)

    def resizeImageToScreen(self):
        self.image = self.image.resize((self.window.winfo_width(), self.window.winfo_height()), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(self.image)

    def displayImage(self):
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
