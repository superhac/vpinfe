# VPinFE
![VPinFE_logo_main](https://github.com/user-attachments/assets/507c50e3-bc1e-499a-b393-f9d11250b709)

## A frontend for vpinball with the following features:
#### **Cross-Platform Frontend for Virtual Pinball**  
- Works on **Linux, Windows, and Mac** (Windows currently needs updates for VPX compatibility).  

#### **Multi-Display Support**  
- Supports **up to 3 screens** (Backglass, DMD, and Table).  
- Configurable display assignments via `vpinfe.ini`.  

#### **Customizable Controls**  
- **Keyboard & Joystick** support.  
- Joystick mappings configurable in `vpinfe.ini`.  

#### **Table Management & Metadata Handling**  
- **Per-table folder structure** for organizing tables and assets.  
- Auto-generated `meta.ini` with table metadata (e.g., manufacturer, theme, ROM info).  
- **VPSdb Integration**: Matches tables with **Virtual Pinball Spreadsheet** database.  
- **VPX file parsing** for versioning, authorship, and ROM detection, table feature detection(SSF, fuzzy, etc)
- **Media Downloader** for retrieving table, bg, dmd, and wheel images from [VPinMediaDB](https://github.com/superhac/vpinmediadb).

#### **Automated Patching & Metadata Gathering**  
- `--vpxpatch` downloads and applies **VPX-Standalone-Scripts** patches automatically.  
- `--buildmeta` generates metadata for tables from VPSdb, improving search & categorization, retrieve media images. 

## What does it look like?
YouTube Video

[![IMAGE ALT TEXT HERE](https://img.youtube.com/vi/49oEZKm6TGE/0.jpg)](https://www.youtube.com/watch?v=49oEZKm6TGE)

Hud
![sc2](https://github.com/user-attachments/assets/74adc0c8-32e3-4583-9796-8d5d14e55a3e)

## ⚠️ Note
🚧 This is still in development! 🚧
VPinFE is functional but subject to change. If you want to test it early, now is a great time!

## Build Status
![Linux](https://img.shields.io/badge/Linux-Works-green)     
![Mac](https://img.shields.io/badge/Mac-Testing-yellow)        
![Windows](https://img.shields.io/badge/Windows-Broken-red)  

Mac: Appears to be looking for SDl2

Windows: VPX needs to be updated to support the individual table folder structure like standalone

## Download
[CI build](https://github.com/superhac/vpinfe/actions)

## 🎮 Controls
Keyboard: 
- SHIFT_LEFT    = Table shift left
- SHIFT_RIGHT   = Table shift right
- ENTER or "a"  = Launch the table
- ESCAPE or "q" = Exit

Joystick
These are now controlled via the `vpinfe.ini` file.  These are not set by default.  To figure out your values use `jstest`.
```
joyleft = 4
joyright = 5
joyselect = 1
joymenu = 2
joyback = 1
joyexit = 8
```

# 📂 File Structure
If you stick to the convention of name your folders in this format, `TABLE_NAME (MANUFACTURER YEAR)` you will better organzied and the automatic VPSdb and auto patching will work well. 

Tables (and their supporting files) go in their own directories under the root table folder:
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
```
## Images
Each table directory can contain images with specific names:
| File Name     | Image Type    |
| ------------- | ------------- |
| bg.png        | Backglass Image |
| dmd.png       | DMD Image |
| table.png     | Table Image |
| wheel.png     | Icon on Hud |

Example:
```
superhac@linpin:~/tables/Back To The Future - The Pinball (Data East 1990)$ ls -las
total 324708
     4 drwxrwxr-x 2 superhac superhac      4096 Feb 21 12:51  .
     4 drwxrwxr-x 7 superhac superhac      4096 Feb 21 12:03  ..
 39228 -rw-rw-r-- 1 superhac superhac  40166639 Feb 21 11:22 'Back To The Future - The Pinball (Data East 1990).directb2s'
     4 -rw-rw-r-- 1 superhac superhac        31 Feb 21 11:22 'Back To The Future - The Pinball (Data East 1990).ini'
266224 -rw-rw-r-- 1 superhac superhac 272613376 Feb 21 11:22 'Back To The Future - The Pinball (Data East 1990).vpx'
  3528 -rw-rw-r-- 1 superhac superhac   3609180 Feb 21 12:50  bg.png
  1288 -rw-rw-r-- 1 superhac superhac   1316112 Feb 21 12:50  dmd.png
 14428 -rw-rw-r-- 1 superhac superhac  14773058 Feb 21 12:50  table.png
```

## ⚙️ How to use (vpinfe.ini)

Help:
```
VPinFE 0.5 beta by Superhac (superhac007@gmail.com)
usage: vpinfe [-h] [--listres] [--configfile CONFIGFILE] [--buildmeta] [--vpxpatch]

options:
  -h, --help            show this help message and exit
  --listres             ID and list your screens
  --configfile CONFIGFILE
                        Configure the location of your vpinfe.ini file. Default is cwd.
  --buildmeta           Builds the meta.ini file in each table dir
  --vpxpatch            Using vpx-standalone-scripts will attempt to load patches automatically
```

#1 run vpinfe with no arugments the first time: `./vpinfe` and it will create the `vpinfe.ini` file for you. 

#2 - Get your display(s) (Supports 1 to 3 displays.  BG, DMD, and Table)

`./vpinfe --listres`
Then you'll see:
```
Number of joysticks connected: 1
0 :Monitor(x=3840, y=0, width=1920, height=1080, width_mm=600, height_mm=340, name='DP-2', is_primary=False)
1 :Monitor(x=5760, y=0, width=1920, height=1080, width_mm=0, height_mm=0, name='HDMI-1', is_primary=False)
2 :Monitor(x=0, y=0, width=3840, height=2160, width_mm=600, height_mm=340, name='DP-3', is_primary=True)
```
#3 Assign your display(s), paths, and joystick button mapping in the vpinfe.ini file
Assign your displays and paths like the example in your **vpinfe.ini**. Put this is the same dir as the vpinfe executable unless your using the `--configfile` argument
You can also change the `Logger` settings it might help figuring out a runtime issue. Valid levels are `debug`, `info`, `warning`, `error` and `critical`. You can turn the console logging on `1` or off `0` or if the output is too long or the console isn't your thing redirect the ouytput to a file by setting its path. Attaching a logger file when filling a bug report could also help the developers.
```
[Displays]
bgscreenid = 0
dmdscreenid = 1
tablescreenid = 2
hudscreenid = 0
hudrotangle = 0
tablerotangle = 0
backgroundcolor = #000000

[Logger]
level = info
console = 1
file = 

[Settings]
vpxbinpath = /home/superhac/working/remove/vpinball/build/VPinballX_BGFX
tablerootdir = /home/superhac/tables/
joyleft = 4
joyright = 5
joyselect = 1
joymenu = 2
joyback = 1
joyexit = 8

[VPSdb]
last = 1747318256399
```

## Building the metadata using VPS and the VPX parser
There's a CLI argument called --buildmeta that allows you to generate a meta.ini file in each table directory. When you run this option, the following process occurs:

* ### Virtual Pinball Spreadsheet (VPS) Integration

If you don't already have a copy of the VPSdb or if a newer version is available, it will be downloaded to your machine.
Using the VPSdb, VPinFE will attempt to match table folders to a VPSdb ID. If you follow the standard naming convention—"TABLE_NAME (MANUFACTURER YEAR)"—the accuracy will be high. However, the system also employs a similarity ratio, requiring an 80% match for association.
Once a match is found, metadata such as table type, theme, and other relevant details will be retrieved from the VPSdb.

* ### Download Media Images from VPinMediaDB
It will also find table,bg, dmd and wheel images for each table and put them in your table directory from [VPinMediaDB](https://github.com/superhac/vpinmediadb)

* ### VPX File Parser

The .vpx file will be hashed, along with any contained .vbs files.  Additional key metadata will be extracted, including the ROM name, version, and other noteworthy details.

Once this process has finished you end up one `meta.ini` in each table directory.  The file will look like this for example:
```
[VPSdb]
id = vyWVqHn5QF
name = Tornado Rally
type = EM
manufacturer = Original
year = 2024
theme = []

[VPXFile]
filename = Tornado Rally (Original 2024).vpx
filehash = b390e08764153a0572d9b733958394bf5b543392c3d6e4dbf9857e904b26c2f3
version = 1.2.1
author = Flying Rabbit Studios
releasedate = unreleased
blurb = Original modern EM table celebrating Oklahoma
savedate = Sat Dec 21 11:23:32 2024
saverev = 555
manufacturer =
year =
type =
vbshash = 37870dc859cbad179cab7cbdaa37ea7359c5d756060642a65fa4b0169664ce84
rom = OKIES_TornadoRally
detectnfozzy = true
detectfleep = false
detectssf = true
detectlut = true
detectscorebit = false
detectfastflips = false
```

## meta.ini

You must manually add the following settings:

[VPinFE]

`update` = true | false – Determines whether to update the VPS entry for this table. If you manually create this entry or prefer not to use the auto-generated VPSdb, set this to false. Default is true.

[Pinmame]

`deleteNVramOnClose` = true | false – Some tables, like Taito machines, retain the game state when you quit. Enabling this option deletes the NVRAM file upon closing.

## VPX-Standalone-scripts Auto Patch Downloader
The new `--vpxpatch` option automatically utilizes the `vbshash` stored in meta.ini to find and apply matching patches from the VPX-Standalone-Scripts repository. If a match is found, the patch is downloaded and placed in your table folder, ensuring the table is ready to run seamlessly on your next launch.

__Important__: Before using this feature, you must generate the necessary metadata with the `--buildmeta` option, as described above.

## Tips

### If you want faster caching performance match the respective images to the resolution of screens on which they will be displayed. This results in an average performance boost of 40 percent.

This is a bash script using `ImageMagick` that you put in your root tables directory and run.  It will check if the resolution already matches the screen res and skip the conversion if it does.  Adjust the vars in the top of the script to match your screens:

```
#! /bin/bash

bg_res="1920x1080"
dmd_res="1920x1080"
table_res="3840x2160"

force="!"

for dir in */; do
  if [[ -d "$dir" ]]; then
    echo "Entering directory: $dir"
    cd "$dir"
    imgRes=`identify bg.png | cut -d " " -f3`
    if [ "$imgRes" != "$bg_res" ]; then
      convert -resize "$bg_res$force" bg.png -set filename:base "%[basename]" "%[filename:base].png"
    fi

    imgRes=`identify dmd.png | cut -d " " -f3`
    if [ "$imgRes" != "$dmd_res" ]; then
      convert -resize "$dmd_res$force" dmd.png -set filename:base "%[basename]" "%[filename:base].png"
    fi

    imgRes=`identify table.png | cut -d " " -f3`
    if [ "$imgRes" != "$table_res" ]; then
      convert -resize "$table_res$force" table.png -set filename:base "%[basename]" "%[filename:base].png"
    fi
    # Return to the previous directory
    cd - > /dev/null 2>&1
  fi
done
```

