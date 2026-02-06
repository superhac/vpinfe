// =============================
// Global State & Initialization
// =============================
let windowName = "";
let currentTableIndex = 0;
let lastTableIndex = 0;
let config = undefined;

const vpin = new VPinFECore();
vpin.init();
window.vpin = vpin;

// =============================
// VPinFECore Initialization
// =============================
vpin.ready.then(async () => {
    console.log("VPinFECore is fully initialized");

    windowName = await vpin.call("get_my_window_name");
    config = await vpin.call("get_theme_config");

    updateImages();
    vpin.registerInputHandler(handleInput);
});

// =============================
// Events & Listeners
// =============================
window.addEventListener("load", sizeRotateboxes);
window.addEventListener("resize", sizeRotateboxes);

window.receiveEvent = receiveEvent; // Hook for Python/other window events

// =============================
// Utility Functions
// =============================

// Circular table index
function wrapIndex(index, length) {
    return (index + length) % length;
}

function fadeOut() {
    document.getElementById("root").style.opacity = 0;
}

function fadeInScreen() {
    document.getElementById("root").style.opacity = 1;
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

// =============================
// Event Handling
// =============================
async function receiveEvent(message) {
    vpin.call("console_out", message);

    // Let VPinFECore handle the data refresh logic
    await vpin.handleEvent(message);

    // Handle UI updates based on event type
    switch (message.type) {
        case "TableIndexUpdate":
            currentTableIndex = message.index;
            updateImages();
            break;

        case "TableLaunching":
            fadeOut();
            break;

        case "TableLaunchComplete":
            fadeInScreen();
            break;

        case "RemoteLaunching":
            // Remote launch from manager UI
            showRemoteLaunchOverlay(message.table_name);
            fadeOut();
            break;

        case "RemoteLaunchComplete":
            // Remote launch completed
            hideRemoteLaunchOverlay();
            fadeInScreen();
            break;

        case "TableDataChange":
            currentTableIndex = message.index;
            updateImages();
            break;
    }
}

async function handleInput(input) {
    switch (input) {
        case "joyleft":
            currentTableIndex = wrapIndex(currentTableIndex - 1, vpin.tableData.length);
            updateImages();
            vpin.sendMessageToAllWindows({ type: "TableIndexUpdate", index: currentTableIndex });
            vpin.call("console_out", vpin.tableData[currentTableIndex]["tableDirName"]);
            break;

        case "joyright":
            currentTableIndex = wrapIndex(currentTableIndex + 1, vpin.tableData.length);
            updateImages();
            vpin.sendMessageToAllWindows({ type: "TableIndexUpdate", index: currentTableIndex });
            break;

        case "joyselect":
            vpin.sendMessageToAllWindows({ type: "TableLaunching" });
            fadeOut();
            await vpin.launchTable(currentTableIndex);
            break;

        case "joymenu":
        case "joyback":
            console.log("Menu/Back pressed (placeholder)");
            break;
    }
}

// =============================
// Image & Metadata Updates
// =============================
function updateImages() {
    // Check for empty table data
    if (!vpin.tableData || vpin.tableData.length === 0) {
        clearAllDisplays();
        return;
    }

    if (windowName === "table") {
        setCarouselWheels();
        setTableImage();
        setMetadata();
        setCabImage();
    } else {
        setSingleFSImage();
    }
}

function clearAllDisplays() {
    if (windowName === "table") {
        // Clear carousel
        const imagesContainer = document.getElementById("carouselImages");
        if (imagesContainer) imagesContainer.innerHTML = '';

        // Clear table and cab images
        const tableContainer = document.getElementById("table");
        const cabContainer = document.getElementById("cab");
        if (tableContainer) tableContainer.innerHTML = '';
        if (cabContainer) cabContainer.innerHTML = '';

        // Clear metadata
        const titleEl = document.getElementById("title");
        if (titleEl) titleEl.innerHTML = 'No tables found';
        const authorsEl = document.getElementById("authors");
        if (authorsEl) authorsEl.innerHTML = '';
        const yearEl = document.getElementById("year");
        if (yearEl) yearEl.innerHTML = '';
        const typeEl = document.getElementById("table-type");
        if (typeEl) typeEl.innerHTML = '';
        const themeEl = document.getElementById("theme");
        if (themeEl) themeEl.innerHTML = '';
        const manufImg = document.getElementById("manufacturer-img");
        if (manufImg) manufImg.src = '';
    } else {
        // Clear fullscreen image
        const fsImg = document.getElementById("fsImage");
        if (fsImg) fsImg.src = '';
    }
}

function setTableImage() {
    const url = vpin.getImageURL(currentTableIndex, "table");
    const container = document.getElementById("table");
    console.log("setTableImage →", currentTableIndex, url);
    crossfade(container, url, "Table Image");
}

function setCabImage() {
    const url = vpin.getImageURL(currentTableIndex, "cab");
    const container = document.getElementById("cab");
    console.log("setCabImage →", currentTableIndex, url);
    crossfade(container, url, "Cab Image");
}

function setSingleFSImage() {
    const url = vpin.getImageURL(currentTableIndex, windowName);
    const img = document.getElementById("fsImage");

    vpin.call("console_out", "ran setsinglefs on screen: " + windowName);
    img.src = url;
}

function setCarouselWheels() {
    const imagesContainer = document.getElementById("carouselImages");
    const total = vpin.tableData.length;
    if (total === 0) return;

    const sideImages = 3;
    if (imagesContainer.children.length === 0) {
        for (let i = -sideImages; i <= sideImages; i++) {
            const img = document.createElement("img");
            img.loading = "lazy";
            imagesContainer.appendChild(img);
        }
    }

    [...imagesContainer.children].forEach((img, i) => {
        const idx = wrapIndex(currentTableIndex + (i - sideImages), total);
        img.src = vpin.getImageURL(idx, "wheel");
        img.alt = `wheel-${idx}`;
        img.classList.toggle("selected", i === sideImages);
    });
}

function setMetadata() {
    const table = vpin.tableData[currentTableIndex];
    if (!table) return;

    const data = table.meta || {};
    const info = data.Info || {};
    const vpx = data.VPXFile || {};

    function strToBool(val) {
        if (typeof val === "boolean") return val;
        if (typeof val === "string") return val.toLowerCase() === "true";
        return false;
    }

    // Title
    document.getElementById("title").innerHTML = info.Title || vpx.filename || "Unknown";

    // Authors
    const authors = Array.isArray(info.Authors) && info.Authors.length > 0
        ? info.Authors.join(", ")
        : "Unknown";
    document.getElementById("authors").innerHTML = authors;

    // Year
    document.getElementById("year").innerHTML = info.Year || vpx.year || "";

    // Table Type
    const typeMap = { EM: "Electro Mechanical", SS: "Solid State", PM: "Pure Mechanical" };
    document.getElementById("table-type").innerHTML = typeMap[info.Type] || vpx.type || "Unknown";

    // Manufacturer
    const manufMap = {
        Sega: "Sega.png",
        Gottlieb: "Gottlieb.png",
        Bally: "Bally.png",
        Stern: "Stern.png",
        Williams: "Williams.png",
        "Data East": "Data East.png",
        Capcom: "Capcom.png",
        "Chicago Coin": "Chicago Coin.png",
        Taito: "Taito.png",
        Zaccaria: "Zaccaria.png",
        "LTD do Brasil": "Taito.png",
        "Taito do Brasil": "Taito.png",
        Playmatic: "Playmatic.png",
        Maresa: "Maresa.png",
    };

    const manufacturer = info.Manufacturer || vpx.manufacturer || "Unknown";
    const manufimg = document.getElementById("manufacturer-img");
    manufimg.src = manufMap[manufacturer]
        ? "assets/manufacturer/" + manufMap[manufacturer]
        : textToImageURL(manufacturer);

    // Themes
    const themes = Array.isArray(info.Themes) ? info.Themes : [];
    document.getElementById("theme").innerHTML = themes.join(", ");

    // Features
    const features = [
        ["detectnfozzy", strToBool(vpx.detectnfozzy)],
        ["detectfleep", strToBool(vpx.detectfleep)],
        ["detectssf", strToBool(vpx.detectssf)],
        ["detectfastflips", strToBool(vpx.detectfastflips)],
        ["detectlut", strToBool(vpx.detectlut)],
        ["detectscorebit", strToBool(vpx.detectscorebit)],
        ["altsound", !!table.altSoundExists],
        ["altcolor", !!table.altColorExists],
        ["pupack", !!table.pupPackExists],
    ];

    features.forEach(([id, isOn]) => {
        isOn ? tablefeatTurnOn(id) : tablefeatTurnOff(id);
    });
}


    function strToBool(val) {
        if (typeof val === "boolean") return val;
        if (typeof val === "string") return val.toLowerCase() === "true";
        return false;
}

// =============================
// Image Helpers
// =============================
function crossfade(container, newUrl, altText = "") {
    // Remove failed images
    [...container.querySelectorAll("img.fading-in")].forEach(img => img.remove());

    const oldImg = container.querySelector("img:last-of-type");
    const newImg = new Image();

    Object.assign(newImg, { src: newUrl, alt: altText });
    Object.assign(newImg.style, {
        opacity: 0,
        transition: "opacity 0.4s ease-in-out",
        width: "100%",
        height: "100%",
        objectFit: "contain",
        position: "absolute",
        top: 0,
        left: 0,
    });

    newImg.classList.add("fading-in");
    container.style.position = "relative";
    container.appendChild(newImg);

    newImg.onload = () => {
        requestAnimationFrame(() => {
            newImg.style.opacity = 1;
            if (oldImg) {
                oldImg.style.opacity = 0;
                oldImg.addEventListener("transitionend", () => {
                    oldImg.remove();
                    newImg.style.position = "static";
                    newImg.classList.remove("fading-in");
                }, { once: true });
            } else {
                newImg.style.position = "static";
                newImg.classList.remove("fading-in");
            }
        });
    };

    newImg.onerror = () => {
        console.warn("Failed to load image:", newUrl);
        newImg.remove();
        if (oldImg) oldImg.style.opacity = 1;
    };
}

// =============================
// Table Features
// =============================
function tablefeatTurnOn(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.remove("tablefeat-red");
        el.classList.add("tablefeat-green");
    }
}

function tablefeatTurnOff(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.remove("tablefeat-green");
        el.classList.add("tablefeat-red");
    }
}

// =============================
// Layout Helpers
// =============================
function sizeRotateboxes() {
    document.querySelectorAll(".rotatebox").forEach((box) => {
        const parent = box.parentElement;
        parent.style.setProperty("--cw", parent.clientWidth + "px");
        parent.style.setProperty("--ch", parent.clientHeight + "px");
        box.classList.add("ready");
    });
}
