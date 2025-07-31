windowName = ""
currentTableIndex = 0;
lastTableIndex = 0;
tableRunning = false;

const vpin = new VPinFECore();
vpin.init();

vpin.ready.then(async () => {
    console.log("VPinFECore is fully initialized");
    // blocks
    await vpin.call("get_my_window_name")
    .then(result => {
        windowName = result;
    });

    setImage();
    vpin.registerInputHandler(handleInput);
});

// circular table index
function wrapIndex(index, length) {
    return (index + length) % length;
}

async function fadeOut() {
    const container = document.getElementById('fadeContainer');
    container.style.opacity = 0;
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
    const imagesContainer = document.getElementById('carouselImages'); // <-- add this
    imagesContainer.innerHTML = ""; // clear previous images

    const bgUrl = vpin.getImageURL(currentTableIndex, "bg");
    const fadeContainer = document.getElementById('fadeContainer');
    const img = new window.Image();
    img.onload = function() {
        fadeContainer.style.setProperty('--carousel-bg', `url('${bgUrl}')`);
    };
    img.src = bgUrl;

    const total = vpin.tableData.length;
    for (let i = -2; i <= 2; i++) {
        const idx = wrapIndex(currentTableIndex + i, total);
        const wheelUrl = vpin.getImageURL(idx, "wheel");
        const img = document.createElement('img');
        img.src = wheelUrl;
        if (i === 0) img.classList.add('selected');
        imagesContainer.appendChild(img);
    }
}