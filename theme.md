# Themes

VPinfe uses pywebview to render the screens and is basically a webkit browser window.  Currently three screens are supported and their pywebview window names are as follows:
- table
- bg
- dmd

Each window has its own webpage, but shares a single instance of the VPinfe API ([frontend/api.py](https://github.com/superhac/vpinfe/blob/master/frontend/api.py)) and is access via [vpinfe-core.js](#vpinfe-corejs).  A theme is created in the `web/theme` dir and has this basic layout:
```
<THEME NAME>
├── index_bg.html
├── index_dmd.html
├── index_table.html
├── style.css
└── theme.js
```

Depending on how the user has their screens configued after the splash screen it will load the respective html page for each page.  These files need to be named exactly how they are listed below.

| File | Desc |
|--------|-----|
|index_table.html | The main screen. Also the controller for all other screens and input. |
|index_bg.html | Would normally be the Blackglass screen |
|index_dmd.html | Would normally be the FULLDMD screen.  This is not a "real dmd" , like ZeDMD. |

Then you have other files.  These can really be any name you want.
| File | Desc |
|--------|-----|
|style.cs|Your CSS style sheet|
|theme.js|The base JS for interacting with the VPinFE API and all your own JS for controlling the interface|

The user selects the theme by setting this in the `vpinfe.ini`:
```
[Settings]
theme = <THEME NAME>
```

## vpinfe-core.js
This is the Javascrip interface to the VPinFE API.  Must be loaded into your theme from `../../common/vpinfe-core.js` as:
```
<script src="../../common/vpinfe-core.js"></script>
```

### API

#### init()

- Sets up:

  - Keyboard event listener.

  - pywebviewready listener, which loads monitors, table data, and gamepad mapping.

#### registerInputHandler(handler)

- Registers an input handler for the table screen.

- Only works when the current window name is "table".

#### registerInputHandlerMenu(handler)

 - Registers an input handler for the menu.

#### call(method, ...args)

- Invokes a pywebview.api method if available.

- Throws an error if the method does not exist.

#### getImageURL(index, type)

- Returns a web server URL for a table’s image.

- type can be "table", "bg", "dmd", "wheel", "cab".

- Falls back to "../../images/file_missing.png" if missing.

#### getTableMeta(index)

- Returns metadata for a given table.

#### getTableCount()

- Returns the number of tables.

#### sendMessageToAllWindows(message)

- Sends an event to all windows except self.

#### sendMessageToAllWindowsIncSelf(message)

- Sends an event to all windows including self.

#### launchTable(index)

- Disables gamepad input.

- Calls backend to launch the selected table.

- Re-enables gamepad input afterward.

#### getTableData(reset=false)

- Loads table metadata from backend into tableData.

