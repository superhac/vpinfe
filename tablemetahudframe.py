import tkinter as tk
from tkinter import Label
from tkinter import font as tkfont
from PIL import Image, ImageTk
import sys
import ast

from tables import Tables, TableInfo
from log import get_logger

class TableMetaHUDFrame(tk.Frame):
    logger = None

    def __init__(self, master=None, width=None, height=None, tableInfo=None, angle=0, **kwargs):
        super().__init__(master, width=width, height=height, **kwargs)
        global logger
        logger = get_logger()

        self.width = width
        self.height = height
        self.angle = angle
        self.wheel = None
        self.vpsImage = None
        self.tableInfo = tableInfo
        
        self.ssIconPath = None
        self.emIconPath = None        
        self.tableTypeIcon = None
        self.pupIconImg = None
        
        self.yearFont = None
        self.manufacturerFont = None
                
        # debug
        logger.debug(f"HUD frame rotation set to {self.angle}")
        logger.debug(f"HUD master frame: {self.width}x{self.height}")
        
        # load any imgs
        try:
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                self.ssIconPath = sys._MEIPASS + "/assets/solidstate-icon.png"
                self.emIconPath = sys._MEIPASS + "/assets/electrom-icon.png"
            else:
                self.ssIconPath = "assets/solidstate-icon.png"
                self.emIconPath = "assets/electrom-icon.png"
        except Exception as e:
            Logger.error(e)
        
        # set bg color
        self.configure(bg="#453a3c")
        
        if self.angle == 0:
                scaleFactor =  (1344 * 216)  / (self.width * self.height)
                
                if scaleFactor < 1:
                    scaleFactor = scaleFactor+2
        else:
            scaleFactor =  (self.width * self.height) / (1344 * 216)
            
            if scaleFactor < 1:
                scaleFactor = scaleFactor+1
       
        self.setWheelSize()
        
        # setup the main frame columns
        self.WHEEL_COL = 0
        self.YEAR_MANUF = 1
        self.TABLE_FEATURES = 3
        self.TABLE_NAME_AUTHOR = 2
        self.LAST_UNUSED = 3
        
        # make master frame a grid
        self.columnconfigure(self.WHEEL_COL, weight=0)
        self.rowconfigure(0, weight=1) # expand to fit vertically 
        self.columnconfigure(self.YEAR_MANUF, weight=0)
        self.rowconfigure(1, weight=1) # expand to fit vertically 
        self.columnconfigure(self.TABLE_FEATURES, weight=0)
        self.rowconfigure(self.TABLE_FEATURES, weight=0) # expand to fit vertically 
        self.columnconfigure(self.TABLE_NAME_AUTHOR, weight=1)
        #self.columnconfigure(self.LAST_UNUSED, weight=0)
        
        # make col1 a grid - WHEEL
        wheelFrame = tk.Frame(self, bg=self["bg"])
        wheelFrame.columnconfigure(self.WHEEL_COL,  weight=0)
        wheelFrame.rowconfigure(0, weight=1) # expand to fit vertically
        wheelFrame.rowconfigure(1, weight=1) # expand to fit vertically 
        wheelFrame.grid(row=0, column=self.YEAR_MANUF, sticky=tk.NSEW)
        
        # make col2 - Table Features
        tableFeatureFrame = tk.Frame(self, bg=self["bg"])
        tableFeatureFrame.columnconfigure(0, weight=1)
        tableFeatureFrame.rowconfigure(0, weight=0 ) # expand to fit vertically - last row sticks to bottom
        tableFeatureFrame.grid(row=0, column=self.TABLE_FEATURES, sticky=tk.NSEW)
        
        # make col3 a grid - tablename and authors
        tableAuthorFrame = tk.Frame(self, bg=self["bg"])
        tableAuthorFrame.columnconfigure(0, weight=1)
        tableAuthorFrame.rowconfigure(0, weight=0) # expand to fit vertically
        tableAuthorFrame.rowconfigure(1, weight=0) # expand to fit vertically 
        tableAuthorFrame.grid(row=0, column=self.TABLE_NAME_AUTHOR, sticky=tk.NSEW)
                            
        # Load the wheel image
        if not tableInfo.WheelImagePath:
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                tableInfo.WheelImagePath = sys._MEIPASS + "/assets/wheel-missing.png"
            else:
                tableInfo.WheelImagePath = "assets/wheel-missing.png"
        logger.debug(f"Found Wheel {self.tableInfo.WheelImagePath}")
        img = Image.open(self.tableInfo.WheelImagePath)
        img = img.resize((self.wheelWidth, self.wheelHeight), Image.LANCZOS)
        img = self.imageRotate(img, self.angle)
        self.wheel = ImageTk.PhotoImage(img)
        wheel_label = Label(self, image=self.wheel, bg=self["bg"])         
        wheel_label.grid(row = 0, column=self.WHEEL_COL, padx=5 , sticky=tk.NSEW)
        
        # set manufacturer year
        self.yearFont = tkfont.Font(family="Arial", size=30)
        try:
            label = Label(wheelFrame, text=tableInfo.metaConfig['VPSdb']['year'], font=self.yearFont, bg=self["bg"], fg="white")
        except KeyError as e:
             label = Label(wheelFrame, text="    ", font=self.yearFont, bg=self["bg"], fg="white")
             logger.error(f"Missing year in {tableInfo.fullPathTable}")
        label.grid(row=0, column=0, sticky="nsew")
        #label.bind("<Configure>", self.resize_font)
        
         # set table type Icon
        self.setTableTypeIcon()
        icon_label = Label(wheelFrame, image=self.tableTypeIcon, bg=self["bg"])         
        icon_label.grid(row = 1, column=0, padx=5, pady=5, sticky=tk.NSEW)
        
        # set manufacturer 
        self.manufacturerFont = tkfont.Font(family="Arial", size=30)
        if self.tableHasMetadata():
            label = Label(wheelFrame, text=tableInfo.metaConfig['VPSdb']['manufacturer'], font=self.manufacturerFont, bg=self["bg"], fg="white")
            label.grid(row=2, column=0, sticky="nsew")
        
            # Table Title
            Label(tableAuthorFrame, text=tableInfo.metaConfig['VPSdb']['name'], font=("Arial", int(26 * scaleFactor), 'bold'),
                fg="#dce1e3", bg=self["bg"]).grid(row = 0, column=0, sticky="nsew" ) #bg=self["bg"]

            # Author(s)
            Label(tableAuthorFrame, text="By "+tableInfo.metaConfig['VPXFile']['author'], font=("Arial", int(16 * scaleFactor), 'bold'),
                fg="#dce1e3", bg=self["bg"]).grid(row = 1, column=0, sticky="nsew") #bg=self["bg"]

            #vps data
            details_text = (
                f"Theme: {', '.join(ast.literal_eval(tableInfo.metaConfig['VPSdb']['theme']))}"
            )
            Label(tableAuthorFrame, text=details_text, font=("Arial", int(12 * scaleFactor)), fg="white", bg=self["bg"], justify="left").grid(row = 3, column=0, sticky="nsew")
        
        # Table features and Addon buttons
         
        # Create a nested frame for grouping the icons side-by-side
        iconGroupFrame = tk.Frame(tableFeatureFrame, bg=self["bg"])               
        iconGroupFrame.grid(row=0, column=0, padx=20, sticky=tk.NSEW)
        
        Label(iconGroupFrame, text="Table Features", font=("Arial", int(12 * scaleFactor)), fg="white", bg=self["bg"], justify="center").grid(row = 0, column=0, columnspan=2)

        if self.tableHasMetadata():
            tk.Button(iconGroupFrame, text ="Fleep", highlightthickness = 0, bg= "green" if tableInfo.metaConfig['VPXFile']['detectFleep'] == 'true' else "red").grid(row = 1, column=0,sticky="nsew")
            tk.Button(iconGroupFrame, text ="Nfozzy", highlightthickness = 0,bg= "green" if tableInfo.metaConfig['VPXFile']['detectNfozzy'] == 'true' else "red").grid(row = 1, column=1, sticky="nsew")
            tk.Button(iconGroupFrame, text ="SSF", highlightthickness = 0,bg= "green" if tableInfo.metaConfig['VPXFile']['detectSSF'] == 'true' else "red").grid(row = 2, column=0,sticky="nsew")
            tk.Button(iconGroupFrame, text ="FastFlips", highlightthickness = 0,bg= "green" if tableInfo.metaConfig['VPXFile']['detectFastflips'] == 'true' else "red").grid(row = 2, column=1,sticky="nsew")
            tk.Button(iconGroupFrame, text ="LUT", highlightthickness = 0,bg= "green" if tableInfo.metaConfig['VPXFile']['detectLut'] == 'true' else "red").grid(row = 3, column=0,sticky="nsew")
            tk.Button(iconGroupFrame, text ="Scorebit", highlightthickness = 0,bg= "green" if tableInfo.metaConfig['VPXFile']['detectScorebit'] == 'true' else "red").grid(row = 3, column=1,sticky="nsew")
        
        # addons
        Label(iconGroupFrame, text="Table Addon's", font=("Arial", int(12 * scaleFactor)), fg="white", bg=self["bg"], justify="center").grid(row = 4, column=0, columnspan=2)
        tk.Button(iconGroupFrame, text ="AltSound", highlightthickness = 0,bg= "green" if tableInfo.altSoundExists == True else "red").grid(row = 5, column=0,sticky="nsew")
        tk.Button(iconGroupFrame, text ="AltColor", highlightthickness = 0,bg= "green" if tableInfo.altColorExists == True else "red").grid(row = 5, column=1, sticky="nsew")
        tk.Button(iconGroupFrame, text ="PupPack", highlightthickness = 0,bg= "green" if tableInfo.pupPackExists == True else "red").grid(row = 6, column=0,sticky="nsew")

    def imageRotate(self, image, degrees):
        # TODO: this a copy of the function in screen.py Figure out how to clean that up in python.
        if image is None or degrees == 0:
            return image
        logger.debug(f"Rotating HUD image by {degrees} degrees...")
        image = image.rotate(degrees, expand=True)
        return image

    def tableHasMetadata(self):
        if self.tableInfo.metaConfig is None or not 'VPSdb' in self.tableInfo.metaConfig:
            logger.warning(f"Missing metadata for table {tableInfo.fullPathVPXfile}. Run with --buildmeta")
            return False
        return True

    def setTableTypeIcon(self):
        if not self.tableHasMetadata():
            return
        if self.tableInfo.metaConfig['VPSdb']['type'] == "SS":
            img = Image.open(self.ssIconPath)
            img = img.resize((100, 100), Image.LANCZOS)
            img = self.imageRotate(img, self.angle)
            self.tableTypeIcon = ImageTk.PhotoImage(img)
        elif self. tableInfo.metaConfig['VPSdb']['type'] == "EM":
            img = Image.open(self.emIconPath)
            img = img.resize((100, 100), Image.LANCZOS)
            img = self.imageRotate(img, self.angle)
            self.tableTypeIcon = ImageTk.PhotoImage(img)
            
    def setWheelSize(self):
        # Determine the size of the wheel image
        if self.angle != 0:
            self.wheelWidth = int(self.width * .90)
            self.wheelHeight = int(self.width * .90)
        else:
            self.wheelWidth = int(self.height * .90)
            self.wheelHeight = int(self.height * .90)
            
    def resize_font(self,event):
        # Calculate font size based on label height
        new_size = max(8, int(event.height / 2))  # Prevent font from becoming too small
        self.yearFont.configure(size=new_size)

if __name__ == "__main__":
    pass
