## vpinfe.json Definition

VPinFE stores its settings as JSON in a platform-specific configuration directory. On
first run it writes a complete `vpinfe.json` there, so a new install never needs the file
opened by hand:

- **Linux**: `~/.config/vpinfe/vpinfe.json`
- **macOS**: `~/Library/Application Support/vpinfe/vpinfe.json`
- **Windows**: `C:\Users\<username>\AppData\Local\vpinfe\vpinfe\vpinfe.json`

A `vpinfe.ini` from an earlier build is read once, converted, and kept, so downgrading
still works. Settings live under a `settings` object beside a `schema` version, and each
heading below is a key in it - `windows.playfield` is a `playfield` object inside a
`windows` object.

Every name a setting has ever had keeps resolving, so an older file and a hand-edit that
uses an old spelling both still load.

<!-- generated from common/config_schema.py by tests/support/config_reference.py -->

### `windows.backglass`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `screen_id` | int |  | Backglass Monitor ID |
| `window_override` | string |  | Backglass Window Override (x,y,width,height) |
| `media_priority` | choice (video, image) | `video` | Backglass Media Priority |

### `windows.scoreview`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `screen_id` | int |  | DMD Monitor ID |
| `window_override` | string |  | DMD Window Override (x,y,width,height) |
| `media_priority` | choice (video, image) | `video` | DMD Media Priority |

### `windows.playfield`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `screen_id` | int | `0` | Playfield Monitor ID |
| `orientation` | choice (landscape, portrait) | `landscape` | How the playfield screen is physically mounted. Portrait means it is turned on its side in the cabinet. This does not rotate anything by itself - it tells themes what shape to lay out for. |
| `rotation` | choice (0, 90, 180, 270) | `0` | How far VPinFE turns its own display so it faces the player. Leave at 0 if your operating system already rotates this screen. |
| `variant` | choice (table, fss) | `table` | Which playfield artwork this library holds: table.png, or fss.png for art captured in Visual Pinball's Full Single Screen mode. |
| `resolution` | choice (4k, 1k) | `4k` | Default Table Resolution |
| `video_resolution` | choice (4k, 1k) | `1k` | Default Table Video Resolution |
| `media_priority` | choice (video, image) | `video` | Table Media Priority |
| `media_rotation` | choice (auto, 0, 90, 180, 270) | `auto` | How far to turn playfield artwork so it fills the screen. auto measures each image and turns only when it disagrees with the surface. |

### `displays`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `cab_mode` | bool | `false` | Presents VPinFE for playing standing at a cabinet: larger text and targets, and no controls that need a mouse. It does not rotate anything. |

### `general`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `vpx_bin_path` | string |  | Full path to the Visual Pinball executable VPinFE launches. |
| `vpx_launch_env` | string |  | VPX Launch Environment |
| `global_ini_override` | string |  | Global ini Override (/home/test/mysuper.ini) |
| `global_game_ini_override_enabled` | bool | `false` | Global tableini Override Enabled |
| `global_game_ini_override_mask` | string |  | Global tableini Override Mask |
| `game_root_dir` | string |  | The folder holding your table folders, one folder per game. |
| `vpx_ini_path` | string |  | Path to VPinballX.ini, which VPinFE reads for the key mappings the Remote page sends. |
| `assets_dir` | string |  | Root folder for assets shared across games rather than owned by one, such as manufacturer logos. Served at /assets/ and defaults to assets/ under the VPinFE config dir. |
| `rar_tool_path` | string |  | RAR Tool Path (unar/unrar, blank = auto-detect) |
| `vpx_log_delete_on_start` | bool | `false` | Delete VPinball Log On Table Start |
| `theme` | string | `Revolution` | Active Theme |
| `startup_collection` | string |  | Default Startup Collection |
| `auto_update_media_on_startup` | bool | `false` | Auto Update Media On Startup |
| `splashscreen` | bool | `false` | Enable splashscreen |
| `mute_audio` | bool | `false` | Mute Frontend Audio |
| `chrome_options` | string |  | Additional Chrome Options |
| `chrome_options_exclude` | string |  |  |
| `disable_default_chrome_options` | bool | `false` | Disable Default Chrome Options |
| `hide_quit_button` | bool | `false` | Hide Quit from MainMenu |
| `restore_last_game` | bool | `true` | Restore Last Table |

### `themes`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `registries` | list | `https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json` | Catalogs to offer themes from, most trusted first. The stock registry is an entry like any other, so a mirrored or offline install can replace or drop it. |
| `repositories` | list |  | Individual theme repos, each one a theme in its own right. Resolved before the registries, and named for the repo with any vpinfe-theme- prefix removed. |

### `lifecycle`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `confirm` | list |  | Scopes to ask about before acting: frontend, app, system. Empty asks about nothing, which is how VPinFE has always behaved. The question is put to whichever surface asked. |

### `logger`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `level` | choice (debug, info, warning, error) | `debug` | Log Verbosity |
| `console` | bool | `true` | Console Logging |

### `media`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `default_missing_media_image` | string |  | Default Missing Media Image |
| `thumb_cache_max_mb` | int | `500` | Thumbnail Cache Max (MB) |
| `wheelset` | string |  | Name of the wheel art set to use library-wide, a folder under a game's medias/wheels/. The reserved name logo shows each game's logo instead. Blank means plain wheels, and the active theme can override this with its own wheelSet option. |
| `realdmd_media_priority` | choice (color, video, image) | `color` | Real DMD Priority |

### `install`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `id` | string |  | Written by VPinFE on first start, and not meant to be edited. A hub tells its installs apart by this, so changing it makes this a different install. |
| `display_name` | string |  | What to call this install where one is listed. Defaults to this machine's hostname. Nothing is addressed by it, so renaming is safe. |
| `roles` | list | `hub,player` | What this install serves: the shared library half (hub), the machine games launch on (player), or both. |

### `vpsdb`

Runtime state written by VPinFE, not shown in the Manager UI.

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `last` | string |  |  |

### `state`

Runtime state written by VPinFE, not shown in the Manager UI.

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `last_game` | string |  |  |

### `pinmame_score_parser`

Runtime state written by VPinFE, not shown in the Manager UI.

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `roms_update_sha` | string |  |  |

### `network`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `theme_assets_port` | int | `8000` | Theme Server Port |
| `ws_port` | int | `8002` | Port the frontend windows and the theme talk to VPinFE over. Loopback only. |
| `manager_ui_port` | int | `8001` | Manager UI Port |

### `dof`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `enable_dof` | bool | `false` | Enable DOF |
| `dof_config_tool_api_key` | string |  | DOF Config Tool API Key |

### `libdmdutil`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `enabled` | bool | `false` | Enabled |
| `pin2dmd_enabled` | bool | `false` | Enable |
| `pixelcade_device` | string |  | PixelcadeDevice |
| `zedmd_device` | string |  | ZeDMDDevice |
| `zedmd_wifi_address` | string |  | ZeDMDWiFiAddr |

### `mobile`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `device_ip` | string |  | Mobile Device IP |
| `device_port` | int | `2112` | Mobile Device Port |
| `chunk_size` | int | `1048576` | Mobile Chunk Size |
| `rename_mask_to_default_ini` | bool | `false` | Enable Rename Mask To Default INI |
| `rename_mask_to_default_ini_mask` | string |  | Rename Mask To Default INI Mask |

### `vpinplay`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `sync_on_exit` | bool | `false` | Sync on Exit |
| `api_endpoint` | string | `https://api.vpinplay.com:8888` | API Endpoint |
| `user_id` | string |  | User ID |
| `initials` | string |  | Initials |
| `machine_id` | string |  | Machine ID |

### `input`

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `previous` | list | `key:ArrowLeft,key:ShiftLeft` | Previous |
| `next` | list | `key:ArrowRight,key:ShiftRight` | Next |
| `page_up` | list | `key:PageUp,key:ArrowUp` | Page up |
| `page_down` | list | `key:PageDown,key:ArrowDown` | Page down |
| `select` | list | `key:Enter` | Select |
| `back` | list | `key:b` | Back |
| `menu` | list | `key:m` | Menu |
| `collection_menu` | list | `key:c` | Collection menu |
| `tutorial` | list | `key:t` | Tutorial |
| `exit` | list | `key:Escape,key:q` | Exit |
| `paging_type` | choice (alpha, numeric) | `alpha` | Paging Type |
| `paging_size` | int | `10` | Paging Size |

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
        "default_table": "123(Talleres de Llobregat 1973) v601.vpx",
        "delete_nvram_on_close": false,
        "alt_launcher": "",
        "plugin_profile": "",
        "alt_title": "",
        "alt_vpsid": "",
        "frontend_dof_event": "",
        "run_time_seconds": 0
    },
    "tables": {
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
  `tables`.

- User

  Stores per-user data for the game. Preserved across `--buildmeta --update-all`:
  - Rating: User rating (0–10)
  - Favorite: Favorite flag (0/1)
  - LastRun: Timestamp of last play
  - StartCount: How many times played
  - RunTime: Total playtime in minutes, rounded down. Derived from
    `vpinfe.run_time_seconds`, which is what actually accumulates — a key fixed by the
    VPX spec cannot hold the seconds, and adding whole minutes per session charged a
    few seconds at a table the same as a few minutes.
  - Tags: Array of custom tags

- tables

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
  - run_time_seconds: total play time. This is the counter that accumulates; `User.RunTime`
    is it rounded down to whole minutes. Written on the first play after upgrading, seeded
    from whatever `User.RunTime` already held.
  - plugin_profile, alt_title, alt_vpsid, frontend_dof_event

  `alt_vpsid` is a manual VPS match: automatic matching got the game wrong, and somebody
  looked up the right record and said so. It overrides `Info.VPSId` everywhere an id is
  used - collections, media matching, the VPinPlay payload.

  It **stops applying** when the default table's hash changes during a rebuild, because
  the claim was made about the file that was there and that file has been replaced.
  Matching falls back to `Info.VPSId`.

  - alt_vpsid_previous

  The superseded override, set aside rather than deleted: `{"value", "table",
  "set_aside"}`. **Nothing resolves through it** - it is what the user typed, kept so it
  can be offered back rather than retyped from memory. Only the most recent is kept; a
  claim made two tables ago is history nobody will restore. Absent when there was no
  override to set aside.

- assets

  One entry per file VPinFE placed in the game folder, keyed by the file's path relative to that folder, with forward slashes. Preserved across `--buildmeta --update-all`. Replaces the old `Medias` section, which was keyed by media type and so could hold only one entry per type — no way to describe artwork belonging to one specific table, and the same question applies to backglasses, ROMs and colorizations. Each entry holds a `source`:
  - host: who supplied the bytes — a remote such as "vpinmediadb", or "user" for a file uploaded through the Manager UI
  - hash: the MD5 the host published, when it published one. Absent for a user upload, since a hash is only meaningful compared against a remote.

  Nothing else is stored. Which media kind a file is, and which table it belongs to, are read off its name every time media resolves, so a stored copy could only agree or be wrong.

  **A file with no entry is not ours.** Ownership is not decided from this section — the downloader hashes what is already on disk and compares it to the MD5 vpinmediadb publishes, so your own artwork is safe whether or not it appears here.

#### Upgrading from a 2.x file

Files written before schema 2 have no `schema` key, and are migrated the first time VPinFE
reads them: `VPXFile` becomes the first `tables` entry, `VPinFE` becomes `vpinfe` with
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
