# VPinFE
![VPinFE_logo_main](https://github.com/user-attachments/assets/507c50e3-bc1e-499a-b393-f9d11250b709)

A frontend for vpinball for linux, windows, mac.

## What does it look like?
YouTube Video

[![IMAGE ALT TEXT HERE](https://img.youtube.com/vi/i7bAqSzp_cQ/0.jpg)](https://www.youtube.com/watch?v=i7bAqSzp_cQ)

## Download
[CI build](https://github.com/superhac/vpinfe/actions)

## Note
This is not yet ready for primetime consumption, but if you want to get your feet wet and do some testing nows a good time.  It works but will subject to changes.

## Controls
Keyboard: 
- SHIFT_LEFT = Table shift left
- SHIFT_RIGHT = Table shift right
- "a" key - Lanuch the table
- ESCAPE = Exit

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

## Build Status

| Platform | Status | Dependencies | Notes |
| -------- |--------|--------------|-------|
|Linux     |Works   | None         |       |
|Mac       |Testing | Unknown      | Appears to be looking for SDl2 |
|Windows   |broken  | None         | VPX needs to be updated to support the individual table folder structure like standalone |

# File Structure
All tables (and their supporting files) are placed in their own directory under the table root dir:
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

Then in each table dir. You can place your images with the following names:
| File Name     | Image Type    |
| ------------- | ------------- |
| bg.png        | Backglass Image |
| dmd.png       | DMD Image |
| table.png     | Table Image |

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

## How to use (vpinfe.ini)

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
Assign your displays and paths like the example in your **vpinfe.ini**.  Put this is the same dir as the vpinfe executable unless your using the `--configfile` argument
```
[Displays]
bgscreenid = 0
dmdscreenid = 1
tablescreenid = 2
[Settings]
vpxbinpath = /home/superhac/working/vpinball/build/VPinballX_BGFX
tablerootdir = /home/superhac/tables/
joyleft = 4
joyright = 5
joyselect = 1
joymenu = 2
joyback = 1
joyexit = 8
```

## Building the metadata using VPS and the VPX parser
Theres a new cli arugument called `--buildmeta` that you can use to create a `meta.ini` file in each table directory.  When you execute this option the following happens:
- Virtual Pinball Spreadsheet (VPS)
  - Will download a copy a copy of the VPSdb to your machine if you neither have it or theres a newer version of avaliable
  - Using VPSdb, VPinFE will attempt to correlate by "table folder" to a VPSdb ID.  __Note if you follow the standard naming convention of "TABLE_NAME (MANUFACTURER YEAR)" the results will be highly accurate.__ But none the less it uses a similarity ratio where 80 percent match is used.
  - Once a match is made it will pull in metadata from the VPSdb.  Like type, theme, etc.
- VPX file parser
  - Will hash the .vpx, hash the contained .vbs and then pull other note worthly metadata, like the rom name, version, etc.

Once this process has finished you end up one `meta.ini` in each table directory.  The file will look like this for example:
```
[VPSdb]
id = uiEUziXx
name = Andromeda
type = SS
manufacturer = Game Plan
year = 1985
theme = ['Fantasy', 'Women']

[VPXFile]
filename = Andromeda (Game Plan 1985).vpx
filehash = 10e0030d3c5a51558a9c56b37096d0284b7bdc2f9f676c9246f1f6f800d00524
version = 5.5.0
author = jpsalas, siggi
releasedate = 11,12.2024
blurb =
savedate = Wed Dec 11 05:01:16 2024
saverev = 58
manufacturer =
year =
type =
vbshash = 0a824c84c9a5ee4660a093530130fa5795c6592f929ab1ac80724620140dbb74
rom = andromed
```
More to come on how this will be used!

### meta.ini

These you have to manually add: 

[VPinFE]

`update` = # true or false whether to update the VPS entry for this table.  If you create this manually or don't want to use the auto generated VPSdb set this to `false`. Default is `true`. 

[Pinmame]

`deleteNVramOnClose` = # true or false # Some tables leave the game in a state where it was when you quit.  Like [Taito machines](https://github.com/jsm174/vpx-standalone-scripts/issues/89).  Use this to delete the nvram file on close.

## VPX-Standalone-scripts Auto Patch Downloader
There is a builtin option now `--vpxpatch` that will attempt using the vbshash captured in the `meta.ini` to match patches from VPX-Standalone-scripts.  If a hash is matched it will automatically download it and place it in your table folder.  Next time you run the table you should be good to go!

__Note__ you must build the metadata first via the `--buildmeta` option mentioned above for this to work.

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

