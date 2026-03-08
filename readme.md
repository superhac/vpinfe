# VPinFE
![VpinFE_V1-MF](https://github.com/user-attachments/assets/44609177-22f8-4a06-8b4b-764217789a64)


**A frontend for vpinball with the following features:**
- Works on Linux, Windows, and Mac (Windows must use Standalone dir structure)
- Multiscreen - Supports up to 3 screens (Backglass, DMD, and Table)
- Keyboard & Joystick support
- Table and Media Manager (Auto download art via [VPinMediaDB](https://github.com/superhac/vpinmediadb))
- Build custom table collections (VPS ID-based and filter-based)
- Automatic [vpx patching](https://github.com/jsm174/vpx-standalone-scripts) for Linux & Mac
- Fully customizable UI theming using HTML, JS and CSS
- JSON-based table metadata with VPX file parsing and feature detection
- Mobile transfer support for VPinball on Android and iOS (Web Send & VPXZ Download)

# Acknowledgements
- A special thanks to @jsm174 for making VPX available to all these other platforms.  He's also a great mentor.  I learned a tremendous amount working with him on the vpx project and is epitome of the VPinball community.  
- @MajorFrenchy for all the great testing and feedback.  And we can't forget his great video on using VPinFE on the MAC!  He also made the VPinFE logo and splash video!
- @gonzonia for all his work on making the MAC App Bundle!  Would not have happened without his knowledge and contributions.
- A big thank you to all the hard work and dedication the [VPS Team](https://virtualpinballspreadsheet.github.io/): (@Dux, @Fraesh and @Studlygoorite) has put into creating this great table finding resource! And they made it "open" so others can leverage it as they want.

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


# Installing (First time Setup)

The install is the same for all platforms you need to download the right release for it.  Currently there are two different builds available for each platform:

- A slim build (has slim in its name) is for people who already have chrome or chromium installed locally on there machine. (Recommend bundle)
- A fat build (no slim in its name and larger binary) that bundles chromium with VPinfe

## Running

### Linux
Download the latest release and unzip it and then run:
```
cd vpinfe
./vpinfe
```

### MAC
This is unsigned APP bundle so you need to do a few things to get VPinFE running.  @MajorFrenchy has put together an excellent video on this [here](https://www.youtube.com/watch?v=YD4eZIqHypw).

### Windows
The windows package has a `vpinfe.bat` file for launching it.  Unless your in a terminal always use the batch file or you will end up window focus issues when using VPinFE. Either double click on it to launch or from the CLI:

```
cd vpinfe
vpinfe.bat
```

## Setup your configuration

When you run VPinFE the first time it load into the ManagerUI.  You need setup the minimum settings to get things to work.  

The frist is the "display" panel.  Its recommend you just start with one screen as its auto-configured.

<img width="1339" height="832" alt="2-settings-panel" src="https://github.com/user-attachments/assets/b659c70d-e103-482c-bafa-539995fcdc2d" />

Next you must configure these three essential settings in the `[Settings]` section:

<img width="1307" height="591" alt="1-settings-panel" src="https://github.com/user-attachments/assets/4c774005-a6a6-4970-b85e-d4f26ea18941" />

1. **vpxbinpath** - Full path to your VPinball executable (e.g., `/home/user/vpinball/build/VPinballX_BGFX`)
2. **tablerootdir** - Root directory where all your tables are located (e.g., `/home/user/tables/`)
3. **vpxinipath** - Path to your VPinballX.ini file (e.g., `~/.vpinball/VPinballX.ini`)

Once these are configured you can exit the ManagerUI by clicking the shutdown button in the UI (upper left area).  Anytime you want to return to the ManagerUI look in the console for its webserver address.  Its a line that looks like this:

```
NiceGUI ready to go on http://localhost:8001, and http://192.168.1.228:8001
```

Put that URL in a browser and your in the ManagerUI.

## Setup your tables

Now that your `vpinfe.ini` file has the basics you need build the metadata.  Your table folder names should be in a format as they appear in [VPSDB](https://virtualpinballspreadsheet.github.io/tables):

---- TODO using the ManagerUI -----

## Default Keyboard Controls

| Action            | Key         |
|-------------------|-------------|
| Left or Up        | Shift left  |
| Right or Down     | Shift Right |
| Menu              | m           |
| Collections Menu  | c           |
| Select            | Enter       |
| Quit              | q or ESCAPE |

## Setup Gamepad (optional)

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

# Addtional Information and Context

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
  --headless            Run web servers/services only, skip the legacy frontend frontend
  --claim-user-media    Bulk mark existing media files as user-sourced so they won't be overwritten by vpinmediadb
  --no-media            When building meta.ini files don't download the images at the same time.
  --update-all          When building meta.ini reparse all tables to recreate the meta.ini file.
  --user-media          With --buildmeta: skip vpinmediadb downloads and claim existing local media as user-sourced
  --table TABLE         Specify a single table folder name to process with --buildmeta or --claim-user-media
```

## Server Listeners
There are three server listeners started on your machine:

| Service | Bound Address/Port | Description                                                           |
| ------- | ---------------    | --------------------------------------------------------------------- |
| HTTP    | 127.0.0.1:RANDOM   | Legacy Frontend server.  Frontend UI/Themes                                 |
| HTTP    | 127.0.0.1:8000     | Python HTTPServer. Serves tables media assets (configurable)          |
| HTTP    | 0.0.0.0:8001       | NiceGui sever.  Handles the UI for configuration and management (configurable) |

The only service that externally accessable from your machine its UI for managing it.  This is setup like this so people with cabinets can administer it remotely.

External Web Endpoints:
- Table/VPX Configuration and Management: http://{YOUR-IP}:8001
- Remote Control: http://{YOUR-IP}:8001/remote
- Mobile Uploader: http://{YOUR-IP}:8001/mobile

## Making a Theme

See [Theme.md](https://github.com/superhac/vpinfe/blob/master/theme.md)

