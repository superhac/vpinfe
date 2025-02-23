# VPinFE
![VPinFE_logo_main](https://github.com/user-attachments/assets/507c50e3-bc1e-499a-b393-f9d11250b709)

A frontend for vpinball for linux, windows, mac.

## What does it look like?
YouTube Video

[![IMAGE ALT TEXT HERE](https://img.youtube.com/vi/qptIbb0wLRY/0.jpg)](https://www.youtube.com/watch?v=qptIbb0wLRY)

## Note
This is not ready for consumption as I'm just putting in the plumbing.  You can pull a CI build if you want to see what it looks like.

## Controls
Keyboard: 
- SHIFT_LEFT = Table shift left
- SHIFT_RIGHT = Table shift right
- <a> key - Lanuch the table
- ESCAPE = Exit

Joystick
- Left_Bumper = Table shift left
- Right_Bumber = Table shift right
- A/Green Button = Launch the table (same button as COIN in on VPX)

## Requirements
Windows (Broken) - Needs to be updated to support the individual table folder structure.
- None
  - SDL2 - Included in Windows build

Linux
- None

MacOS
- Not Sure

# File Structure
All tables (and their supporting files) are placed in their own dir under the table root dir:
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

## How to use

Help:
```
usage: vpinfe [-h] [--listres] [--bgid BGID] [--dmdid DMDID] [--tableid TABLEID] [--tableroot TABLEROOT] [--vpxbin VPXBIN]

options:
  -h, --help            show this help message and exit
  --listres             ID and list your screens
  --bgid BGID           The monitor id of the BG monitor
  --dmdid DMDID         The monitor id of the DMD monitor
  --tableid TABLEID     The monitor id of the table monitor
  --tableroot TABLEROOT
                        Root table directory
  --vpxbin VPXBIN       Full Path to your VPX binary
```
#1 - Get your displays (2 minimum for now.  BG and Table)

`./vpinfe --listres`
Then you'll see:
```
Number of joysticks connected: 1
0 :Monitor(x=3840, y=0, width=1920, height=1080, width_mm=600, height_mm=340, name='DP-2', is_primary=False)
1 :Monitor(x=5760, y=0, width=1920, height=1080, width_mm=0, height_mm=0, name='HDMI-1', is_primary=False)
2 :Monitor(x=0, y=0, width=3840, height=2160, width_mm=600, height_mm=340, name='DP-3', is_primary=True)
```
#2 Assign your yours display

`./vpinfe --bgid 0 --tableid 2 --dmdid 1`

or this if you only have two screens:

`./vpinfe --bgid 0 --tableid 2`


#3 Assign you table root folder and vpxbin path

`./dist/vpinfe --bgid 0 --tableid 1 --dmdid 2 --vpxbin /home/superhac/working/vpinball/build/VPinballX_BGFX --tableroot /home/superhac/tables/`
