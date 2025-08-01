windowName = ""
currentTableIndex = 0;
tableRunning = false;

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
    container.style.opacity = 0;

    //setTimeout(() => {
        //await vpin.launchTable(currentTableIndex);
   // }, 5000); // Match the CSS transition
}

function fadeInScreen() {
    const container = document.getElementById('fadeContainer');
    container.style.opacity = 1;
}

// Hook for Python events
function receiveEvent(message) {
    vpin.call("console_out", message);  // no 'this' here
    if (message.type == "TableIndexUpdate") {
        this.currentTableIndex = message.index;
        setImage();
    }
    else if (message.type == "TableLaunching") {
        fadeOut();
    }
    else if (message.type == "TableLaunchComplete") {
        fadeInScreen();
    }
}

window.receiveEvent = receiveEvent;  // get events from other windows.

// create an input hanfler function. Only for the "table" window
async function handleInput(input) {
    if (!tableRunning) { // need this or when that table is running this is still getting gamepad input!
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
            fadeOut();
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
}

function setImage() {
    image = vpin.getImageURL(currentTableIndex, windowName)
    const img = document.getElementById('fsImage');
    img.src = image;  // Replace with your new image path
}
