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

## index_table.html

This is the main html file used to control and interact with the VPinFE API.  This is also the window where the in theme main menu gets rendered. Below is the minium required to make things work.

A plain example used in the `web/theme/template` theme. 
```
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>VPinFE - Template</title>
  <link rel="stylesheet" href="../../common/vpinfe-style.css">
  <link rel="stylesheet" href="style.css">
  <script src="../../common/vpinfe-core.js"></script>
  <script src="theme.js"></script>
</head>
<body>
  <div id="rootContainer">
  </div>
  <div id="overlay-root">
        <!-- Independent popup or menu overlay -->
  </div>
</body>
</html>
```

The `common` includes:

```
<link rel="stylesheet" href="../../common/vpinfe-style.css">
<script src="../../common/vpinfe-core.js"></script>
```

These are the core of VPinFE interface.  The `vpinfe-core.js` is the interface to the pywebview API.  It includes all the calls for getting table data and joystick/keyboard interface.  `vpinfe-style.css` needs to be included because that is the style sheet we use to render the in theme Menu system. 

`theme.js` and `style.css` are your JS and CSS respectivietly.  You can name those whatever you want.

Refer to the [web/theme/template](https://github.com/superhac/vpinfe/tree/master/web/theme/default) for a full example with the bare bones.  

## index_bg.html & index_bg.html

The same as above.

## theme.js
The base JS for interacting with the VPinFE API and all your own JS for controlling the interface

```
/*
Bare minimum example of how a theme can be implemented.
*/

// Globals
windowName = ""
currentTableIndex = 0;
lastTableIndex = 0;

// init the core interface to VPinFE
const vpin = new VPinFECore();
vpin.init();
window.vpin = vpin // main menu needs this to call back in.


// wait for VPinFECore to be ready
vpin.ready.then(async () => {
    console.log("VPinFECore is fully initialized");
    // blocks
    await vpin.call("get_my_window_name")
        .then(result => {
            windowName = result;
        });
    // register your input handler.  VPinFECOre handles all the input(keyboard or gamepad)and calls your handler when input is detected.
    vpin.registerInputHandler(handleInput);

    // register a window event listener.  VPinFECore sends events to all windows.
    window.receiveEvent = receiveEvent;  // get events from other windows.

    //
    // anything you want to run after VPinFECore has been initialized the first time.
    //

    // example load a config.json file from your theme dir.  You can use this to have users customize options of your theme.
    config = await vpin.call("get_theme_config");

    // example:
    updateScreen();
});

// listener for windows events.  VPinFECore uses this to send events to all windows.
async function receiveEvent(message) {
    vpin.call("console_out", message); // this is just example debug. you can send text to the CLI console that launched VPinFE

    // another window changed the table index.  Typcially the "table" window changes this when user selects a table.  So only BG/DMD window gets this event.
    if (message.type == "TableIndexUpdate") {
        this.currentTableIndex = message.index;
         updateScreen() 
    }
    // the table is launching. 
    else if (message.type == "TableLaunching") {
        //do something, like fade out
    }
    // the table was exited and we are back to theme
    else if (message.type == "TableLaunchComplete") {
        //do something, like fade in
    }
    // the collection was changed.  All windows get (table,bg,dmd) this event.  The table window changes this when user selects a new collection in the main menu. we need a new table list.
    else if (message.type == "TableDataChange") {
        // if collection is "All" then reset to all tables, otherwise set to the selected collection.
        if (message.collection == "All") {
            vpin.getTableData(reset = true);
        } else {
            vpin.call("console_out", "collection change.");
            await vpin.call("set_tables_by_collection", message.collection);
            await vpin.getTableData();
        }
        this.currentTableIndex = message.index;
        // NOW do something with the new table data. like update the images.
         updateScreen() 

    }
}

// create an input handler function. ***** Only for the "table" window *****
/*  joyleft 
    joyright 
    joyup
    joydown
    joyselect
    joymenu
    joycollectionmenu
*/
async function handleInput(input) {
    switch (input) {
        case "joyleft":
            currentTableIndex = wrapIndex(currentTableIndex - 1, vpin.tableData.length);
            updateScreen();
            
            // tell other windows the table index changed
            vpin.sendMessageToAllWindows({
                type: 'TableIndexUpdate',
                index: this.currentTableIndex
            });
            break;
        case "joyright":
            currentTableIndex = wrapIndex(currentTableIndex + 1, vpin.tableData.length);
            updateScreen();

            // tell other windows the table index changed
            vpin.sendMessageToAllWindows({
                type: 'TableIndexUpdate',
                index: this.currentTableIndex
            });
            break;
        case "joyselect":
            vpin.sendMessageToAllWindows({ type: "TableLaunching" })
            // do something like fade out the table window!  
            await vpin.launchTable(currentTableIndex); // this will notifiy all windows other windows.  You don't need to do it here.
            break;
        case "joyback":
            // do something on joyback if you want
            break;
    }
}

// example. for updating the screen
function updateScreen() {
    const container = document.getElementById('rootContainer');

    // clear out old content
    container.innerHTML = '';

    container.innerHTML += 'Window name: ' + windowName + '<br>';
    container.innerHTML += 'Current table index: ' + currentTableIndex + '<br>';
    container.innerHTML += 'Total tables: ' + vpin.getTableCount() + '<br><br>';

    // table metadata
    container.innerHTML +=
        'table meta data (json): <pre>' +
        JSON.stringify(vpin.getTableMeta(currentTableIndex), null, 2) +
        '</pre><br><br>';

    // get table images
    // table, cab, bg, dmd, wheel
    container.innerHTML += 'table img url: ' + vpin.getImageURL(currentTableIndex, "table") + '<br>';
    container.innerHTML += 'bg img url: ' + vpin.getImageURL(currentTableIndex, "bg") + '<br>';
    container.innerHTML += 'dmd img url: ' + vpin.getImageURL(currentTableIndex, "dmd") + '<br>';
    container.innerHTML += 'cab img url: ' + vpin.getImageURL(currentTableIndex, "cab") + '<br>';
    container.innerHTML += 'wheel img url: ' + vpin.getImageURL(currentTableIndex, "wheel") + '<br>';
}

//
// MISC suuport functions
//

// circular table index
function wrapIndex(index, length) {
    return (index + length) % length;
}
```

Again, Refer to the [web/theme/template](https://github.com/superhac/vpinfe/tree/master/web/theme/default) for a full example with the bare bones. 


# Setting the theme

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

- Returns a web server URL for a table's image.

- type can be "table", "bg", "dmd", "wheel", "cab".

- Falls back to "../../images/file_missing.png" if missing.

#### getVideoURL(index, type)

- Returns a web server URL for a table's video.

- type can be "table", "bg", or "dmd".

- Falls back to "../../images/file_missing.png" if no video exists.

- See [Video Support](#video-support) for usage details.

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

## Video Support

Themes can display looping videos for table, backglass, and DMD screens in addition to (or instead of) static images.

### Video Files

Videos are stored in the same `medias/` folder as images, using the `.mp4` extension:

| File | Description |
|------|-------------|
| `table.mp4` (or `fss.mp4`) | Table playfield video |
| `bg.mp4` | Backglass video |
| `dmd.mp4` | DMD video |

The same lookup order applies as images: `medias/` subfolder first, then the table root folder.

### Using Videos in a Theme

Use `vpin.getVideoURL(index, type)` to get the video URL, where type is `"table"`, `"bg"`, or `"dmd"`. The method returns `"../../images/file_missing.png"` if no video file exists for that table, so you should check for this before creating a `<video>` element.

Example with image fallback:
```javascript
const videoUrl = vpin.getVideoURL(currentTableIndex, 'table');
const imageUrl = vpin.getImageURL(currentTableIndex, 'table');

if (videoUrl && !videoUrl.includes('file_missing')) {
    const preview = document.createElement('video');
    preview.className = 'preview';
    preview.poster = imageUrl;  // stable dimensions while video loads
    preview.src = videoUrl;
    preview.autoplay = true;
    preview.loop = true;
    preview.muted = true;
    preview.playsInline = true;
    // Fall back to image if video fails to load
    preview.onerror = () => {
        const fallback = document.createElement('img');
        fallback.className = 'preview';
        fallback.src = imageUrl;
        preview.replaceWith(fallback);
    };
    container.appendChild(preview);
} else {
    const preview = document.createElement('img');
    preview.className = 'preview';
    preview.src = imageUrl;
    container.appendChild(preview);
}
```

Key points:
- Set `muted = true` — browsers require this for autoplay to work.
- Set `poster = imageUrl` — this gives the video element proper dimensions before its metadata loads, preventing layout shifts.
- The `onerror` handler provides a graceful fallback to the static image if the video can't be played.
- The `slider-video` theme is a full working example of video integration.

