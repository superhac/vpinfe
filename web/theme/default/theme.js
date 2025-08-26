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

// Hook for Python events
async function receiveEvent(message) {
    vpin.call("console_out", message);  // no 'this' here
    if (message.type == "TableIndexUpdate") {
        this.currentTableIndex = message.index;
        setImage();
    }
    else if (message.type == "TableLaunching") {
        await fadeOut();
    }
    else if (message.type == "TableLaunchComplete") {
        fadeInScreen();
    }
     else if (message.type == "TableDataChange") {
        vpin.call("console_out", "table data change");
        await window.parent.vpin.getTableData();
        this.currentTableIndex = message.index;
        updateImages();
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
    image = vpin.getImageURL(currentTableIndex, windowName)
    const img = document.getElementById('fsImage');
    img.src = image;  // Replace with your new image path
}
