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

carousel-desktop

![carousel-desktop-Trim-clean-ezgif com-video-to-gif-converter](https://github.com/user-attachments/assets/6f2d2b6d-652a-47c6-8e8e-a84b6aa461ee)

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
Beware if you upgrade to 25.10 as they [removed gamepad support from webkitgtk](https://launchpad.net/ubuntu/+source/webkit2gtk/2.48.5-1ubuntu1):
```
    * Disable gamepad feature on Ubuntu since libmanette is in universe there. 

libmanette is a library that provides a GObject-based API for interacting with gamepads. The change log indicates that the developers of the webkit2gtk package chose to disable the built-in gamepad support in this specific Ubuntu package version because the necessary dependency (libmanette) is located in the "universe" repository (which contains community-maintained software) rather than the main "main" repository. This decision was likely made to avoid dependency issues or to ensure the stability of the core webkit2gtk package within Ubuntu's main archives. 
Therefore, this package version likely has gamepad support explicitly disabled in Ubuntu.
```
This breaks the gamepad functionally in VPinfe.  There is currently no work around for this.

### Debian 13
```
sudo apt install python3.13-venv python3-evdev
python3 -m venv vvv --system-site-packages
pip install nicegui screeninfo colorama olefile pynput nicegui==2.* pywebview==6.1
deactivate

# then run like this inside the vpinfe dir
GDK_BACKEND=x11 vvv/bin/python3 main.py
```

### Ubuntu 25.04 (GTK):
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
cd vpinfe
pip install -r osx_requirements.txt
```

### Setup your configuration (vpinfe.ini)

VPinFE uses a platform-specific configuration directory to store its settings. On first run, VPinFE will automatically create a default `vpinfe.ini` file in the following location:

- **Linux**: `~/.config/vpinfe/vpinfe.ini`
- **macOS**: `~/Library/Application Support/vpinfe/vpinfe.ini`
- **Windows**: `C:\Users\<username>\AppData\Local\vpinfe\vpinfe\vpinfe.ini`

When you first run VPinFE, it will create the default configuration file and exit with a message showing the file location. You must then edit this file with your settings before running VPinFE again.

**Required Settings (Minimum):**

Before VPinFE can run, you must configure these three essential settings in the `[Settings]` section:

1. **vpxbinpath** - Full path to your VPinball executable (e.g., `/home/user/vpinball/build/VPinballX_BGFX`)
2. **tablerootdir** - Root directory where all your tables are located (e.g., `/home/user/tables/`)
3. **vpxinipath** - Path to your VPinballX.ini file (e.g., `~/.vpinball/VPinballX.ini`)

**Display Configuration:**

VPinFE supports up to three displays. You need to have at least the `tablescreenid` set. This is typically `0` if you're only running one screen. To figure out your display IDs, run:

`python3 main.py --listres`

This will list your monitors starting at ID 0 to X. Set the appropriate screen IDs in the `[Displays]` section:
- **bgscreenid** - Backglass screen (leave empty if not used)
- **dmdscreenid** - DMD screen (leave empty if not used)
- **tablescreenid** - Main table screen (required, typically `0`)

**Theme Selection:**

Set your preferred theme in the `[Settings]` section:
- **theme** - Choose from: `carousel-desktop`, `carousel2`, `slider`, `cab`, or `default`

**Gamepad/Joystick Controls (Optional):**

All gamepad button mappings are optional. If you want to use a gamepad, configure these in the `[Settings]` section after running `--gamepadtest` (see [Setup Gamepad](#setup-gamepad) section):
- joyleft, joyright, joyup, joydown
- joyselect, joymenu, joyback, joyexit, joycollectionmenu

All the other settings have sensible defaults and can be left as-is initially. Configuring the gamepad and other advanced fields are covered below. 

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

| Action            | Key         |
|-------------------|-------------|
| Left or Up        | Shift left  |
| Right or Down     | Shift Right |
| Menu              | m           |
| Collections Menu  | c           |
| Select            | Enter       |
| Quit              | q or ESCAPE |

## Setup Gamepad

VPinFE includes an interactive gamepad configuration tool that makes mapping your controller buttons easy. Run the gamepad test with:

```bash
GDK_BACKEND=x11 vvv/bin/python3 main.py --gamepadtest
```

<img width="735" height="547" alt="image" src="https://github.com/user-attachments/assets/4291e8dc-7ed5-4dfc-89c8-404a8eb28a1c" />


The gamepad configuration interface provides:

**Button Tester** - Real-time visual feedback showing which buttons are being pressed on your gamepad (numbered 0-16)

**Interactive Button Mapping** - Click on any mapping card (Left, Right, Up, Down, Select, Menu, Back, Exit, Collection Menu), then press the corresponding gamepad button to assign it. The mapping is automatically saved to your `vpinfe.ini` file.

**Visual Workflow:**
1. Click a mapping card (e.g., "Left") - it will highlight with an orange pulsing glow
2. Press the desired button on your gamepad
3. A green success message confirms the mapping
4. The button number is saved to `vpinfe.ini` immediately

Press ESC to exit the gamepad configuration tool when you're done mapping your buttons.

## Collections / Filters
<img width="435" height="592" alt="filter-menu" src="https://github.com/user-attachments/assets/d9733591-4487-488b-9c27-9b3473fb08f1" />

VPinFE supports two types of collections for organizing your tables. Collections are stored in `collections.ini` in the platform-specific configuration directory alongside `vpinfe.ini`:

- **Linux**: `~/.config/vpinfe/collections.ini`
- **macOS**: `~/Library/Application Support/vpinfe/collections.ini`
- **Windows**: `C:\Users\<username>\AppData\Local\vpinfe\vpinfe\collections.ini`

### VPS ID-Based Collections
Create handpicked collections by specifying individual table VPS IDs. Perfect for curated favorites or competition playlists:

```
[Favorites]
type = vpsid
vpsids = 43ma3WQK, lkSumsrF, 6HmAOp06, F4ma5afn, tTOMTth0p8, 9Paf7-CL,M7FYR1GJ, F6QcJM6t_E,
        vyWVqHn5QF,garmU1ZC,yxmGmEGyFk, MBZPVX6p, wasB0RRz, 9Uv1Jljw, 3CvHz8Fa,CdZWHtTg

[Competition]
type = vpsid
vpsids = wEOAp90_,W1JOjl6A,F4ma5afn,XQqwrauH,GXsgeoz_,x6df4mgv,-QXdrtsH, 1IlVLynt
```

### Filter-Based Collections
Create dynamic collections based on VPSdb metadata filters. These collections automatically include all tables matching your filter criteria:

```
[Williams SS Tables]
type = filter
letter = All
theme = All
table_type = SS
manufacturer = Williams
year = All

[1980s EM Tables]
type = filter
letter = All
theme = All
table_type = EM
manufacturer = All
year = 1980
```

**Available Filter Options:**
- `letter` - Filter by starting letter (A-Z) or "All"
- `theme` - Filter by table theme or "All"
- `table_type` - Filter by type (EM, SS) or "All"
- `manufacturer` - Filter by manufacturer (Williams, Bally, GottiaC_sSXnlieb, etc.) or "All"
- `year` - Filter by year or "All"

### Accessing Collections and Filters
VPinFE provides a dedicated Collection Menu for managing all your collections and filters:
- **Open Collection Menu**: Press `c` key (or joycollectionmenu button on gamepad)
- **Navigate**: Use up/down arrows or joyup/joydown to select menu items
- **Select/Apply**: Press Enter or joyselect to open dropdowns or apply selections
- **Close Menu**: Press `c` again, joyback, or select "Close" from the menu

### Saving Filter Collections from the Collection Menu
You can create filter-based collections directly from the Collection Menu:
1. Open the Collection Menu (default: `c` key or joycollectionmenu button on gamepad)
2. Set your desired filters (Letter, Theme, Type, Manufacturer, Year)
3. Select "Save Filter..." from the menu
4. Enter a name for your collection
5. Your filter combination is saved and appears in the Collections dropdown

Both collection types appear together in the Collections dropdown menu and can be switched between seamlessly. **Also note if you want to setup a collection to be activated on startup use the `vpinfe.ini` option "startup_collection".**

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
| joycollectionmenu | Open collection menu in the Theme UI. Button mapping ids from `--gamepadtest`. |
| startup_collection| Set the collection VPinFE starts up with.  Case sensitive, match collection name. |

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

## VPX Table Patches
VPinFE can automaticlly pull patches from [vpx-standalone-scripts](https://github.com/jsm174/vpx-standalone-scripts) via the `--vpxpatch` CLI option if a matching patch can be found.  

`python3 main.py --vpxpatch`

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
