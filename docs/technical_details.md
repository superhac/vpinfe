## Vpinfe.ini Definition
VPinFE uses a platform-specific configuration directory to store its settings. On first run, VPinFE will automatically create a default `vpinfe.ini` file in the following location:

- **Linux**: `~/.config/vpinfe/vpinfe.ini`
- **macOS**: `~/Library/Application Support/vpinfe/vpinfe.ini`
- **Windows**: `C:\Users\<username>\AppData\Local\vpinfe\vpinfe\vpinfe.ini`

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
| splashscreen      | Enable or disable the splash screen at startup. Default is `true`. |

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
| joytutorial       | Open the Pinball Primer tutorial overlay. Button mapping ids from `--gamepadtest`. |
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

### [Mobile]
| Key        | Description                                              |
| ---------- | -------------------------------------------------------- |
| deviceip   | IP address of the mobile device running VPinball         |
| deviceport | Port of the mobile device's web server. Default is `2112` |
| chunksize  | Upload chunk size in bytes. Default is `1048576` (1MB)    |

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
        "detectnfozzy": "false",
        "detectfleep": "false",
        "detectssf": "true",
        "detectlut": "true",
        "detectscorebit": "false",
        "detectfastflips": "false",
        "detectflex": "false"
    },
    "VPinFE": {
        "deletedNVRamOnClose": false,
        "altlauncher": ""
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
  - detect* flags: Booleans indicating which features were detected (detectnfozzy, detectfleep, detectssf, detectlut, detectscorebit, detectfastflips, detectflex)

- VPinFE

  VPinFE-specific settings for the table. Preserved across `--buildmeta --update-all`, except `altvpsid` which is cleared when the table's stored `VPXFile.filehash` changes during a rebuild:
  - deletedNVRamOnClose: (true/false) Some tables, like Taito machines, retain the game state when you quit. Enabling this option deletes the NVRAM file upon closing. Default is false.
  - altlauncher: Optional executable path override used only for this table. If set, this is used instead of `vpinfe.ini` `Settings.vpxbinpath`.

- Medias

  Tracks downloaded media files per table. Preserved across `--buildmeta --update-all`. Each entry is keyed by media type (bg, dmd, table, fss, wheel, cab, realdmd, realdmd_color, audio):
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
    ├── realdmd-color.png
    └── audio.mp3
```

| File Name         | Image Type                              |
| ----------------- | --------------------------------------- |
| bg.png            | Backglass Image                         |
| dmd.png           | DMD Image                               |
| table.png         | Table Image (landscape)                 |
| table.mp4         | Table Video (landscape)                 |
| fss.png           | Full Single Screen Image                |
| wheel.png         | Icon on Hud                             |
| cab.png           | A cabinet image of the pinball machine  |
| flyer.png         | Promotional flyer image                 |
| realdmd.png       | Real DMD for use with ZeDMD            |
| realdmd-color.png | Real DMD (Colorized) for use with ZeDMD |
| audio.mp3         | Table audio track for frontend playback  |

## Using Your Own Media (User Media)

By default, `--buildmeta` downloads media artwork from [VPinMediaDB](https://github.com/superhac/vpinmediadb) and tracks updates via MD5 hashes. If you prefer to use your own media collection instead, VPinFE provides two options to mark media as "user-sourced" so it won't be pulled from or overwritten by VPinMediaDB.

### `--claim-user-media` (Standalone)

Scans all table directories for existing media files in the `medias/` subfolder and marks them as `"Source": "user"` in each table's `.info` file. Use this if you already have `.info` files and want to retroactively protect your media from being overwritten.

```bash
# Claim all existing media across all tables
python3 main.py --claim-user-media

# Claim media for a single table
python3 main.py --claim-user-media --table "Back To The Future - The Pinball (Data East 1990)"
```

### `--user-media` (With `--buildmeta`)

A modifier for `--buildmeta` that skips VPinMediaDB downloads entirely and instead claims any media files found locally as user-sourced. Use this when building metadata from scratch and you never want VPinMediaDB media.

```bash
# Build metadata and claim local media instead of downloading
python3 main.py --buildmeta --user-media

# Rebuild all metadata with user media
python3 main.py --buildmeta --update-all --user-media
```

Once media is marked as `"Source": "user"`, subsequent runs of `--buildmeta` will skip downloading that media type from VPinMediaDB. You can also set individual media sources to "user" via the Media Manager UI.

**Note:** Only media files that actually exist on disk get claimed as user-sourced. If a media type is missing (e.g., you don't have a `dmd.png`), no entry is written for it. This means the next normal `--buildmeta` run will fill in any gaps by downloading the missing media from VPinMediaDB.

## VPX Table Patches
VPinFE can automaticlly pull patches from [vpx-standalone-scripts](https://github.com/jsm174/vpx-standalone-scripts) via the `--vpxpatch` CLI option if a matching patch can be found.  

`python3 main.py --vpxpatch`

## Mobile Transfer

VPinFE includes a mobile transfer feature for sending tables to the mobile version of VPinball on Android and iOS. Access it from the Manager UI sidebar ("Mobile Uploader") or directly at `http://{YOUR-IP}:8001/mobile`.

### Web Send
Transfers tables directly to a mobile device running VPinball's built-in web server. To use this:

1. Open VPinball on your mobile device and enable the web server in its settings
2. Note the IP address and port displayed in VPinball's settings
3. Enter the device IP and port in VPinFE's Mobile Uploader connection settings (saved to `vpinfe.ini` under `[Mobile]`)
4. Click "Check Device" to verify the connection and see which tables are already installed
5. Send individual tables or batch-send multiple selected tables

Tables already on the device are shown with a green checkmark. You can also delete tables from the device directly.

### VPXZ Download
Packages any of your tables into a `.vpxz` archive (zip format) for manual transfer. Click the download icon next to a table to generate and download the archive.

# Enabling the Shutdown Feature
If you plan on using the Shutdown/Reboot option in the frontend or in the remote you need to have the right permissions on some systems:

## Linux
`sudo nano /etc/polkit-1/rules.d/49-allow-poweroff.rules`

```
polkit.addRule(function(action, subject) {
    if (
        (
            action.id == "org.freedesktop.login1.power-off" ||
            action.id == "org.freedesktop.login1.power-off-multiple-sessions" ||
            action.id == "org.freedesktop.login1.power-off-ignore-inhibit" ||
            action.id == "org.freedesktop.login1.reboot" ||
            action.id == "org.freedesktop.login1.reboot-multiple-sessions" ||
            action.id == "org.freedesktop.login1.reboot-ignore-inhibit"
        ) &&
        subject.user == "superhac"
    ) {
        return polkit.Result.YES;
    }
});
```

`sudo systemctl restart polkit`

On Kubuntu/KDE, journal entries about `/run/polkit-1/rules.d` or `/usr/local/share/polkit-1/rules.d` not existing after the restart are normal and can be ignored.
