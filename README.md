# PINFE

A frontend for vpinball for linux, windows, mac.

## Note
This is not ready for consumption as I'm just putting in the plumbing.  You can pull a CI build if you want to see what it looks like.  RIGHT_SHIFT will switch tables (Only 2) and ESCAPE will exit.

## Controls
Keyboard: 
- SHIFT_LEFT = Table shift left
- SHIFT_RIGHT = Table shift right
- ESCAPE = Exit

Joystick
- Left_Bumper = Table shift left
- Right_Bumber = Table shift right

## Requirements
Windows
- None
  - SDL2 - Included in Windows build

Linux
- Not Sure

MacOS
- Not Sure

## How to use

Help:
```
usage: vpinfe [-h] [--listres] [--bgid BGID] [--dmdid DMDID] [--tableid TABLEID]

options:
  -h, --help         show this help message and exit
  --listres          ID and list your screens
  --bgid BGID        The monitor id of the BG monitor
  --dmdid DMDID      The monitor id of the DMD monitor
  --tableid TABLEID  The monitor id of the table monitor
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
#2 Assign your yours displays and run

`./vpinfe --bgid 0 --tableid 2 --dmdid 1`

or this if you only have two screens:

`./vpinfe --bgid 0 --tableid 2`


#3 Enjoy ;)
