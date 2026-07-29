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
| assetsdir         | Root folder for shared assets such as manufacturer logos, served at `/assets/`. Defaults to `assets/` under the VPinFE config dir. Put your own logos in `manufacturers/user/` (e.g. `bally.png`); files there win over a downloaded pack in `manufacturers/default/`. The generated `manufacturers/manufacturers-reference.json` lists every known manufacturer with the filename it looks for. |
| startup_collection| Set the collection VPinFE starts up with.  Case sensitive, match collection name. |
| splashscreen      | Enable or disable the splash screen at startup. Default is `false`. |
| restorelasttable  | Open the wheel on the last table you launched instead of the first. Default is `true`. |

### [Input]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| joyleft           | Move left. Button mapping ids from `--gamepadtest`.                      |
| joyright          | Move right. Button mapping ids from `--gamepadtest`.                     |
| joyup             | Move up. Button mapping ids from `--gamepadtest`.                        |
| joydown           | Move down. Button mapping ids from `--gamepadtest`.                      |
| joypageup         | Page the wheel forward. Button mapping ids from `--gamepadtest`.         |
| joypagedown       | Page the wheel backward. Button mapping ids from `--gamepadtest`.        |
| pagingtype        | `alpha` (default) pages by letter; `numeric` pages by `pagingsize` tables. Alpha falls back to numeric on non-Alpha sorts. |
| pagingsize        | Tables per numeric page jump. Default is `10`.                           |
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

### [State]
Internal state written by VPinFE, not shown in the Manager UI.
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| lasttable         | Path of the last table you launched. Used by `restorelasttable` to reopen on that table. |

### [Media]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| tabletype         | If you're using a Full Single Screen or FSS set this to `fss`. Leaving it blank or any other valid will use the portrait table images. |
| tableresolution   | You can choose `1k` or `4k` to let the system know which resolution images you want to download when building the metadata. Leaving it blank will  default to 4K images. |
| wheelset          | Name of the wheel set to use library-wide. A set is a folder of alternate wheel art at `medias/wheels/<set>/` inside a table folder. The reserved name `logo` shows each table's game logo in the wheel slot. Blank means plain wheels. The active theme can override this with its own `wheelSet` option. |

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
    "assets": {
        "medias/bg.png": {
            "source": {
                "host": "vpinmediadb",
                "hash": "d80f67a370ebce2edd19febdc3fd7636"
            }
        },
        "medias/wheel.png": {
            "source": {
                "host": "vpinmediadb",
                "hash": "a88bcaf2ade6b9614417fc18a8782f78"
            }
        },
        "medias/cab.png": {
            "source": {"host": "user"}
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

- assets

  One entry per file VPinFE placed in the table folder, keyed by the file's path relative to that folder, with forward slashes. Preserved across `--buildmeta --update-all`. Replaces the old `Medias` section, which was keyed by media type and so could hold only one entry per type — no way to describe artwork belonging to one specific game file, and the same question applies to backglasses, ROMs and colorizations. Each entry holds a `source`:
  - host: who supplied the bytes — a remote such as "vpinmediadb", or "user" for a file uploaded through the Manager UI
  - hash: the MD5 the host published, when it published one. Absent for a user upload, since a hash is only meaningful compared against a remote.

  Nothing else is stored. Which media kind a file is, and which game file it belongs to, are read off its name every time media resolves, so a stored copy could only agree or be wrong.

  **A file with no entry is not ours.** Ownership is not decided from this section — the downloader hashes what is already on disk and compares it to the MD5 vpinmediadb publishes, so your own artwork is safe whether or not it appears here.

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

By default, `--buildmeta` downloads media artwork from [VPinMediaDB](https://github.com/superhac/vpinmediadb).

**Your own artwork needs no protecting.** Before the downloader touches a file that already exists, it hashes it and compares that to the MD5 VPinMediaDB publishes. If they match it is demonstrably our file and stays managed. Anything else — your own artwork, or our file after you replaced it — is left alone. A file we cannot prove is ours is never overwritten, and VPinMediaDB having no hash for it counts as cannot prove.

So drop your artwork in and run `--buildmeta` as normal. Missing kinds get filled in from VPinMediaDB; yours stay put.

### `--user-media` (With `--buildmeta`)

A modifier for `--buildmeta` that skips VPinMediaDB downloads entirely. Use it when you are supplying the whole library yourself and would rather not wait on the network at all.

```bash
# Build metadata without fetching any media
python3 main.py --buildmeta --user-media

# Rebuild all metadata, still fetching nothing
python3 main.py --buildmeta --update-all --user-media
```

### `--claim-user-media` (Deprecated)

Marked existing media as `"Source": "user"` so VPinMediaDB would not overwrite it. The downloader proves ownership by hash now, so there is nothing to mark. The flag still parses and does nothing; it will be removed in a later release.

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
