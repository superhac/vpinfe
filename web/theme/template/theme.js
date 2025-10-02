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
    joyfav
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
