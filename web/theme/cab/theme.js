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

window.addEventListener('load', sizeRotateboxes);
window.addEventListener('resize', sizeRotateboxes);

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
        if (message.collection == "All") {
            vpin.getTableData(reset = true);
        } else {
            await vpin.call("set_tables_by_collection", message.collection);
            await vpin.getTableData();
        }
        vpin.call("console_out", "got new table data, length: " + vpin.tableData.length);
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
    if (windowName === "table") {
        setCarouselWheels();
        setTableImage();
        setMetadata();
        setCabImage();
    }
    else setSingleFSImage();
}

function setMetadata() {
    document.getElementById('title').innerHTML = vpin.tableData[currentTableIndex]["meta"]["VPSdb"]["name"];
    document.getElementById('authors').innerHTML = vpin.tableData[currentTableIndex]["meta"]["VPXFile"]["author"];
    document.getElementById('year').innerHTML = vpin.tableData[currentTableIndex]["meta"]["VPSdb"]["year"];

    switch (vpin.tableData[currentTableIndex]["meta"]["VPSdb"]["type"]) {
        case "EM":
            document.getElementById('table-type').innerHTML = "Electro Mechanical";
            break;
        case "SS":
            document.getElementById('table-type').innerHTML = "Solid State";
            break;
        case "PM":
            document.getElementById('table-type').innerHTML = "Pure Mechanical";
            break;
        default:
            document.getElementById('table-type').innerHTML = "Unknown";
    }
    const manufimg = document.getElementById('manufacturer-img');
    switch (vpin.tableData[currentTableIndex]["meta"]["VPSdb"]["manufacturer"]) {
        case "Sega":
            manufimg.src = "assets/manufacturer/Sega.png";
            break;
        case "Gottlieb":
            manufimg.src = "assets/manufacturer/Gottlieb.png";
            break;
        case "Bally":
            manufimg.src = "assets/manufacturer/Bally.png";
            break;
        case "Stern":
            manufimg.src = "assets/manufacturer/Stern.png";
            break;
        case "Williams":
            manufimg.src = "assets/manufacturer/Williams.png";
            break;
        case "Data East":
            manufimg.src = "assets/manufacturer/Data East.png";
            break;
        case "Capcom":
            manufimg.src = "assets/manufacturer/Capcom.png";
            break;
        case "Chicago Coin":
            manufimg.src = "assets/manufacturer/Chicago Coin.png";
            break;
        case "Taito":
            manufimg.src = "assets/manufacturer/Taito.png";
            break;
        case "Zaccaria":
            manufimg.src = "assets/manufacturer/Zaccaria.png";
            break;
        case "LTD do Brasil":
            manufimg.src = "assets/manufacturer/Taito.png";
            break;
        case "Taito do Brasil":
            manufimg.src = "assets/manufacturer/Taito.png";
            break;
        case "Playmatic":
            manufimg.src = "assets/manufacturer/Playmatic.png";
            break;
        case "Maresa":
            manufimg.src = "assets/manufacturer/Maresa.png";
            break;
        default:
            manufimg.src = textToImageURL(vpin.tableData[currentTableIndex]["meta"]["VPSdb"]["manufacturer"]);
    }

    // Remove brackets and single quotes
    document.getElementById('theme').innerHTML = vpin.tableData[currentTableIndex]["meta"]["VPSdb"]["theme"].replace(/[\[\]']/g, '');

    vpin.tableData[currentTableIndex]["meta"]["VPXFile"]["detectnfozzy"] === "true" ? tablefeatTurnOn("detectnfozzy") : tablefeatTurnOff("detectnfozzy");
    vpin.tableData[currentTableIndex]["meta"]["VPXFile"]["detectfleep"] === "true" ? tablefeatTurnOn("detectfleep") : tablefeatTurnOff("detectfleep");
    vpin.tableData[currentTableIndex]["meta"]["VPXFile"]["detectSSF"] === "true" ? tablefeatTurnOn("detectssf") : tablefeatTurnOff("detectssf");
    vpin.tableData[currentTableIndex]["meta"]["VPXFile"]["detectfastflips"] === "true" ? tablefeatTurnOn("detectfastflips") : tablefeatTurnOff("detectfastflips");
    vpin.tableData[currentTableIndex]["meta"]["VPXFile"]["detectlut"] === "true" ? tablefeatTurnOn("detectlut") : tablefeatTurnOff("detectlut");
    vpin.tableData[currentTableIndex]["meta"]["VPXFile"]["detectscorebit"] === "true" ? tablefeatTurnOn("detectscorebit") : tablefeatTurnOff("detectscorebit");
    vpin.tableData[currentTableIndex]["meta"]["VPXFile"]["detectflex"] === "true" ? tablefeatTurnOn("detectflex") : tablefeatTurnOff("detectflex");

    vpin.tableData[currentTableIndex]["altSoundExists"] === true ? tablefeatTurnOn("altsound") : tablefeatTurnOff("altsound");
    vpin.tableData[currentTableIndex]["altColorExists"] === true ? tablefeatTurnOn("altcolor") : tablefeatTurnOff("altcolor");
    vpin.tableData[currentTableIndex]["pupPackExists"] === true ? tablefeatTurnOn("pupack") : tablefeatTurnOff("pupack");

}

function crossfade(container, newUrl, altText = "") {
    // Remove images that failed to load
    [...container.querySelectorAll("img.fading-in")].forEach(img => img.remove());

    const oldImg = container.querySelector("img:last-of-type");

    const newImg = new Image();
    newImg.src = newUrl;
    newImg.alt = altText;
    newImg.classList.add("fading-in");
    newImg.style.opacity = 0;
    newImg.style.transition = "opacity 0.4s ease-in-out";
    newImg.style.width = "100%";
    newImg.style.height = "100%";
    newImg.style.objectFit = "contain";
    newImg.style.position = "absolute";
    newImg.style.top = 0;
    newImg.style.left = 0;

    container.style.position = "relative";
    container.appendChild(newImg);

    newImg.onload = () => {
        requestAnimationFrame(() => {
            newImg.style.opacity = 1;
            if (oldImg) {
                oldImg.style.opacity = 0;
                oldImg.addEventListener(
                    "transitionend",
                    () => {
                        if (oldImg.parentElement) oldImg.remove();
                        newImg.style.position = "static";
                        newImg.classList.remove("fading-in");
                    },
                    { once: true }
                );
            } else {
                newImg.style.position = "static";
                newImg.classList.remove("fading-in");
            }
        });
    };

    newImg.onerror = () => {
        console.warn("Failed to load image:", newUrl);
        if (newImg.parentElement) newImg.remove();
        if (oldImg) oldImg.style.opacity = 1;
    };
}

function setTableImage() {
    const bgUrl = vpin.getImageURL(currentTableIndex, "table");
    console.log("setTableImage →", currentTableIndex, bgUrl);
    const container = document.getElementById('table');
    crossfade(container, bgUrl, "Table Image");
}

function setCabImage() {
    const bgUrl = vpin.getImageURL(currentTableIndex, "cab");
    console.log("setCabImage →", currentTableIndex, bgUrl);
    const container = document.getElementById('cab');
    crossfade(container, bgUrl, "Cab Image");
}

function setCarouselWheels() {
    const imagesContainer = document.getElementById('carouselImages');
    const total = vpin.tableData.length;
    if (total === 0) return;

    const visibleCount = 7;
    const sideImages = 3;

    // if no children yet, create them once
    if (imagesContainer.children.length === 0) {
        for (let i = -sideImages; i <= sideImages; i++) {
            const img = document.createElement('img');
            img.loading = 'lazy';
            imagesContainer.appendChild(img);
        }
    }

    // update existing children
    [...imagesContainer.children].forEach((img, i) => {
        const idx = wrapIndex(currentTableIndex + (i - sideImages), total);
        img.src = vpin.getImageURL(idx, "wheel");
        img.alt = `wheel-${idx}`;
        img.classList.toggle("selected", i === sideImages); // center slot
    });
}


// Swap dimensions for every .rotatebox based on its parent’s current size
function sizeRotateboxes() {
    document.querySelectorAll('.rotatebox').forEach((box) => {
        const parent = box.parentElement;
        const cw = parent.clientWidth;
        const ch = parent.clientHeight;
        parent.style.setProperty('--cw', cw + 'px');
        parent.style.setProperty('--ch', ch + 'px');
        box.classList.add("ready"); // show only after sized
    });
}

function textToImageURL(text, options = {}) {
    const { font = "30px Arial", color = "black", background = "white", padding = 10 } = options;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    ctx.font = font;
    const textWidth = ctx.measureText(text).width;
    const textHeight = parseInt(ctx.font, 10);
    canvas.width = textWidth + padding * 2;
    canvas.height = textHeight + padding * 2;
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = color;
    ctx.font = font;
    ctx.fillText(text, padding, textHeight + padding / 2);
    return canvas.toDataURL("image/png");
}

function tablefeatTurnOn(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.remove("tablefeat-red");
        el.classList.add("tablefeat-green");
    }
}

// Turn a light OFF
function tablefeatTurnOff(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.remove("tablefeat-green");
        el.classList.add("tablefeat-red");
    }
}

function setSingleFSImage() {
    vpin.call("console_out", "ran setsinglefs on screen: " + windowName);
    image = vpin.getImageURL(currentTableIndex, windowName)
    const img = document.getElementById('fsImage');
    img.src = image;  // Replace with your new image path
}



