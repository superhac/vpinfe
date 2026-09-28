# Launchers

How a table gets played. Two nouns, and the difference between them is the whole model.

- **App** - the program that plays a table, and how to talk to it: which suffixes it claims, how to build a launch command, what its ini means, how to parse a table, how to resolve a ROM. Code, in `common/apps/`.
- **Launcher** - a configured wrapper around an app: an id, a display name, the app it wraps, an enabled flag, and values for that app's settings. User data, in `launchers.json`. No two launchers on an install share a name, whatever their app, compared ignoring case (`launchers.same_name`); Add and Duplicate ask for the name first; Add left blank, Duplicate's offer and the 2.x migration take the next free one (`launchers.free_name`).

A table names a launcher; a launcher names an app. An install ships one launcher wrapping `vpx`, seeded from the configuration it already had.

Because every launcher names an app, VPinFE always knows how to talk to it. A second VPX launcher inherits ROM resolution, table parsing and ini semantics for nothing, which is the property a launcher defined from scratch could not have.

## The apps

`common/apps/__init__.py` is the registry and `common/apps/contract.py` is the `App` contract.

Built-ins are `apps.vpx.VPX` and `apps.generic.GENERIC`, offered in that order. `generic` knows only suffixes, a binary and arguments: a launcher wrapping it can launch a file and nothing else, with no parsing, no ROM resolution, no ini overrides and no per-table configuration. It is a declared app rather than a special case so its reduced capability is visible rather than discovered.

Extensions contribute apps through `contribute()`, and `withdraw()` takes one back when the extension is disabled or reloaded. Contributed apps are always offered after the built-ins, so one cannot take a suffix out from under Visual Pinball by loading first, and an id already in use is refused rather than allowed to win. Ids are stored in a table's record, so two apps answering to one id would make what is stored ambiguous.

- `all_apps()` - every app this install has, in the order they are offered.
- `app_for(filename)` - which app claims a file, or `None`.
- `get(app_id)` - by id. An unknown id is a real state, not an error, because ids are stored.
- `app_name(app_id)` - what to call one on screen. Ids are for the wire.

## Where a launcher's settings live

`launchers.json` in the install's config directory, beside `collections.json`, `devices.json` and `players.json`. Not a config section.

A launcher is an object the user creates, names, duplicates, removes and switches off, rather than one of a fixed set of settings the install has. Nothing in the tree has a dynamically named config section and `config_schema` has no concept of one.

Seven keys left `general` and became four fields on the launcher, shedding the app's name:

| was | is |
|---|---|
| `general.vpx_bin_path` | `bin_path` |
| `general.vpx_ini_path` | `ini_path`, where no override was set |
| `general.global_ini_override` | `ini_path` |
| `general.vpx_launch_env` | `launch_env` |
| `general.vpx_log_delete_on_start` | `log_delete_on_start` |
| `general.global_game_ini_override_enabled`, `general.global_game_ini_override_mask` | retired: each table's `{stem}.{mask}.ini` became its `{stem}.ini`, where it had none |

A second launcher's fields are then the same names, which is what lets its editor be generated from the app's settings schema instead of hand-written per app. A 2.x config is migrated once rather than carrying seven permanent key aliases.

`ini_path` is the **Settings File**: the `VPinballX.ini` a table starts with and the one the Console's settings change. One that is not Visual Pinball's own is passed as `-ini`. Empty means Visual Pinball's own, which VPinFE finds where the program keeps it: the newest version folder under its preferences folder (`~/.local/share/VPinballX/10.8/` on Linux, `~/Library/Application Support/VPinballX/10.8/` on macOS, `%APPDATA%\VPinballX\10.8\` on Windows), then beside the program, then the layouts from before version folders.

A table launched to be recorded (`SOURCE_CAPTURE`) is given a copy of the Settings File instead, through the app's capture hook (`common/apps/contract.py` `Capture`). Visual Pinball's (`apps/vpx/capture.py`) writes it with `SyncMode = 0` and `MaxFramerate = -1`, the frame cap at the display's refresh, because at its own frame pacing VPX runs at half rate while a screen is being recorded; and, unless the table's sound is recorded, with `PlaySound` and `PlayMusic` off and both volumes at 0. Where the table's own settings file sets any of those, a copy of it with the recording's values goes in with `-tableini`, since the table's value would win. The copies live in `capture/launch/` under the config directory for as long as the table runs. The Settings File itself is never written: VPX writes back the file it was given when it exits.

The same hook says where the app shows each window, so a recording looks at the output VPX draws on rather than at VPinFE's own screen ids, which on Wayland place nothing. Visual Pinball's reads `PlayfieldDisplay` and each of `BackglassOutput`/`BackglassDisplay`, `ScoreViewOutput`/`ScoreViewDisplay` and `TopperOutput`/`TopperDisplay`, the table's own file over the Settings File where VPX reads that key from a table. The output is the first word inside the parentheses a display name ends with, as SDL names a Wayland output: `Samsung Electric Company SAMSUNG 0x00000001 (DP-1 via HDMI)` is `DP-1`. An Output other than 1 (Floating) shows that window on no screen of its own. A display name with no parentheses says nothing, and the recording falls back to VPinFE's screen ids. Once the table is up, the desktop's own list of windows, matched by the titles VPX gives them (`Visual Pinball Player`, `Visual Pinball Backglass`, `Visual Pinball Score View`), answers over all of it.

`owns_ini` records whether VPinFE created the file `ini_path` names.

**A launcher is per install.** A binary path and an ini path are facts about one machine; `common/launcher_path.py` exists only because macOS hands you a `.app` bundle and Linux hands you an executable.

## Per-table assignment

A table pointed at a specific launcher is recorded in `launchers.json` under `MAPPINGS_KEY`, not in the table's `.info`.

A table's **Launcher** picker shows the launcher that plays it. It lists the table's own app's launchers first, its default marked *Default*, then *Other Programs* (`launchers.launcher_offer` in the Console). A switched-off launcher is left out unless the table names it. A table that chose its own carries a dot, amber where the one it chose is switched off, and **Clear** takes it back to the default. One played by another program's launcher says what it gives up, where its own app has settings: *Runs with Generic - Visual Pinball X's settings, ROM and start-up check don't apply*.

## Resolution

Two functions in `common/games/launchers.py`, and the second is the one that decides.

- `launcher_for_entry(app_id, table_id, launchers, mappings)` - what the entry names, then the default for its app. By app rather than by filename, because an entry with no file has no suffix to resolve through.
- `launcher_for_table(filename, table_id, launchers, mappings)` - for callers holding a name off a directory listing. It resolves the app from the suffix and delegates.

The default for an app is the first enabled launcher wrapping it, so the file's order answers "which is the default". Making one the default, from its **Default** switch or `POST /launchers/{id}/default`, moves it to the front (`LauncherStore.to_front`). A switched-off launcher cannot be made the default, and the default's own switch cannot be turned off: another launcher is made the default instead.

One path, so the grid's effective-launcher column and the launch path cannot disagree.

## Enable, disable and fallback

Disabling is non-destructive: it hides a launcher from pickers, and tables already assigned to it keep their assignment. Removal is the destructive one and asks about its tables.

A table assigned to a disabled launcher **falls back** to the default for its app rather than refusing to launch. The fallback is honest and silence about it is what turns a configuration choice into a mystery, so it is said in three places:

1. At the transition, a confirm dialog naming the impact, count first: *"Switch off “VPX (4K)”? 4 tables use it. Switched off, they launch with Visual Pinball X."* A launcher no table uses goes off without asking. Where its tables would go to a launcher with no program, or to none, switching it off is refused and the switch stays on: *"Switched off, its tables would go to Visual Pinball X, which has no program."* `GET /api/v1/launchers/{id}/fallback` answers the same question without switching anything. Making a launcher with no program the default is the other way to send tables to nothing, and it is refused the same way: its **Default** switch is disabled, *“VPX (4K)” has no program*.
2. While the state persists, a mark on the row: not *set here and in effect*, not *following the default*, but *set here and overridden*. The Launcher column's dot, which says a table chose its own, turns amber beside the name of the launcher that plays it instead, and the table's picker marks it the same way. A table row carries it as `launcher_falls_back`.
3. At launch, a log record saying which table, which launcher it asked for, why that did not happen, and what ran instead.

## The API

`docs/http_api.md` documents the endpoints, in its Endpoints table and its Launcher settings section.

## The Console

Launchers is a subject under Frontend, beside Themes. Both are gated on the `frontend` feature, so an install without it shows neither. It is not a group in Settings, because Settings is label-and-value pairs and a launcher is an object to manage.

The grid says how many tables each launcher plays (`tables` on `GET /launchers`, counted through `launcher_for_entry`), and a state only where one cannot play them: *No Program*, *Program Missing* or *Switched Off*. A ready launcher's state is blank.

A launcher's panel opens on **Details**: its name, whether it is the default and whether it is on, then what it runs and how. Then a section for each area its app declares, drawing only the rows the app curates for it (`ConfigGroup.curated`), under its sub-headings. A heading led by a switch (`Heading.enabled_by`, as every plugin is by its *Enable*) draws its other rows only while the switch is on, and a row a switch of its own gates (`Heading.switched`, as each window's *Video Mode* is by its *Fullscreen* and each B2S plugin's DMD rows are by its *DMD Overlay*) is drawn only while that one is, or only while it is off where the gate is `Switched.on=False`: a window's *Position* and *Size* are drawn only while it is not fullscreen, and a B2S plugin's *Backglass DMD Position* and *Backglass DMD Size*, and its score view's, only while that automatic position is off, because VPX reads them only then. VPX's Plugins area has a heading for each plugin the installed program has, named and described by that plugin's own `plugin.cfg`. A switch that is on while its rival is (`Heading.rivals`: *B2S* and *B2S Legacy*, of which a table gets one) carries **Conflict**, whose hover names the other, wherever the row is drawn. A pair (`Heading.pairs`) draws two of a heading's rows as one, two numbers on a line with a joiner between them: VPX pairs each window's full-screen width and height as *Video Mode*, its X and Y as *Position* and its width and height as *Size*. Its words are the app's, `group.<key>.pair.<pair>.label`, `.note` and `.joiner`. An area ends with how many of its settings it does not draw, which opens All Settings on that area, and a search box at its top carries what is typed into All Settings. An area the app curates nothing for is drawn whole.

Then **All Settings**: every setting the program keeps, in the program's own words. Its search matches the label, the key and the program's description, each word anywhere, so a key copied out of the ini finds its row. Three filters narrow it: **Set Here** (in this launcher's settings file), **Different from Default**, and the area, where *Other* holds the settings no area does. Results sit under the program's section names made readable - *Player*, *Score View*, *Plugin: PinMAME* - a plugin taking the name its area gives it, and a plugin no area heads its id in words, *Plugin: Hello World*. A pair is one row here too, found whole where either of its numbers is.

A setting's row marks where its value comes from, the same way here and in a table's **Settings** (`workbench._marked` and `_config_mark`). A dot before the value means this scope sets it; **Clear**, at the end of the value's line, goes back to what it would follow. A pair takes one dot and one **Clear** for both of its numbers. The dot is amber beside *Ignored*, where the program does not read the value set here, and the value's hover names what it reads instead: *All Tables has its own: Off*. Hovering any value says whose it is - *Set here*, *Same as Visual Pinball X's default* where the value set is the default, the scope it follows, or *Visual Pinball X's default* where nobody set it. Only exceptions take a word: at a table, a value from All Tables takes none, and one from This Game does. At the launcher, a row that some of its tables answer over for themselves says how many, *4 tables set their own*, as a link to the Tables grid filtered to exactly those tables: the ones this launcher plays whose settings file, their own or their game's, sets that key (`launcher_settings_keys`).

A table's **Settings** section (`console/app_settings.py`) comes after **Table** on its rail. It holds the launcher that plays the table and **Clear NVRAM on Exit**, then the program's settings for this table - the table's differences and nothing else: what its own file sets and what reaches it from the game's, by area. Its **Point of View** is the view mode of each view it starts in, editable, then the camera as one row, *Saved for this table* or *The table's own*, with **Reset**. The table options its file holds are listed as it holds them, each with **Reset**, and **Reset All** where there are two or more. With none it says *Same as all tables*, and **Show Every Setting** opens All Settings at this table. **Add a Setting** stands at the foot of the program's settings, or under *Same as all tables*, and is typed into: the settings commonly set for one table first (`per_table`, which counts the view modes of the views the table starts in), then every other one the program keeps for a table, each with its area under it (`panel.SettingPicker`). Picking one draws its row in its area with the value the table uses now, focused; nothing is written until it is changed, and a row added and left alone goes when another table is opened. A pair is one row here as well, listed whole where the table sets either of its numbers and named by its window or plugin, *Backglass Size* or *B2S: Backglass DMD Position*, the name **Add a Setting** offers it by once. At a game whose other tables run on the same program, a value the table sets itself carries **Set for All N Tables** beside **Clear** wherever another of those tables does not use it yet: the value goes into each one's own file, the table whose file is also the game's first, so the tables reading that file are not given one of their own, and any table that stops reading a game file made by hand is named in a warning. On a pair it writes each of the two the table sets. The camera and the table options are one table's own and do not carry it. Where the table has a file of its own and the game's file sets values it does not (`from_game`), a line counts them, with **Copy the Game's Settings Here**, which writes them into the table's file under what it already sets. A value set equal to what all tables use clears the table's own instead. A setting the table's file holds that the program reads only for all tables stays listed as *Ignored*, read-only, with **Clear**. One the program keeps for all tables but still reads from the table's file when the table starts (the backglass, score view and topper windows' Display Mode and full-screen size, and some graphics settings) is listed as the table's own, read-only, with **Clear**. **Launch** reports the launcher in one line, with how many settings the table has of its own or from its game, as a link to the section.

A backglass file's panel, in Assets, has a **Settings** section after **File** (`workbench._file_settings`), holding the headings the app ties to that kind of file (`Heading.kinds`): in VPX, *B2S* and *B2S Legacy*, each under its *Enable*, with the grill, the DMD drawn on the backglass art, *Backglass DMD Position* and *Backglass DMD Size*, and the same for the score view. They are the table's own values, written by the same writer as the table's **Settings**, so a value set in either shows in the other, and **Clear** goes back to all tables. Where the file is the game's and several tables use it, the section is theirs together (`app_settings.as_one`, `app_settings.write_shared`): a line says how many tables it writes to and names them on hover, a change goes into each table's own file the way **Set for All N Tables** does, naming any table that stops reading a game file, and **Clear** clears it at each table that sets it. A row where the tables use different values reads *Varies*, with each table's value on hover, and its control holds none of them - a switch neither on nor off, which counts as on for the rows under it. The section is absent where the file is missing, where one of the tables it is used by runs another program, or where a launcher has no program or keeps no settings.

The Tables grid's **Settings** column, in its Launch view, says the same of every table: *Point of View* where its file holds only a saved camera, *3 of its own*, *2 from This Game* where it reads its game's file, or nothing where it plays as all tables do. It filters by those, *Has Settings of Its Own* first, and focusing a cell opens that table's **Settings**. **Own Settings**, in no view until it is asked for, names which, one chip for each setting the Settings column counts, a saved camera among them as *Point of View*. A name two settings share, such as *Width* or *Enable*, carries the heading or section it sits under, *Backglass Width*, *B2S Enable*. The names come from one settings read per launcher that plays a table, made when the table list is read. An address carrying `launcher` and `sets`, a setting's key or several comma separated, arrives on the Tables grid filtered to that launcher's tables that set any of them, which is where the launcher's link goes.
