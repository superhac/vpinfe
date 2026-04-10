# VPinFE
<img width="1278" height="852" alt="VpinFE_V1-MF-withCredit" src="https://github.com/user-attachments/assets/914dff06-e3de-4096-8bc1-b4586d9802f6" />

**A frontend for vpinball with the following features:**
- Works on Linux, Windows, Mac, and ARM (Windows must use Standalone dir structure)
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
- Optional online ratings, scoring and play tracking via [VPin Play](https://www.vpinplay.com/). The [GitHub Project](https://github.com/superhac/vpinplay)

### Support/Feedback
Join us on VPC discord channel @ [vpinfe](https://discord.gg/SFBfA6Te2A)

## Acknowledgements
- A special thanks to **@jsm174** for making VPX available to all these other platforms.  He's also a great mentor.  I learned a tremendous amount working with him on the vpx project and he is the epitome of the VPinball community.  
- **@MajorFrenchy** is another great example of what the VPinball community is all about. He jumped in right away and provided invaluable testing and feedback.  And we can't forget his great video on using [VPinFE on the MAC](https://www.youtube.com/watch?v=YD4eZIqHypw)!  He also made the VPinFE logo and splash video! Thank you, thank you!!!
- Huge thanks to **@Gonzonia** for all his work on the Mac app bundle. This simply wouldn’t have happened without his knowledge and contributions.
- A big high five to @evilwraith for making the ARM build! 
- A big thank you to all the hard work and dedication the [VPS Team](https://virtualpinballspreadsheet.github.io/): (**@Dux, @Fraesh and @Studlygoorite**) has put into creating this great table finding resource! And they made it "open" so others can leverage it as they want.

## See it in action
![carousel-desktop-Trim-clean-ezgif com-video-to-gif-converter](https://github.com/user-attachments/assets/6f2d2b6d-652a-47c6-8e8e-a84b6aa461ee)

[Youtube: Cab Demo](https://www.youtube.com/shorts/49oEZKm6TGE)

[YouTube: Desktop](https://www.youtube.com/watch?v=YXK53rmKRfI)

# Installing (First time Setup)

The install is the same for all platforms you need to download the right release for it.  Currently there are two different builds available for each platform:

- A slim build (has slim in its name) is for people who already have chrome installed locally on there machine. (Recommend bundle)
- A fat build (no slim in its name and larger binary) that bundles chromium with VPinfe

The latest version can be downloaded from [Releases](https://github.com/superhac/vpinfe/releases).

## Running

### Linux (X64 & ARM)
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

<img width="1327" height="219" alt="unmatched" src="https://github.com/user-attachments/assets/9b646c30-1e30-4edc-8835-eda58d5b18cd" />

Click on the unmatched tables button and walkthtough the dialogs.  Once comleted the table will show in your tables list.

## ManagerUI Guide

When VPinFE starts for the first time it opens the ManagerUI on the **Configuration** page. On later runs it remembers the last page you had open. The ManagerUI header also includes:

- **Restart VPinFE** to restart the frontend process
- **Quit VPinFE** to close the app
- **Version and update status** with direct install support when the running build supports in-app updates

The main navigation includes:

- **Tables**
- **Collections**
- **Media**
- **Themes**
- **Mobile Uploader**
- **System**
- **Configuration**
- **Remote Control** opens in a separate tab at `/remote`

### Configuration page

The **Configuration** page edits `vpinfe.ini`. Changes are only written when you click **Save Changes**.

#### Settings section

Core startup and launch behavior:

- **VPX Executable Path**: main VPinball executable or app bundle used to launch tables
- **VPX Launch Environment**: optional environment variable overrides added only to VPX launches. Accepts `KEY=value` pairs, multiple lines, or semicolon-separated entries
- **Global ini Override**: adds `-ini <path>` to all VPX launches
- **Global tableini Override Enabled**: enables masked per-table `-tableini` launching
- **Global tableini Override Mask**: builds `{TableName}.{mask}.ini` beside the `.vpx` and uses it only when the file exists
- **Tables Directory**: root folder scanned for tables, metadata, media, mobile transfer, and VPinPlay sync
- **VPX Ini Path**: path to your VPinballX ini file
- **Active Theme**: currently selected frontend theme
- **Startup Collection**: collection opened when VPinFE starts
- **Auto Update Media On Startup**: enables startup media refresh behavior
- **Enable splashscreen**: shows the frontend splash screen during startup
- **Mute Frontend Audio**: mutes frontend audio playback

The page also shows a **VPinball Launch Command w/Options** preview so you can verify the exact launch command and launch environment before saving.

#### Displays section

Screen assignment and playfield layout:

- **Playfield Monitor ID**
- **Backglass Monitor ID**
- **DMD Monitor ID**
- **Backglass Window Override (x,y,width,height)**: optional explicit bounds passed to themes
- **DMD Window Override (x,y,width,height)**: optional explicit bounds passed to themes
- **Playfield Orientation (Landscape/Portrait)**
- **Playfield Rotation (0/90/270)**
- **Cabinet Mode**

The right side of the page lists detected displays so you can map IDs correctly. On macOS it also shows NSScreen coordinates used for window placement.

#### Input section

Gamepad button mappings stored in `vpinfe.ini`:

- **Left**
- **Right**
- **Up**
- **Down**
- **Select**
- **Menu**
- **Back**
- **Exit**
- **Collection Menu**

You normally set these from `./vpinfe --gamepadtest`, but the values are visible and editable here.

#### Logger section

Logging behavior:

- **Log Verbosity**: debug/info/warning/error/critical
- **Console Logging**: enables console log output

The page also has a **View Log** button that opens the current `vpinfe.log`. VPinFE writes logs to the standard config directory and starts a fresh log file on each launch.

#### Media section

Default metadata/media behavior:

- **Table Type**: preferred media type family when downloading media
- **Default Table Resolution**
- **Default Table Video Resolution**
- **Default Missing Media Image**
- **Thumbnail Cache Max (MB)**: cap for generated media thumbnails used by ManagerUI

#### Network section

Local service ports:

- **Theme Server Port**: media/theme asset server
- **Manager UI Port**: NiceGUI management interface

#### Mobile section

Saved defaults for the **Mobile Uploader** page:

- **Mobile Device IP**
- **Mobile Device Port**
- **Mobile Chunk Size**
- **Enable Rename Mask To Default INI**
- **Rename Mask To Default INI Mask**

When the rename-mask option is enabled for Web Send, VPinFE can send `{VPX_FILENAME}.{MASK}.ini` to the mobile device as `{VPX_FILENAME}.ini`.

#### DOF section

Frontend DOF integration:

- **Enable DOF**: starts the bundled DOF runner for frontend events
- **DOF Config Tool API Key**: used by the online config sync helper

The page also includes:

- **DOF Event Test**: starts and stops a test event token like `E900` or `S27`
- **Online Config Tool**: runs the bundled `ledcontrol_pull.py` helper using your API key, with an optional force update

#### libdmdutil section

Real DMD output integration:

- **libdmdutil Service**: enables the bundled libdmdutil controller
- **ZeDMDDevice**: explicit ZeDMD device path
- **ZeDMDWiFiAddr**: ZeDMD network address
- **PIN2DMD**
- **PixelcadeDevice**

VPinFE currently uses the service enable flag plus the ZeDMD device/Wi-Fi settings directly. If both ZeDMD fields are blank, libdmdutil falls back to its own auto-detection behavior.

#### VPinPlay section

Experimental online metadata sync:

- **API Endpoint**: VPinPlay service base URL
- **User ID**
- **Initials**: uppercased in the UI and limited to 3 characters
- **Machine ID**: auto-generated if missing and read-only in the UI
- **Sync on Exit**: sends installed table metadata during shutdown when all required values are present

The page also provides:

- **VPinPlay Home** and **Your Stats** links
- **Sync Installed Tables** button that posts installed table metadata to the configured VPinPlay endpoint

### Tables page

The **Tables** page scans your tables root for folders that contain both a `.vpx` file and a matching `.info` file. It provides:

- Search by table name
- Filters for manufacturer, year, theme, type, and PUP Pack presence
- Multi-select with **Select Page**
- Batch **Add to Collection**
- Links to **IPDB** and **VPS**
- Badges for rating, collection membership, and per-table overrides

Header actions:

- **Scan Tables** opens the **Build Metadata** workflow
- **Apply Patches** runs standalone VPX patching across supported tables
- **Unmatched Tables** opens folders that have a `.vpx` but no `.info`
- **Import Table** imports a new table package into your tables root

Build Metadata options:

- **Update All Tables** reparses tables even if `.info` already exists
- **Download Media** downloads media from VPinMediaDB while building metadata

Clicking a table opens a detail dialog with:

- Table information from `.info`
- Detected feature flags such as nFozzy, Fleep, SSF, LUT, ScoreBit, FastFlips, and Flex
- Addon detection for PupVideos, Serum, VNI, and AltSound
- Editable **Rating**
- Collection membership management
- Per-table overrides:
  - **Alt Title**
  - **Alt VPS ID**
  - **Alt Launcher**
  - **FrontendDOFEvent**
  - **Delete NVRAM on close**
- Addon upload tools:
  - PUP packs as `.zip`
  - Serum `.cRZ`
  - VNI `.vni` and `.pal`
  - AltSound files
- **Rebuild Meta** for that single table

The **Unmatched Tables** dialog lets you:

- Search VPS by name
- Associate a table folder with a VPS entry
- Optionally rename the folder to `Table Name (Manufacturer Year)`
- Either download media from VPinMediaDB or claim your existing local media as user-owned

The **Import Table** dialog lets you:

- Choose a VPS entry first
- Upload a required `.vpx`
- Optionally upload `.directb2s`, ROM `.zip`, PUP pack `.zip`, and music `.zip`
- Create the table folder, generate metadata, copy/extract uploaded files, and download media

### Collections page

The **Collections** page manages both collection types used by VPinFE:

- **Table collections**: explicit VPS ID lists
- **Filter collections**: dynamic collections based on metadata filters

Supported collection filters:

- Starting letter
- Theme
- Table type
- Manufacturer
- Year
- Rating
- Rating or higher
- Sort order

From this page you can:

- Create, edit, rename, and delete collections
- Search installed tables and add them to a table collection
- Edit filter rules for filter collections
- See collection contents directly in the list

### Media page

The **Media** page scans each table folder and shows which standard media assets are present. Supported media keys are:

- BG
- DMD
- Table
- FSS
- Wheel
- Cab
- Flyer
- Real DMD
- Real DMD Color
- Table Video
- BG Video
- DMD Video
- Audio

Features on this page:

- Search by table name
- Filters for manufacturer, year, theme, and type
- Missing-media filters per media type
- Generated image thumbnails with on-demand caching
- Click any media cell to replace that asset for the selected table

Replacement behavior:

- New files are written to the table's `medias/` folder using the standard VPinFE filename
- The table's `.info` media entry is updated as user media
- The cached media listing refreshes immediately

### Themes page

The **Themes** page loads the remote theme registry and compares it to locally installed themes. It shows:

- Preview image
- Theme name, author, description, version, and supported screen count
- Theme type: desktop, cab, or both
- Whether the theme is built-in, installed, active, or has an update available
- Optional change log text when a new version exists

Actions:

- **Refresh Registry**
- **Install**
- **Update**
- **Set as Active** which writes `Settings.theme` and restarts VPinFE
- **Delete** for non-default themes

### Mobile Uploader page

The **Mobile Uploader** page has two tabs.

**Web Send**

Uses the built-in web server in the mobile VPX app on Android/iOS. VPinFE can:

- Save the target device IP/port/chunk size in `vpinfe.ini`
- Check the device and compare which table folders are already installed
- Filter to **Show Installed Only**
- Send a single table or **Send Selected** for multiple tables
- Delete a table from the mobile device
- Request a mobile-side table refresh after uploads or deletes

Send options:

- **Exclude {VPX_FILENAME}.ini files** prevents sending table-specific default ini files
- **Enable Rename Mask To Default INI** can copy `{VPX_FILENAME}.{MASK}.ini` to the mobile device as `{VPX_FILENAME}.ini`

**VPXZ Download**

Creates a `.vpxz` archive from an installed table folder and downloads it from the ManagerUI.

### System page

The **System** page shows live host metrics and build information:

- CPU utilization
- Memory utilization
- Free disk space for the monitored tables/config volume
- Hostname and OS details
- Build flavor and release target
- Frontend browser name, version, and path
- Last refresh timestamp

On Linux, it also supports optional **GPU Monitoring** using `nvtop`. When enabled it shows:

- GPU utilization
- Device name
- Temperature
- Power draw
- GPU and memory clocks
- Fan speed
- Per-device metrics when multiple GPUs are present

### Remote Control page

The **Remote Control** page is available from the left nav and directly at `/remote`. It uses the configured VPX and PinMAME key mappings through the internal key simulator.

Modes:

- **VPX Maintenance**
  - Reset
  - Quit
  - Volume up/down
  - Toggle stereo
  - In-game UI navigation
  - Debugger
  - Debug balls
  - Performance overlay
- **VPX Game**
  - Start
  - Pause
  - Quit
  - Show Rules
  - Extra Ball
  - Lockbar / Fire
  - Credit 1-4
  - Launch Table picker with collection filter and search
- **PinMAME**
  - Coin Door
  - Up/Down
  - Enter/Cancel
  - Service 1-8
- **VPinFE**
  - Restart VPinFE
  - Reboot system
  - Shutdown system

Remote table launch behavior:

- Uses `Settings.vpxbinpath` unless the table has a per-table **Alt Launcher**
- Applies `Settings.globalinioverride` and masked `-tableini` overrides when configured
- Applies `Settings.vpxlaunchenv` environment overrides
- Stops DOF and libdmdutil before launching
- Restarts DOF after the launched process exits

The page also includes a **Virtual Keyboard** dialog for sending manual key presses.


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

## DOF and libdmdutil

VPinFE includes two bundled integrations in its release distributions:

- **DOF** for cabinet output events such as feedback devices and toys
- **libdmdutil** for sending the table's real DMD image to supported external DMD hardware

They are fetched during the GitHub build workflow and packaged into the distributed app under `third-party/dof` and `third-party/libdmdutil`. You can leave either integration disabled in `vpinfe.ini`, but the supporting files are included with the release builds.

### DOF setup

Release builds already include the DOF files in `third-party/dof`. If you are running from source or want to refresh the bundled files locally, use:

```bash
./scripts/fetch_dof_bundle.sh
```

You can also point VPinFE at a custom DOF bundle location by setting `VPINFE_DOF_DIR`.

Enable DOF in the ManagerUI under the **DOF** section, or in `vpinfe.ini`:

```ini
[DOF]
enabledof = true
dofconfigtoolapikey =
```

Notes:

- VPinFE starts the DOF runner automatically when `enabledof = true`.
- The ManagerUI includes a **DOF Event Test** panel where you can send event tokens like `E900` or `S27`.
- If you use the VPUniverse online config tool, put your API key in `dofconfigtoolapikey` and use the **Update DOF via Online Config Tool** button. That uses the bundled `ledcontrol_pull.py` helper from the DOF package.

### libdmdutil setup

Release builds already include the libdmdutil files in `third-party/libdmdutil`. If you are running from source or want to refresh the bundled files locally, use:

```bash
./scripts/fetch_libdmdutil_bundle.sh
```

You can also override the lookup path with `VPINFE_LIBDMDUTIL_DIR`.

Enable it in the ManagerUI under the **libdmdutil** section, or in `vpinfe.ini`:

```ini
[libdmdutil]
enabled = true
pin2dmdenabled = false
pixelcadedevice =
zedmddevice =
zedmdwifiaddr =
```

Notes:

- VPinFE loads `libdmdutil_wrapper.py` from the bundled package when `enabled = true`.
- If `zedmddevice` is set, VPinFE connects to that device path first.
- If `zedmddevice` is blank and `zedmdwifiaddr` is set, VPinFE connects over Wi-Fi instead.
- If both are blank, libdmdutil falls back to its default auto-detection behavior.
- `pin2dmdenabled` and `pixelcadedevice` are preserved in `vpinfe.ini` for libdmdutil-related configuration, even though VPinFE currently only uses the ZeDMD device and Wi-Fi address fields directly.

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
  --headless            Run web servers/services only, skip the Chromium frontend
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
| HTTP    | 127.0.0.1:RANDOM   | Frontend web asset server (themes/UI content)                               |
| HTTP    | 127.0.0.1:8000     | Python HTTPServer. Serves tables media assets (configurable)          |
| HTTP    | 0.0.0.0:8001       | NiceGui sever.  Handles the UI for configuration and management (configurable) |

The only service that externally accessable from your machine its UI for managing it.  This is setup like this so people with cabinets can administer it remotely.

External Web Endpoints:
- Table/VPX Configuration and Management: http://{YOUR-IP}:8001
- Remote Control: http://{YOUR-IP}:8001/remote
- Mobile Uploader: http://{YOUR-IP}:8001/mobile

## VPINPlay (Experimental)

VPinFE includes an experimental VPINPlay integration for syncing your installed table metadata and usage stats to the VPinPlay service.

- Main site: [vpinplay.com](https://www.vpinplay.com)
- API default: `https://api.vpinplay.com:8888`
- ManagerUI config page: `vpinplay` section in **VPinFE Configuration**

## Making a Theme

See [Theme Doc](docs/theme.md)

## Addtional Details

[Technical Details](docs/technical_details.md)
