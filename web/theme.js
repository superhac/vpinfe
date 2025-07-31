windowName = ""
currentTableIndex = 0;

const vpin = new VPinFECore();
vpin.init();

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

// Hook for Python events
function receiveEvent(message) {
    vpin.call("console_out", message);  // no 'this' here
    if (message.type == "TableIndexUpdate") {
    this.currentTableIndex = message.index;
    setImage();
    }
}

window.receiveEvent = receiveEvent;  // get events from other windows.

// create an input hanfler function. Only for the "table" window
function handleInput(input) {
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
        message = "You chose an orange.";
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
    image = vpin.getImageURL(currentTableIndex, windowName)
    const img = document.getElementById('fsImage');
    img.src = image;  // Replace with your new image path

}
