windowName = ""
currentTableIndex = 0;

const vpin = new VPinFECore();
vpin.init();
window.vpin = vpin

vpin.ready.then(async () => {
    console.log("VPinFECore is fully initialized");
    // blocks
    await vpin.call("get_my_window_name")
    .then(result => {
        windowName = result;                      // <- stored here

    });

    setImage();
    vpin.registerInputHandler(handleInput);
});

// circular tables index
function wrapIndex(index, length) {
    return (index + length) % length;
}

async function fadeOut() {
  const container = document.getElementById('fadeContainer');

  return new Promise(resolve => {
    container.addEventListener('transitionend', e => {
      if (e.propertyName === 'opacity') resolve();
    }, { once: true });

    container.style.opacity = 0;
  });
}

function fadeInScreen() {
    const container = document.getElementById('fadeContainer');
    container.style.opacity = 1;
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

// Hook for Python events
async function receiveEvent(message) {
    vpin.call("console_out", message);  // no 'this' here

    // Let VPinFECore handle the data refresh logic
    await vpin.handleEvent(message);

    // Handle UI updates based on event type
    if (message.type == "TableIndexUpdate") {
        currentTableIndex = message.index;
        setImage();
    }
    else if (message.type == "TableLaunching") {
        await fadeOut();
    }
    else if (message.type == "TableLaunchComplete") {
        fadeInScreen();
    }
    else if (message.type == "RemoteLaunching") {
        // Remote launch from manager UI
        showRemoteLaunchOverlay(message.table_name);
        await fadeOut();
    }
    else if (message.type == "RemoteLaunchComplete") {
        // Remote launch completed
        hideRemoteLaunchOverlay();
        fadeInScreen();
    }
    else if (message.type == "TableDataChange") {
        currentTableIndex = message.index;
        setImage();
    }
}

window.receiveEvent = receiveEvent;  // get events from other windows.

// create an input hanfler function. Only for the "table" window
async function handleInput(input) {
        switch (input) {
        case "joyleft":
            currentTableIndex = wrapIndex(currentTableIndex - 1, vpin.tableData.length);
            setImage();
            vpin.sendMessageToAllWindows({
            type: 'TableIndexUpdate',
            index: this.currentTableIndex
            });
            break;
        case "joyright":
            currentTableIndex = wrapIndex(currentTableIndex + 1, vpin.tableData.length);
            setImage();
            vpin.sendMessageToAllWindows({
            type: 'TableIndexUpdate',
            index: this.currentTableIndex
            });
            break;
        case "joyselect":
            vpin.sendMessageToAllWindows({type: "TableLaunching"})
            await fadeOut();
            await vpin.launchTable(currentTableIndex);
            //await fadeOutAndLaunch();
            vpin.call("console_out", "FADEOUT done");
            //fadeInScreen()
            //vpin.launchTable(this.currentTableIndex);
            break;
        case "joymenu":
            message = "You chose an orange.";
            break;
        case "joyback":
            message = "You chose an orange.";
            break;
        }
}

function setImage() {
    // Check for empty table data
    if (!vpin.tableData || vpin.tableData.length === 0) {
        const img = document.getElementById('fsImage');
        if (img) img.src = '';
        return;
    }

    image = vpin.getImageURL(currentTableIndex, windowName)
    const img = document.getElementById('fsImage');
    img.src = image;  // Replace with your new image path
}
