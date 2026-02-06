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

    // Let VPinFECore handle the data refresh logic
    await vpin.handleEvent(message);

    // Handle UI updates based on event type
    if (message.type == "TableIndexUpdate") {
        currentTableIndex = message.index;
        updateScreen();
    }
    else if (message.type == "TableLaunching") {
        //do something, like fade out
    }
    else if (message.type == "TableLaunchComplete") {
        //do something, like fade in
    }
    else if (message.type == "RemoteLaunching") {
        // Remote launch from manager UI
        showRemoteLaunchOverlay(message.table_name);
    }
    else if (message.type == "RemoteLaunchComplete") {
        // Remote launch completed
        hideRemoteLaunchOverlay();
    }
    else if (message.type == "TableDataChange") {
        currentTableIndex = message.index;
        updateScreen();
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

    // Check for empty table data
    if (!vpin.tableData || vpin.tableData.length === 0) {
        container.innerHTML = '<div style="color: white; font-size: 2em; text-align: center; margin-top: 20%;">No tables found</div>';
        return;
    }

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

// Remote launch overlay functions
function showRemoteLaunchOverlay(tableName) {
    const overlay = document.getElementById('remote-launch-overlay');
    const nameEl = document.getElementById('remote-launch-table-name');
    if (overlay && nameEl) {
        nameEl.textContent = tableName || 'Unknown Table';
        overlay.style.display = 'flex';
    }
}

function hideRemoteLaunchOverlay() {
    const overlay = document.getElementById('remote-launch-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}
