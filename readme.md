# VPinFE
![VPinFE_logo_main](https://github.com/user-attachments/assets/507c50e3-bc1e-499a-b393-f9d11250b709)

**A frontend for vpinball with the following features:**
- Works on Linux, Windows, and Mac (Windows must use Standalone dir structure)
- Multiscreen - Supports up to 3 screens (Backglass, DMD, and Table)
- Keyboard & Joystick support
- Table and Media Manager (Auto download art via [VPinMediaDB](https://github.com/superhac/vpinmediadb))
- Build custom table collections (VPS ID-based and filter-based)
- Automatic [vpx patching](https://github.com/jsm174/vpx-standalone-scripts) for Linux & Mac
- Fully customizable UI theming using HTML, JS and CSS
- JSON-based table metadata with VPX file parsing and feature detection

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
![ezgif com-animated-gif-maker](https://github.com/user-attachments/assets/5dec5fab-2222-4a7b-90c3-c90795ab4720)


## Remote:
![remote](https://github.com/user-attachments/assets/088346a4-db6c-4b6f-8e01-bd653d267b79)


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
git clone https://github.com/superhac/vpinfe.git
cd vpinfe
python3 -m venv vvv --system-site-packages
source vvv/bin/activate
pip install nicegui screeninfo colorama olefile pynput nicegui==2.* pywebview platformdirs
deactivate

# then run like this inside the vpinfe dir
GDK_BACKEND=x11 vvv/bin/python3 main.py
```

### Ubuntu 25.04 (GTK):
```
sudo apt install python3-gi python3-gi-cairo gir1.2-webkit2-4.1 python3-webview python3-screeninfo platformdirs
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
`GDK_BACKEND=x11 python3 main.py`.

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

### Windows 11
 
**Requirements**

* Python 3.13.12

>[!CAUTION] 
>If you use the top Button, you might download a wrong Version not working with the following Steps

![image](https://github.com/user-attachments/assets/201ead7f-297f-4b2a-9bf2-f085c14feba8)

![image](https://github.com/user-attachments/assets/d6815cc6-7016-4c31-9103-e4cde8956f48)
* add Path to Enviromentvars (Win11 -> System -> Enviroment)
* enable Script Execution in PowerShell
![image](https://github.com/user-attachments/assets/0c09970e-0b81-422e-ab7e-c07e18d57a0c)

>[!IMPORTANT]
>Due to the Fact Script Execution is needed later on for launching VPINFE, do not disable Script Execution.

* open PowerShell as Admin
```
git clone https://github.com/superhac/vpinfe.git
cd vpinfe
python -m pip install —-upgrade pip
python -m venv venv-vpinfe --system-site-packages
.\venv-vpinfe\scripts\Activate.ps1
pip install pywebview screeninfo colorama requests olefile nicegui pynput
python main.py -h
```
* add Shortcut to this Script on the Desktop
```
cd c:\vpinfe
.\venv-vpinfe\scripts\Activate.ps1
Python Main.py
```

>[!TIP]
>You might have to change the "Open With" from Editor to PowerShell


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

All gamepad button mappings are optional. If you want to use a gamepad, configure these in the `[Input]` section after running `--gamepadtest` (see [Setup Gamepad](#setup-gamepad) section):
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

With your tables in this format run `python3 main.py --buildmeta`.  More details on what this does and what it creates can be found [Meta.ini](#metaini).  At this point you should be able to run VPinfe with keyboard controls.  If using a gamepad see that [section](#setup-gamepad).

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
- `manufacturer` - Filter by manufacturer (Williams, Bally, Gottlieb, etc.) or "All"
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
| startup_collection| Set the collection VPinFE starts up with.  Case sensitive, match collection name. |

### [Input]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| joyleft           | Move left. Button mapping ids from `--gamepadtest`.                      |
| joyright          | Move right. Button mapping ids from `--gamepadtest`.                     |
| joyup             | Move up. Button mapping ids from `--gamepadtest`.                        |
| joydown           | Move down. Button mapping ids from `--gamepadtest`.                      |
| joyselect         | Select button / Launch. Button mapping ids from `--gamepadtest`.        |
| joymenu           | Pop Menu. Button mapping ids from `--gamepadtest`.                       |
| joyback           | Go Back. Button mapping ids from `--gamepadtest`.                        |
| joyexit           | Exit VpinFE. Button mapping ids from `--gamepadtest`.                   |
| joycollectionmenu | Open collection menu in the Theme UI. Button mapping ids from `--gamepadtest`. |

### [VPSdb]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| last              | Rev of VPSDB that was last pulled.                                        |

### [Media]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| tabletype         | If you're using a Full Single Screen or FSS set this to `fss`. Leaving it blank or any other valid will use the portrait table images. |
| tableresolution   | You can choose `1k` or `4k` to let the system know which resolution images you want to download when building the metadata. Leaving it blank will  default to 4K images. |

### [Network]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| themeassetsport   | Port for the theme assets HTTP server. Default is `8000`.                 |
| manageruiport     | Port for the Manager UI (NiceGUI) server. Default is `8001`.              |

## Table Metadata File (based on the Zero install table format)
When you run VPinFE with the `--buildmeta` option it recursively goes through your table directory attempts to match your tables to their VPSDB id.  When matched, it will then parse the VPX for the table for more meta information and produce a `TABLE FOLDER NAME(manufactuer year).info` in that tables directory.  Heres an example for the table 1-2-3:

```
{
    "Info": {
        "IPDBId": "5247",
        "Title": "1-2-3",
        "Manufacturer": "Automaticos",
        "Year": 1973,
        "Type": "EM",
        "Themes": [
            "TV Show",
            "Game Show"
        ],
        "VPSId": "HhMnyw53",
        "Authors": [
            "jpsalas",
            "akiles50000",
            "Loserman76"
        ],
        "Rom": "TlD_123",
        "Description": ""
    },
    "User": {
        "Rating": 0,
        "Favorite": 0,
        "LastRun": null,
        "StartCount": 0,
        "RunTime": 0,
        "Tags": []
    },
    "VPXFile": {
        "filename": "123(Talleres de Llobregat 1973) v601.vpx",
        "filehash": "d685ce54d659fadcafd90a296473fb126754aa23b1145f457c6626aa5baa75d9",
        "version": "6.0.1",
        "releaseDate": "25.01.2026",
        "saveDate": "Sun Jan 25 22:24:36 2026",
        "saveRev": "91",
        "manufacturer": "",
        "year": "",
        "type": "",
        "vbsHash": "bd6dcb7e0c618e4553d230095e73c7ca8e17f31def4595c38a8439b279977b45",
        "rom": "TlD_123",
        "detectNfozzy": "false",
        "detectFleep": "false",
        "detectSSF": "true",
        "detectLUT": "true",
        "detectScorebit": "false",
        "detectFastflips": "false",
        "detectFlex": "false"
    },
    "VPinFE": {
        "deletedNVRamOnClose": false
    },
    "Medias": {
        "bg": {
            "Source": "vpinmediadb",
            "Path": "/home/superhac/tables/1-2-3 (Automaticos 1973)/medias/bg.png",
            "MD5Hash": "d80f67a370ebce2edd19febdc3fd7636"
        },
        "wheel": {
            "Source": "vpinmediadb",
            "Path": "/home/superhac/tables/1-2-3 (Automaticos 1973)/medias/wheel.png",
            "MD5Hash": "a88bcaf2ade6b9614417fc18a8782f78"
        },
        "cab": {
            "Source": "vpinmediadb",
            "Path": "/home/superhac/tables/1-2-3 (Automaticos 1973)/medias/cab.png",
            "MD5Hash": "2df700d28fbfd88bb9a08c50da0c00ae"
        },
        "table": {
            "Source": "vpinmediadb",
            "Path": "/home/superhac/tables/1-2-3 (Automaticos 1973)/medias/table.png",
            "MD5Hash": "ee863e38e38d8dd5552e511a15583d23"
        }
    }
}
```
### Sections Explained

- Info

  Contains the core table metadata sourced from VPSdb and the VPX file:
  - IPDBId: Internet Pinball Database ID (if available)
  - Title: Table name
  - Manufacturer, Year, Type (EM, SS, etc.)
  - Themes: Array of themes
  - VPSId: Internal VPS database ID
  - Authors: Table authors
  - Rom: Name of the ROM file
  - Description: Table description/blurb

- User

  Stores per-user data for the table. Preserved across `--buildmeta --update-all`:
  - Rating: User rating (0–10)
  - Favorite: Favorite flag (0/1)
  - LastRun: Timestamp of last play
  - StartCount: How many times played
  - RunTime: Total playtime in seconds
  - Tags: Array of custom tags

- VPXFile

  Contains metadata extracted from the VPX file:
  - filename, filehash, version
  - releaseDate, saveDate, saveRev (VPX save info)
  - manufacturer, year, type
  - vbsHash: SHA-256 hash of table's VBS script
  - rom: ROM name from the VPX
  - detect* flags: Booleans indicating which features were detected (detectNfozzy, detectFleep, detectSSF, detectLUT, detectScorebit, detectFastflips, detectFlex)

- VPinFE

  VPinFE-specific settings for the table. Preserved across `--buildmeta --update-all`:
  - deletedNVRamOnClose: (true/false) Some tables, like Taito machines, retain the game state when you quit. Enabling this option deletes the NVRAM file upon closing. Default is false.

- Medias

  Tracks downloaded media files per table. Preserved across `--buildmeta --update-all`. Each entry is keyed by media type (bg, dmd, table, fss, wheel, cab, realdmd, realdmd_color):
  - Source: Where the media was downloaded from (e.g. "vpinmediadb" or "user" for manually uploaded)
  - Path: Full local path to the media file
  - MD5Hash: MD5 hash of the media from the source. On `--buildmeta`, if the remote MD5 differs from the stored hash, the image is re-downloaded automatically.

After that file is created it then attempts to download the media artwork for that table from [VPinMediaDB](https://github.com/superhac/vpinmediadb). All media images are stored in a `medias/` subfolder within each table's directory:

```
Table Folder Name (Manufacturer Year)/
├── TableName.vpx
├── TableName.info
└── medias/
    ├── bg.png
    ├── dmd.png
    ├── table.png (or fss.png)
    ├── wheel.png
    ├── cab.png
    ├── flyer.png
    ├── realdmd.png
    └── realdmd-color.png
```

| File Name         | Image Type                              |
| ----------------- | --------------------------------------- |
| bg.png            | Backglass Image                         |
| dmd.png           | DMD Image                               |
| table.png         | Table Image (portrait)                  |
| fss.png           | Full Single Screen Image                |
| wheel.png         | Icon on Hud                             |
| cab.png           | A cabinet image of the pinball machine  |
| flyer.png         | Promotional flyer image                 |
| realdmd.png       | Real DMD for use with ZeDMD            |
| realdmd-color.png | Real DMD (Colorized) for use with ZeDMD |

## VPX Table Patches
VPinFE can automaticlly pull patches from [vpx-standalone-scripts](https://github.com/jsm174/vpx-standalone-scripts) via the `--vpxpatch` CLI option if a matching patch can be found.  

`python3 main.py --vpxpatch`

## Server Listeners
There are three server listeners started on your machine:

| Service | Bound Address/Port | Description                                                           |
| ------- | ---------------    | --------------------------------------------------------------------- |
| HTTP    | 127.0.0.1:RANDOM   | PyWebView server.  Frontend UI/Themes                                 |
| HTTP    | 127.0.0.1:8000     | Python HTTPServer. Serves tables media assets (configurable)          |
| HTTP    | 0.0.0.0:8001       | NiceGui sever.  Handles the UI for configuration and management (configurable) |

The only service that externally accessable from your machine its UI for managing it.  This is setup like this so people with cabinets can administer it remotely.

The ports for the theme assets server and manager UI can be configured in your `vpinfe.ini` file under the `[Network]` section:

```ini
[Network]
themeassetsport = 8000
manageruiport = 8001
```

External Web Endpoints:
- Table/VPX Configuration and Management: http://{YOUR-IP}:8001
- Remote Control: http://{YOUR-IP}:8001/remote

## Making a Theme

See [Theme.md](https://github.com/superhac/vpinfe/blob/master/theme.md)
