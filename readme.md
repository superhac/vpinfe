# VPinFE
<img width="1278" height="852" alt="VpinFE_V1-MF-withCredit" src="https://github.com/user-attachments/assets/914dff06-e3de-4096-8bc1-b4586d9802f6" />

**A frontend for vpinball with the following features:**
- Works on Linux, Windows, and Mac (Windows must use Standalone dir structure)
- Multiscreen - Supports up to 3 screens (Backglass, DMD, and Table)
- Fully remote cabinet management
- Keyboard & Controller Input support
- Table and Media Manager (Auto download art via [VPinMediaDB](https://github.com/superhac/vpinmediadb))
- Build custom table collections (VPS ID-based and filter-based)
- Automatic [vpx patching](https://github.com/jsm174/vpx-standalone-scripts) for Linux & Mac
- Fully customizable UI theming using HTML, JS and CSS
- JSON-based table metadata with VPX file parsing and feature detection
- DOF Support using [libdof-python](https://github.com/superhac/libdof-python)
- Mobile transfer support for VPinball on Android and iOS (Web Send & VPXZ Download)

### Support/Feedback
Join us on VPC discord channel @ [vpinfe](https://discord.gg/SFBfA6Te2A)

## Acknowledgements
- A special thanks to **@jsm174** for making VPX available to all these other platforms.  He's also a great mentor.  I learned a tremendous amount working with him on the vpx project and he is the epitome of the VPinball community.  
- **@MajorFrenchy** is another great example of what the VPinball community is all about. He jumped in right away and provided invaluable testing and feedback.  And we can't forget his great video on using [VPinFE on the MAC](https://www.youtube.com/watch?v=YD4eZIqHypw)!  He also made the VPinFE logo and splash video! Thank you, thank you!!!
- Huge thanks to **@Gonzonia** for all his work on the Mac app bundle. This simply wouldn’t have happened without his knowledge and contributions.
- A big thank you to all the hard work and dedication the [VPS Team](https://virtualpinballspreadsheet.github.io/): (**@Dux, @Fraesh and @Studlygoorite**) has put into creating this great table finding resource! And they made it "open" so others can leverage it as they want.

## See it in action
![carousel-desktop-Trim-clean-ezgif com-video-to-gif-converter](https://github.com/user-attachments/assets/6f2d2b6d-652a-47c6-8e8e-a84b6aa461ee)

[Youtube: Cab Demo](https://www.youtube.com/shorts/49oEZKm6TGE)

[YouTube: Desktop](https://www.youtube.com/watch?v=YXK53rmKRfI)

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
This is unsigned APP bundle so you need to do a few things to get VPinFE running.  @MajorFrenchy has put together an excellent video on setting this up for the MAC [here](https://www.youtube.com/watch?v=YD4eZIqHypw).  He also has a written tutorial available at his site @  [Major Frenchy's VPinFE on MacOS](https://www.majorfrenchy.com/blog/2026/03/05/vpinfe-macos/).  If you are a MAC user this is best route to take.  Watch the video and/or read the tutorial, and you'll be running quick.   


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

Now that your `vpinfe.ini` file has the basics you need build the metadata.  Your table folder names and layouts should follow the [VPinball table organization standard](https://github.com/vpinball/vpinball/blob/master/docs/FileLayout.md).

Example of how your table directory should look:
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

Example of whats inside a table folder:
```
superhac@testrig:~/test/dof$ tree ~/tables/Hurricane\ \(Williams\ 1991\)/
/home/superhac/tables/Hurricane (Williams 1991)/
├── Hurricane Balutito MOD V2.directb2s
├── Hurricane Balutito MOD V2.vpx
├── Hurricane (Williams 1991).info
├── medias
│   ├── audio.mp3
│   ├── bg.png
│   ├── cab.png
│   ├── dmd.png
│   ├── flyer.png
│   ├── realdmd.png
│   ├── table.mp4
│   ├── table.png
│   └── wheel.png
└── pinmame
    ├── cfg
    │   ├── default.cfg
    │   └── hurr_l2.cfg
    ├── ini
    │   └── hurr_l2.ini
    ├── nvram
    │   └── hurr_l2.nv
    └── roms
        └── hurr_l2.zip
```

VPinFE will try to automatch your tables to VPSID's, but in the event it can't you will have to match it manually.  Any table that is not matched shows up as a "UNMATCHED TABLE" in the UI:

**add IMAGE**

Click on the unmatched tables button and walkthtough the dialogs.  Once comleted the table will show in your tables list.


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
./vpinfe --gamepadtest
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

See [Theme Doc](docs/theme.md)

