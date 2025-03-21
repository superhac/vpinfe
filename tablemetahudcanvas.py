import tkinter as tk
from tkinter import Canvas, PhotoImage
from PIL import Image, ImageTk, ImageDraw
import sys
import ast

from tables import Tables, TableInfo


class tableMetaHUDCanvas(tk.Canvas):
    def __init__(self, master=None, width=None, height=None, tableInfo=None, angle=0, **kwargs):
        super().__init__(master, width=width, height=height, highlightthickness=0, **kwargs)
        self.width  = width
        self.height = height
        self.angle = angle
        self.wheel = None
        self.vpsImage = None
        self.tableInfo = tableInfo
        
        if self.angle == 0:
            scaleFactor =  (1344 * 216)  / (self.width * self.height)
            
            if scaleFactor < 1:
                scaleFactor = scaleFactor+2
        else:
            scaleFactor =  (self.width * self.height) / (1344 * 216)
            
            if scaleFactor < 1:
                scaleFactor = scaleFactor+1
                
        print("scale factor: ", scaleFactor)
        print(self.angle)
        
        # scale the wheel icon to fit the height of the hud
        if self.angle !=0:
            self.wheelWidth = self.width - 20 # 20px gap
            self.wheelHeight = self.width - 20 # 20px gap
        else:
            self.wheelWidth = self.height - 20 # 20px gap
            self.wheelHeight = self.height - 20 # 20px gap
            
        vpsTextIndentPer = .20
        
        print("metacanvas: ", self.width, self.height)
        
        try:
            self.vpsImagePath = sys._MEIPASS+"/assets/vps.png"
        except Exception as e:
            print(e)
            self.vpsImagePath = "/home/superhac/working/vpinfe/assets/vps.png"
        
        # You must do this before anything.  This will wipe out any imgs on the canvas
        self.create_rusty_gradient(self.width, self.height)
        #self.create_gradient(self.width, self.height)
        master.update_idletasks()
        
        if tableInfo.WheelImagePath:
            print("Found Wheel", self.tableInfo.WheelImagePath)
            img = Image.open(self.tableInfo.WheelImagePath)
            img = img.resize((self.wheelWidth, self.wheelHeight), Image.LANCZOS)  # Resize for display
            if self.angle != 0:
                img = self.imageRotate(self.angle, img)
                self.wheel = ImageTk.PhotoImage(img)
                self.create_image(self.width/2, self.height- ( int(self.wheelHeight/2) +40), image=self.wheel, anchor=tk.CENTER)
                print("img pos", int(self.width/2), self.height- (int(self.wheelHeight/2)+40))
            else:
                self.wheel = ImageTk.PhotoImage(img)
                self.create_image((self.wheelHeight/2)+40, self.height / 2, image=self.wheel, anchor=tk.CENTER)
                print( int(self.wheelHeight/2)+40, int(self.height / 2))
            
        # vps image
        #img2 = Image.open(self.vpsImagePath)
        #img2 = img2.resize((90, 90), Image.LANCZOS)  # Resize for display
        #self.vpsImage = ImageTk.PhotoImage(img2)
        #self.create_image(vpsTextIndentPer*self.width - 50, self.height / 2 +25, image=self.vpsImage, anchor=tk.CENTER)
        
       
        #print("inside edge: ",  insideEdgeOfimage )
        
        
        
        if self.angle != 0:
            insideEdgeOfimage = self.height - ((self.wheelHeight)+ (40*scaleFactor))
            self.create_text(25, self.height/2, text=tableInfo.metaConfig['VPSdb']['name'], font=("Arial", int(18 * scaleFactor), 'bold'), angle=self.angle, anchor=tk.CENTER)
            
            self.create_text(30 * scaleFactor, insideEdgeOfimage, text=f"Manufacturer:  {tableInfo.metaConfig['VPSdb']['manufacturer']}\n"+
                            f"Year:  {tableInfo.metaConfig['VPSdb']['year']}\n"+
                            f"Type:  {tableInfo.metaConfig['VPSdb']['type']}\n"+
                            ', '.join(ast.literal_eval(tableInfo.metaConfig['VPSdb']['theme']))+'\n'+
                            f"Author(s):  {tableInfo.metaConfig['VPXFile']['author']}",
                            font=("Arial", int(11 * scaleFactor)), angle=self.angle, anchor=tk.NW)
            print("inside edge: ",  insideEdgeOfimage, "width= ", self.wheelHeight )
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        else:
            insideEdgeOfimage = self.wheelHeight + (50 * scaleFactor)
            self.create_text(self.width/2, 30* scaleFactor, text=tableInfo.metaConfig['VPSdb']['name'], font=("Arial", int(26 * scaleFactor), 'bold'), angle=self.angle, anchor=tk.CENTER)
            
            self.create_text(insideEdgeOfimage, 50 * scaleFactor, text=f"Manufacturer:  {tableInfo.metaConfig['VPSdb']['manufacturer']}\n"+
                            f"Year:  {tableInfo.metaConfig['VPSdb']['year']}\n"+
                            f"Type:  {tableInfo.metaConfig['VPSdb']['type']}\n"+
                            ', '.join(ast.literal_eval(tableInfo.metaConfig['VPSdb']['theme']))+'\n'+
                            f"Author(s):  {tableInfo.metaConfig['VPXFile']['author']}",
                            font=("Arial", int(15 * scaleFactor)), angle=self.angle, anchor=tk.NW)
            print("inside edge: ",  insideEdgeOfimage, "width= ", self.wheelHeight )
        #self.pack()  # You can choose how to pack or grid the canvas
    
    def imageRotate(self,degrees,image):
        print("img angle roatation")
        if image != None:
            return image.rotate(degrees, expand=True)
    
    def create_gradient(self, width, height):
        """Creates a radial gradient matching the uploaded VPS logo background."""
        # Create a new image with an RGBA mode
        image = Image.new("RGB", (width, height), "#000000")
        draw = ImageDraw.Draw(image)

        # Define gradient colors (approximate based on the given image)
        colors = [(120, 30, 150), (200, 100, 180), (100, 100, 200), (50, 50, 100)]  

        # Draw a radial gradient
        for i in range(width//2, 0, -1):
            r = int(colors[0][0] * i / (width//2) + colors[3][0] * (1 - i / (width//2)))
            g = int(colors[0][1] * i / (width//2) + colors[3][1] * (1 - i / (width//2)))
            b = int(colors[0][2] * i / (width//2) + colors[3][2] * (1 - i / (width//2)))
            draw.ellipse([width//2 - i, height//2 - i, width//2 + i, height//2 + i], fill=(r, g, b))

        # Convert to Tkinter-compatible image
        tk_image = ImageTk.PhotoImage(image)
        self.create_image(0, 0, anchor=tk.NW, image=tk_image)
        self.image = tk_image  # Keep reference    
            
    def create_rusty_gradient(self, width, height):
        # Define a list of colors representing rusty tones
        rust_colors = [
            "#7a4b34",  # Dark brown
            "#b76e3f",  # Rusty orange
            "#f2a14f",  # Light orange
            "#e0a56c",  # Dirty yellow
            "#b97d4b",  # Rusty brown
        ]
        
        # Create a gradient by blending colors
        for i in range(height):
            # Calculate the color blend ratio based on the current row
            ratio = i / height
            # Interpolate between two adjacent colors in the list
            color1 = rust_colors[int(ratio * (len(rust_colors) - 1))]
            color2 = rust_colors[min(int(ratio * (len(rust_colors) - 1)) + 1, len(rust_colors) - 1)]
            
            # Linear interpolation between the two colors
            r1, g1, b1 = [int(color1[j:j+2], 16) for j in (1, 3, 5)]
            r2, g2, b2 = [int(color2[j:j+2], 16) for j in (1, 3, 5)]
            
            r = int(r1 + (r2 - r1) * (ratio * (len(rust_colors) - 1) % 1))
            g = int(g1 + (g2 - g1) * (ratio * (len(rust_colors) - 1) % 1))
            b = int(b1 + (b2 - b1) * (ratio * (len(rust_colors) - 1) % 1))

            # Convert to a hex color
            color = f"#{r:02x}{g:02x}{b:02x}"

            # Draw a horizontal line across the canvas
            self.create_line(0, i, width, i, fill=color)
            
if __name__ == "__main__":
    pass