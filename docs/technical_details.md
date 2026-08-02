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
| playfieldscreenid     | playfieldscreenid screen number.  use `--listres` to get your mointor ids. Leave blank if no display    |

### [Settings]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| vpxbinpath        | Full path to you vpx binary.  e.g. /apps/vpinball/build/VPinballX_BGFX    |
| gamerootdir      | The root folder where all your games are located.  e.g /vpx/tables/      |
| assetsdir         | Root folder for shared assets such as manufacturer logos, served at `/assets/`. Defaults to `assets/` under the VPinFE config dir. Put your own logos in `manufacturers/user/` (e.g. `bally.png`); files there win over a downloaded pack in `manufacturers/default/`. The generated `manufacturers/manufacturers-reference.json` lists every known manufacturer with the filename it looks for. |
| startup_collection| Set the collection VPinFE starts up with.  Case sensitive, match collection name. |
| splashscreen      | Enable or disable the splash screen at startup. Default is `false`. |
| restorelastgame  | Open the wheel on the last game you launched instead of the first. Default is `true`. |

### [Input]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| joyleft           | Move left. Button mapping ids from `--gamepadtest`.                      |
| joyright          | Move right. Button mapping ids from `--gamepadtest`.                     |
| joyup             | Move up. Button mapping ids from `--gamepadtest`.                        |
| joydown           | Move down. Button mapping ids from `--gamepadtest`.                      |
| joypageup         | Page the wheel forward. Button mapping ids from `--gamepadtest`.         |
| joypagedown       | Page the wheel backward. Button mapping ids from `--gamepadtest`.        |
| pagingtype        | `alpha` (default) pages by letter; `numeric` pages by `pagingsize` games. Alpha falls back to numeric on non-Alpha sorts. |
| pagingsize        | Games per numeric page jump. Default is `10`.                           |
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
| lastgame         | Path of the last game you launched. Used by `restorelastgame` to reopen on that game. |

### [Media]
| Key               | Description |
| ----------------- | ------------------------------------------------------------------------- |
| playfieldvariant         | If you're using a Full Single Screen or FSS set this to `fss`. Leaving it blank or any other valid will use the portrait playfield images. |
| playfieldresolution   | You can choose `1k` or `4k` to let the system know which resolution images you want to download when building the metadata. Leaving it blank will  default to 4K images. |
| wheelset          | Name of the wheel set to use library-wide. A set is a folder of alternate wheel art at `medias/wheels/<set>/` inside a game folder. The reserved name `logo` shows each game's logo in the wheel slot. Blank means plain wheels. The active theme can override this with its own `wheelSet` option. |

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

## Game Metadata File (based on the Zero install table format)
When you run VPinFE with the `--buildmeta` option it recursively goes through your game directory attempts to match your games to their VPSDB id.  When matched, it will then parse the VPX for the game for more meta information and produce a `GAME FOLDER NAME(manufactuer year).info` in that game's directory.  Heres an example for the game 1-2-3:

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
        "VPSId": "HhMnyw53"
    },
    "User": {
        "Rating": 0,
        "Favorite": 0,
        "LastRun": null,
        "StartCount": 0,
        "RunTime": 0,
        "Tags": []
    },
    "vpinfe": {
        "schema": 2,
        "id": "tuF3WogthK",
        "default_game_file": "123(Talleres de Llobregat 1973) v601.vpx",
        "delete_nvram_on_close": false,
        "alt_launcher": "",
        "plugin_profile": "",
        "alt_title": "",
        "alt_vpsid": "",
        "frontend_dof_event": ""
    },
    "game_files": {
        "123(Talleres de Llobregat 1973) v601.vpx": {
            "file_hash": "d685ce54d659fadcafd90a296473fb126754aa23b1145f457c6626aa5baa75d9",
            "vbs_hash": "bd6dcb7e0c618e4553d230095e73c7ca8e17f31def4595c38a8439b279977b45",
            "version": "6.0.1",
            "release_date": "2026-01-25",
            "save_date": "2026-01-25T22:24:36",
            "save_rev": "91",
            "manufacturer": "",
            "year": "",
            "type": "",
            "rom": "TlD_123",
            "authors": [
                "jpsalas",
                "akiles50000",
                "Loserman76"
            ],
            "detect_nfozzy": false,
            "detect_fleep": false,
            "detect_ssf": true,
            "detect_lut": true,
            "detect_scorbit": false,
            "detect_fastflips": false,
            "detect_flex": false,
            "user": {
                "last_run": null,
                "start_count": 0,
                "run_time_seconds": 0
            }
        }
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

  Contains the core game metadata sourced from VPSdb and the VPX file:
  - IPDBId: Internet Pinball Database ID (if available)
  - Title: Game name
  - Manufacturer, Year, Type (EM, SS, etc.)
  - Themes: Array of themes
  - VPSId: Internal VPS database ID
  - Description: Game description/blurb

  Authors and Rom used to live here too. Both are properties of a table rather than of
  the machine — a folder can hold several, and they can disagree — so they moved to
  `game_files`.

- User

  Stores per-user data for the game. Preserved across `--buildmeta --update-all`:
  - Rating: User rating (0–10)
  - Favorite: Favorite flag (0/1)
  - LastRun: Timestamp of last play
  - StartCount: How many times played
  - RunTime: Total playtime in minutes
  - Tags: Array of custom tags

- game_files

  One entry per `.vpx` in the folder, keyed by filename. A game folder can hold a desktop
  build, a VR build and a patched one, and every visible entry is independently launchable —
  they are peers, not a primary with alternates. Each entry holds what that file says about
  itself:
  - file_hash, vbs_hash, version
  - release_date, save_date, save_rev — normalized to ISO 8601, at whatever precision the
    author actually gave. An unreadable or ambiguous date degrades to the year rather than
    being guessed at.
  - manufacturer, year, type — the `.vpx`'s own claim, which can differ from what VPS says
    in `Info`. Both are kept: the disagreement is a signal.
  - rom, authors
  - detect_* flags: what was found in the table's script
  - hidden: set to keep a table out of the frontend without deleting it — a patch base
    has to stay on disk, but should not be offered
  - user: play history for this table alone (last_run, start_count, run_time_seconds).
    It accumulates separately from `User`, which is the game's own history.

- vpinfe

  VPinFE-specific settings for the game, preserved across `--buildmeta --update-all`:
  - schema: the version of this file's shape. Absent means a 2.x file, which is migrated on
    first read — see below.
  - id: the game's stable local identity, used in the API, in events and in collections
  - default_table: which table a consumer that can only take one should get
  - delete_nvram_on_close: (true/false) Some games, like Taito machines, retain the game
    state when you quit. Enabling this deletes the NVRAM file on close. Default is false.
  - alt_launcher: Optional executable path override for this game alone. If set, it is used
    instead of `vpinfe.ini` `Settings.vpxbinpath`.
  - plugin_profile, alt_title, alt_vpsid, frontend_dof_event

  `alt_vpsid` is cleared when the default table's hash changes during a rebuild, since a
  manual VPS match was chosen against the file that was there.

- assets

  One entry per file VPinFE placed in the game folder, keyed by the file's path relative to that folder, with forward slashes. Preserved across `--buildmeta --update-all`. Replaces the old `Medias` section, which was keyed by media type and so could hold only one entry per type — no way to describe artwork belonging to one specific table, and the same question applies to backglasses, ROMs and colorizations. Each entry holds a `source`:
  - host: who supplied the bytes — a remote such as "vpinmediadb", or "user" for a file uploaded through the Manager UI
  - hash: the MD5 the host published, when it published one. Absent for a user upload, since a hash is only meaningful compared against a remote.

  Nothing else is stored. Which media kind a file is, and which table it belongs to, are read off its name every time media resolves, so a stored copy could only agree or be wrong.

  **A file with no entry is not ours.** Ownership is not decided from this section — the downloader hashes what is already on disk and compares it to the MD5 vpinmediadb publishes, so your own artwork is safe whether or not it appears here.

#### Upgrading from a 2.x file

Files written before schema 2 have no `schema` key, and are migrated the first time VPinFE
reads them: `VPXFile` becomes the first `game_files` entry, `VPinFE` becomes `vpinfe` with
snake_case keys, `User.FrontendDOFEvent` moves to `vpinfe.frontend_dof_event`, and `Medias`
is dropped.

Nothing is written until something would have written anyway, and when it does, the original
is kept first as `<Game>.info.vpinfe-<timestamp>` — for example
`Table Name (Bally 1995).info.vpinfe-20260729T143022Z`. The timestamp is UTC, so restore
points sort and accumulate rather than overwriting each other. **To go back, rename one over
the `.info`.** Which schema a backup holds is read from its contents, not its name: no
`schema` key means it is a 2.x file.

After that file is created it then attempts to download the media artwork for that game from [VPinMediaDB](https://github.com/superhac/vpinmediadb). All media images are stored in a `medias/` subfolder within each game's directory:

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
