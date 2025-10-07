# VPinFE
![VPinFE_logo_main](https://github.com/user-attachments/assets/507c50e3-bc1e-499a-b393-f9d11250b709)

**A frontend for vpinball with the following features:**
- Works on Linux, Windows, and Mac (Windows currently needs support for the Standalone dir structure)
- Multiscreen - Supports up to 3 screens (Backglass, DMD, and Table)
- Keyboard & Joystick support
- Table and Media Manager (Auto download art via [VPinMediaDB](https://github.com/superhac/vpinmediadb))
- High Score Extraction/Tracking
- Build custom table collections
- Automatic [vpx patching](https://github.com/jsm174/vpx-standalone-scripts) for Linux & Mac
- Fully customizable UI themeing using HTML, JS and CSS

## Themes
Cab
<img width="5000" height="1404" alt="wenshot-cab" src="https://github.com/user-attachments/assets/7851b3fc-0b5a-45dc-b8dd-b54093594199" />

Default
<img width="1349" height="393" alt="image" src="https://github.com/user-attachments/assets/47a3db0b-6988-4e97-9487-84e394709f92" />

slider (Single Screen)
<img width="1917" height="1080" alt="Screenshot From 2025-10-07 08-00-59" src="https://github.com/user-attachments/assets/df0d8227-67b5-4ab4-8808-26b00bcb16f8" />

carousel2 (Single Screen)
<img width="1919" height="1080" alt="Screenshot From 2025-08-12 16-07-26" src="https://github.com/user-attachments/assets/0e0dfd02-999a-476b-a8f8-bc67d2a5ae10" />

[Videos](https://www.youtube.com/@Superhac007)

## ManagerUI:
![mangerui](https://github.com/user-attachments/assets/9cf8e0e5-4f7f-4f29-bd1d-3080310a10c9)


## Remote:
<img width="2820" height="2215" alt="image" src="https://github.com/user-attachments/assets/6d6f8508-e1ad-4170-825a-cf237ce10cb5" />

## Installing

### Ubuntu 25.10 (GTK):
```
sudo apt install python3-gi python3-gi-cairo gir1.2-webkit2-4.1 python3-webview python3-screeninfo
git clone https://github.com/superhac/vpinfe.git
cd vpinfe
python3 -m venv vvv --system-site-packages
source vvv/bin/activate
pip install pywebview nicegui screeninfo colorama
deactivate

# then run like this inside the vpinfe dir
GDK_BACKEND=x11 vvv/bin/python3 main.py
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
tabletype = table
tableresolution = 4k
```

There are three sections above that need to be set mandatorily. `Displays` and three of the settings in `Settings`.

VPinFE supports up to three displays and you need to have atleast the `tablescreenid` one set.  This is typcially `0` so you can leave it if your only running one screen.  To figure out your display ID's you can run the following command:

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

With your tables in this format run `vpinfe.py --buildmeta`.  More details on what this does and what it creates can be found [Meta.ini](#metaini).  At this point you should be able to run VPinfe with keyboard controls.  If using a gamepad see that [section](#setup-gamepad).

## Default Keyboard Controls

| Action | Key |
|--------|-----|
| Left or Up    | LeftArrow or Left Control   |
| Right or Down | RightArrow or Right Control |
| Menu          | m                           |
| Select        | Enter                       |


## Setup Gamepad

Since we are using the JS gamepad API there is the `--gamepadtest` option that can be run to test and map your controls.

<img width="3840" height="2160" alt="Screenshot From 2025-08-12 15-57-31" src="https://github.com/user-attachments/assets/57f4f09d-f289-4286-bbb6-d1aef87308fa" />

Those numbers represent the same numbers you would set in the `vpinfe.ini` file as shown below:

```
[Settings]
joyleft = 
joyright = 
joyup = 
joydown = 
joyselect = 
joymenu = 
joyback = 
joyexit = 
joyfav = 
```

## Collections
If you have lots of tables you may want to organize them as a collection.  VPinFE will look in the CWD for a file called `collections.ini`.  The format is self explanatory:

```
[Favorites]
vpsids = 43ma3WQK, lkSumsrF, 6HmAOp06, F4ma5afn, tTOMTth0p8, 9Paf7-CL,M7FYR1GJ, F6QcJM6t_E,
        vyWVqHn5QF,garmU1ZC,yxmGmEGyFk, MBZPVX6p, wasB0RRz, 9Uv1Jljw, 3CvHz8Fa,CdZWHtTg

[Competition]
vpsids = wEOAp90_,W1JOjl6A,F4ma5afn,XQqwrauH,GXsgeoz_,x6df4mgv,-QXdrtsH, 1IlVLynt
```

The tables for each collection are identified by their VPSID.  You can access your collections in the menu.

## VPinfe CLI Options
```
options:
  -h, --help            show this help message and exit
  --listres             ID and list your screens
  --listmissing         List the tables from VPSdb
  --listunknown         List the tables we can't match in VPSdb
  --configfile CONFIGFILE
                        Configure the location of your vpinfe.ini file. Default is cwd.
  --buildmeta           Builds the meta.ini file in each table dir
  --vpxpatch            Using vpx-standalone-scripts will attempt to load patches automatically
  --gamepadtest         Testing and mapping your gamepad via js api
  --no-media            When building meta.ini files don't download the images at the same time.
  --update-all          When building meta.ini reparse all tables to recreate the meta.ini file.
```

## Vpinfe.ini
### [Displays]
| Key               | Description                                                                                         |
| ----------------- | -------------------------------------------------------------------------                           |
| bgscreenid        | Blackglass screen number.  use `--listres` to get your mointor ids. Leave blank if no display       |
| dmdscreenid       | dmdscreenid screen number.  use `--listres` to get your mointor ids. Leave blank if no display      |
| tablescreenid     | tablescreenid screen number.  use `--listres` to get your mointor ids. Leave blank if no display    |

### [Settings]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| vpxbinpath        | Full path to you vpx binary.  e.g. /apps/vpinball/build/VPinballX_BGFX    |
| tablerootdir      | The root folder where all your tables are located.  e.g /vpx/tables/      |
| gamepadid         | The gamepad device ID.  use --listgpads to find the id. default is 0      |
| joyleft           | Move left. Button mapping ids from `--gamepadtest`.                      |
| joyright          | Move right. Button mapping ids from `--gamepadtest`.                     |
| joyselect         | Select button / Launch. Button mapping ids from `--gamepadtest`.        |
| joymenu           | Pop Menu. Button mapping ids from `--gamepadtest`.                       |     
| joyback           | Go Back. Button mapping ids from `--gamepadtest`.                        |
| joyexit           | Exit VpinFE. Button mapping ids from `--gamepadtest`.                   |
| joyfav            | Mark a favorate table when in the Theme UI. Button mapping ids from `--gamepadtest`. |                                |

### [VPSdb]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| last              | Rev of VPSDB that was last pulled.                                        |

### [Media]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| tabletype         | If you're using a Full Single Screen or FSS set this to `fss`. Leaving it blank or any other valid will use the portrait table images. |
| tableresolution   | You can choose `1k` or `4k` to let the system know which resolution images you want to download when building the metadata. Leaving it blank will  default to 4K images. |

## Meta.ini
When you run VPinFE with the `--buildmeta` option it recursively goes through your table directory attempts to match your tables to their VPSDB id.  When matched, it will then parse the VPX for the table for more meta information and produce a `meta.ini` in that tables directory.  Heres an example for the table 2001:

```
[VPSdb]
id = sMBqx5fp
name = 2001
type = EM
manufacturer = Gottlieb
year = 1971
theme = ['Fantasy']

[VPXFile]
filename = 2001 (Gottlieb 1971) v0.99a.vpx
filehash = 61bfb1d1ab39836ac28724af7c5d7ae330c608e2092f527b70bae2f75748e3a6
version = 1.0
author =
releasedate =
blurb =
savedate = Sun Apr 23 02:19:21 2023
saverev = 1466
manufacturer =
year =
type =
vbshash = 0bdf965426045a5bb2d98e509cd17ae7b9afc4039b8a10f793cf6123fe9962c9
rom = GTB2001_1971
detectnfozzy = true
detectfleep = true
detectssf = true
detectlut = true
detectscorebit = false
detectfastflips = false
detectflex = false
```

After that file is created it then attempts to download the media artwork for that table.   Currently the following images are downloaded and are stored in each of the table's directory:

| File Name     | Image Type    |
| ------------- | ------------- |
| bg.png        | Backglass Image |
| dmd.png       | DMD Image |
| table.png     | Table Image |
| wheel.png     | Icon on Hud |
| fss.png       | Full Single Screen Image |
| cab.png       | A cabinet image of the pinball machine |
| realdmd.png       | Real DMD for use with ZeDMD |
| realdmd-color.png       | Real DMD (Colorized) for use with ZeDMD |

You must manually add the following settings:

[VPinFE]

`update` = true | false – Determines whether to update the VPS entry for this table. If you manually create this entry or prefer not to use the auto-generated VPSdb, set this to false. Default is true.

[Pinmame]

`deleteNVramOnClose` = true | false – Some tables, like Taito machines, retain the game state when you quit. Enabling this option deletes the NVRAM file upon closing.

## Server Listeners
There are three server listeners started on your machine:

| Service | Bound Address/Port | Description                                                           |
| ------- | ---------------    | --------------------------------------------------------------------- |
| HTTP    | 127.0.0.1:RANDOM   | PyWebView server.  Frontend UI/Themes                                 |
| HTTP    | 127.0.0.1:8000     | Python HTTPServer. Serves tables media assets                         |
| HTTP    | 0.0.0.0:8001       | NiceGui sever.  Handles the UI for configuration and management       | 

The only service that externally accessable from your machine its UI for managing it.  This is setup like this so people with cabinets can administer it remotely.

External Web Endpoints:
- Table/VPX Configuration and Management: http://{YOUR-IP}:8001
- Remote Control: http://{YOUR-IP}:8001/remote

## Making a Theme

See [Theme.md](https://github.com/superhac/vpinfe/blob/master/theme.md)
