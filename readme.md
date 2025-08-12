# VPinFE
![VPinFE_logo_main](https://github.com/user-attachments/assets/507c50e3-bc1e-499a-b393-f9d11250b709)

**A frontend for vpinball with the following features:**
- Works on Linux, Windows, and Mac (Windows currently needs updates for VPX compatibility)
- Multiscreen - Supports up to 3 screens (Backglass, DMD, and Table)
- Keyboard & Joystick support
- Table and Media Manager all built in
- Automatic vpx patching for Linux & Mac
- Fully customizable UI themeing using HTML, JS and CSS

Cab Mode (Three Screens)

Desktop mode (Single Screen)

Desktop mode (Dual Screen)

## Installing

### Ubuntu 25.10 (GTK):
```
sudo apt install python3-gi python3-gi-cairo gir1.2-webkit2-4.1 python3-webview python3-screeninfo
git clone https://github.com/superhac/vpinfe.git
cd vpinfe
```

*** There is a known issue with positioning windows under wayland.  To get around that run VpinFE with the following env var:
`GDK_BACKEND=x11 python3 vpinfe.py`.

### Fedora ???? (KDE):
```
git clone https://github.com/superhac/vpinfe.git
```

### Mac ????: 
```
git clone https://github.com/superhac/vpinfe.git
```

### Setup your configuration (vpinfe.ini)

Create a file named `vpinfe.ini` in you vpinfe dir.  Template:
```
[Displays]
bgscreenid =
dmdscreenid =
tablescreenid = 0

[Settings]
vpxbinpath = 
tablerootdir = 
theme = carousel2
joyleft = 14
joyright = 15
joyup = 12
joydown = 13
joyselect = 1
joymenu = 9
joyback = 0
joyexit = 0
joyfav = 16

[Media]
tabletype =
tableresolution = 4k
```

There are three sections above that need to be set mandatorily. `Displays` and three of the settings in `Settings`.

VPinFE supports up two three displays and you need to have atleast the `tablescreenid` one set.  This is typcially `0` so you can leave it if your owning running one screen.  To figure out your display ID's you can run the following command:

`python3 main.py --listres`

This will list your monitors starting at ID 0 to X.

Next you need set three settings in `Settings`.  
- vpxbinpath - The path to your vpinball executable 
- tablerootdir - The root dir where all your tables are located
- Theme - Which theme you want to use.  Right now theres `default` - Three screens cab mode, `carousel` and `carousel2` both for single screens.

All the other settings can be left as they are in the template above for now.  Configuring the gamepad and other fields are covered below. 

Now that your `vpinfe.ini` file has the basics you need build the metadata.  Your names should be in a format like this with the table folders named as they appear in [VPSDB](https://virtualpinballspreadsheet.github.io/tables):


```
superhac@linpin:~/tables$ ls -las
total 28
4 drwxrwxr-x  7 superhac superhac 4096 Feb 21 12:03  .
4 drwxr-x--- 23 superhac superhac 4096 Feb 21 14:49  ..
4 drwxrwxr-x  2 superhac superhac 4096 Feb 21 12:03 '24 (Stern 2009)'
4 drwxrwxr-x  2 superhac superhac 4096 Feb 21 12:09 'AC-DC LUCI Premium VR (Stern 2013)'
4 drwxrwxr-x  3 superhac superhac 4096 Feb 21 15:08 'American Graffiti (Original 2024)'
4 drwxrwxr-x  2 superhac superhac 4096 Feb 21 12:49 'Andromeda (Game Plan 1985)'
4 drwxrwxr-x  2 superhac superhac 4096 Feb 21 12:51 'Back To The Future - The Pinball (Data East 1990)'
...
```

More details on what this does and what it creates can be found [Meta.ini](#Meta.ini)



## Default Keyboard Controls

| Action | Key |
|--------|-----|
| Left or Up    | LeftArrow or Left Control   |
| Right or Down | RightArrow or Right Control |
| Menu          | m                           |
| Select        | Enter                       |


## Meta.ini
ddd