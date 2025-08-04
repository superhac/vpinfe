windowName = ""
currentTableIndex = 0;
lastTableIndex = 0;
tableRunning = false;

const vpin = new VPinFECore();
vpin.init();
window.vpin = vpin

vpin.ready.then(async () => {
    console.log("VPinFECore is fully initialized");
    // blocks
    await vpin.call("get_my_window_name")
    .then(result => {
        windowName = result;
    });

    updateImages();
    vpin.registerInputHandler(handleInput);
});

// circular table index
function wrapIndex(index, length) {
    return (index + length) % length;
}

async function fadeOut() {
    //const container = document.getElementById('fadeContainer');
    //container.style.opacity = 0;
}

function fadeInScreen() {
    //const container = document.getElementById('fadeContainer');
    //container.style.opacity = 1;
}

// Hook for Python events
function receiveEvent(message) {
    vpin.call("console_out", message);  // no 'this' here
    if (message.type == "TableIndexUpdate") {
        this.currentTableIndex = message.index;
        updateImages();
    }
    else if (message.type == "TableLaunching") {S
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
            updateImages();
            vpin.sendMessageToAllWindows({
            type: 'TableIndexUpdate',
            index: this.currentTableIndex
            });
            break;
        case "joyright":
            currentTableIndex = wrapIndex(currentTableIndex + 1, vpin.tableData.length);
            updateImages();
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

function updateImages() {
    setCarouselWheels();
    setTableImage();
    setBGImage();
}

function setTableImage() {
   
    const bgUrl = vpin.getImageURL(currentTableIndex, "cab");
    const container = document.getElementById('cab');
    container.innerHTML = ''; // Clear previous image

    const img = new Image();
    vpin.call("console_out", "angle out url? "+bgUrl);
    img.src = bgUrl;
    img.alt = "Table Image";
     

    container.appendChild(img);
}

function setBGImage() {
    const bgUrl = vpin.getImageURL(currentTableIndex, "bg");
    const container = document.getElementById('bg');

    container.innerHTML = ''; // Clear previous image

    // Create image
    const img = new Image();
    img.src = bgUrl;
    img.alt = "bgImage";

    // Append image to wrapper
    container.appendChild(img);

}

function  setCarouselWheels() {
    const imagesContainer = document.getElementById('carouselImages');
    imagesContainer.innerHTML = ""; // clear previous images

    const containerWidth = imagesContainer.clientWidth;
    const averageImageWidth = 7 * window.innerWidth / 100 + 30; // 6vw + 30px gap
    const total = vpin.tableData.length;

    // Calculate how many images fit, subtract 1 for the center image
    const maxVisible = Math.floor(containerWidth / averageImageWidth);
    const sideImages = Math.floor((maxVisible - 1) / 2); // images on each side

    for (let i = -sideImages; i <= sideImages; i++) {
        const idx = wrapIndex(currentTableIndex + i, total);
        const wheelUrl = vpin.getImageURL(idx, "wheel");
        const img = document.createElement('img');
        img.src = wheelUrl;
        if (i === 0) img.classList.add('selected');
        imagesContainer.appendChild(img);
    }
}


