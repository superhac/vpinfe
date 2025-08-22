windowName = ""
currentTableIndex = 0;
lastTableIndex = 0;

const vpin = new VPinFECore();
vpin.init();
window.vpin = vpin
config = undefined

vpin.ready.then(async () => {
    console.log("VPinFECore is fully initialized");
    // blocks
    await vpin.call("get_my_window_name")
        .then(result => {
            windowName = result;
        });
    config = await vpin.call("get_theme_config");

    updateImages();
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
async function receiveEvent(message) {
    vpin.call("console_out", message);
    if (message.type == "TableIndexUpdate") {
        this.currentTableIndex = message.index;
        updateImages();
    }
    else if (message.type == "TableLaunching") {
        fadeOut();
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
            updateImages();
            vpin.sendMessageToAllWindows({
                type: 'TableIndexUpdate',
                index: this.currentTableIndex
            });
            vpin.call("console_out", vpin.tableData[currentTableIndex]["tableDirName"])

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
            vpin.sendMessageToAllWindows({ type: "TableLaunching" })
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

function updateImages() {
    setCarouselWheels();
    setMainGfxImage();
    setTableImage();
}

function setTableImage() {
    const bgUrl = vpin.getImageURL(currentTableIndex, "cab");
    const container = document.getElementById('cab');
    const oldImg = container.querySelector('img');

    if (oldImg) {
        oldImg.style.opacity = 0;

        setTimeout(() => {
            container.innerHTML = '';

            const newImg = new Image();
            newImg.src = bgUrl;
            newImg.alt = "Table Image";
            newImg.style.opacity = 0;

            newImg.onload = () => {
                requestAnimationFrame(() => {
                    newImg.style.opacity = 1;
                });
            };

            container.appendChild(newImg);
        }, 300);
    } else {
        const img = new Image();
        img.src = bgUrl;
        img.alt = "Table Image";
        img.style.opacity = 0;

        img.onload = () => {
            requestAnimationFrame(() => {
                img.style.opacity = 1;
            });
        };

        container.appendChild(img);
    }
}

function setMainGfxImage() {
    let gfx = 'bg';
    if (config) gfx = config.maingfx;

    const container = document.getElementById('bg');
    const oldImg = container.querySelector('img');

    if (oldImg) {
        oldImg.style.opacity = 0;

        setTimeout(() => {
            container.innerHTML = '';

            const newImg = new Image();
            newImg.src = vpin.getImageURL(currentTableIndex, gfx);
            newImg.alt = "bgImage";
            newImg.style.opacity = 0;

            newImg.onload = () => {
                requestAnimationFrame(() => {
                    newImg.style.opacity = 1;
                });
            };

            container.appendChild(newImg);
        }, 300); // match transition duration
    } else {
        const img = new Image();
        img.src = vpin.getImageURL(currentTableIndex, gfx);
        img.alt = "bgImage";
        img.style.opacity = 0;

        img.onload = () => {
            requestAnimationFrame(() => {
                img.style.opacity = 1;
            });
        };

        container.appendChild(img);
    }
}

function setCarouselWheels() {
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


