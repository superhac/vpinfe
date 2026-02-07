/*
Bare minimum example of how a theme can be implemented.
*/

// Globals
windowName = ""
currentTableIndex = 0;
lastTableIndex = 0;
let currentBgDiv = null;    // keep track of the current background
let bgFadeTimeout = null;   // pending timeout for removing old bg
const bgCache = {};

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
        fadeOutScreen();
    }
    else if (message.type == "RemoteLaunchComplete") {
        // Remote launch completed
        hideRemoteLaunchOverlay();
        fadeInScreen();
    }
    else if (message.type == "TableDataChange") {
        // Log table count for debugging
        vpin.call("console_out", `TableDataChange: vpin.tableData.length = ${vpin.tableData ? vpin.tableData.length : 'null'}`);

        // Reset index to 0 or clamp to valid range
        if (vpin.tableData && vpin.tableData.length > 0) {
            currentTableIndex = Math.min(message.index, vpin.tableData.length - 1);
        } else {
            currentTableIndex = 0;
        }
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
            await fadeOutScreen(); // fade to black
            await vpin.launchTable(currentTableIndex); // this will notifiy all windows other windows.  You don't need to do it here.
            await fadeInScreen(); // fade back in
            break;
        case "joyback":
            // do something on joyback if you want
            break;
    }
}

function preloadBg(tableIndex) {
    const url = vpin.getImageURL(tableIndex, "bg");
    if (!bgCache[url]) {
        const img = new Image();
        img.src = url;
        bgCache[url] = img;
    }
}

async function updateScreen() {
    const container = document.getElementById('rootContainer');

    // If no tables, show "No tables found" message
    if (!vpin.tableData || vpin.tableData.length === 0) {
        vpin.call("console_out", "updateScreen: No tables found, clearing display");
        container.innerHTML = '';
        currentBgDiv = null;

        // Create message element
        const messageDiv = document.createElement('div');
        Object.assign(messageDiv.style, {
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            color: '#fff',
            fontSize: '4vh',
            fontWeight: 'bold',
            textAlign: 'center',
            padding: '2vh',
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            borderRadius: '1vh',
            border: '2px solid #555'
        });
        messageDiv.textContent = 'No tables found';
        container.appendChild(messageDiv);
        return;
    }
    vpin.call("console_out", `updateScreen: Rendering table ${currentTableIndex} of ${vpin.tableData.length}`);
    const bgUrl = vpin.getImageURL(currentTableIndex, "bg");

    // Cancel pending fade removal
    if (bgFadeTimeout) {
        clearTimeout(bgFadeTimeout);
        bgFadeTimeout = null;
    }

    // Create or reuse background div
    if (!currentBgDiv) {
        currentBgDiv = document.createElement('div');
        Object.assign(currentBgDiv.style, {
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            backgroundSize: '100% 100%',
            backgroundPosition: 'center',
            backgroundRepeat: 'no-repeat',
            opacity: 1,
            transition: 'opacity 0.5s ease-in-out',
            zIndex: 0,
            backgroundColor: 'black' // fallback while loading
        });
        container.appendChild(currentBgDiv);
    }

    // Use cached image if available
    if (bgCache[bgUrl] && bgCache[bgUrl].complete) {
        currentBgDiv.style.backgroundImage = `url("${bgUrl}")`;
        currentBgDiv.style.opacity = 1;

        // Remove old siblings
        bgFadeTimeout = setTimeout(() => {
            Array.from(container.children)
                .filter(child => child !== currentBgDiv && child.id !== 'cardWrapper')
                .forEach(el => el.remove());
        }, 600);
    } else {
        // Preload current image
        const img = new Image();
        img.src = bgUrl;
        img.onload = () => {
            currentBgDiv.style.backgroundImage = `url("${bgUrl}")`;
            currentBgDiv.style.opacity = 1;

            bgFadeTimeout = setTimeout(() => {
                Array.from(container.children)
                    .filter(child => child !== currentBgDiv && child.id !== 'cardWrapper')
                    .forEach(el => el.remove());
            }, 600);
        };
        bgCache[bgUrl] = img;
    }

    // Preload next/previous table backgrounds
    const nextIndex = wrapIndex(currentTableIndex + 1, vpin.tableData.length);
    const prevIndex = wrapIndex(currentTableIndex - 1, vpin.tableData.length);
    preloadBg(nextIndex);
    preloadBg(prevIndex);

    // --- Card wrapper logic ---
    let cardWrapper = document.getElementById('cardWrapper');
    if (!cardWrapper) {
        cardWrapper = document.createElement('div');
        cardWrapper.id = 'cardWrapper';
        Object.assign(cardWrapper.style, {
            position: 'relative',
            zIndex: 1,
            width: '100%',
            height: '100%',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center'
        });
        container.appendChild(cardWrapper);

        const card = document.createElement('div');
        card.className = 'table-card active';
        cardWrapper.appendChild(card);
        cardWrapper.card = card;
    }

    const card = cardWrapper.card;

    // Reset card off-screen before slide in
    cardWrapper.style.transition = 'none';
    cardWrapper.style.transform = 'translateY(100%)';
    cardWrapper.style.opacity = 0;
    cardWrapper.offsetHeight; // force reflow

    // Update card content
    const tableMeta = vpin.getTableMeta(currentTableIndex);
    updateCardContent(card, tableMeta, currentTableIndex);

    // Slide card in
    requestAnimationFrame(() => {
        cardWrapper.style.transition = 'transform 0.5s ease, opacity 0.5s ease';
        cardWrapper.style.transform = 'translateY(0)';
        cardWrapper.style.opacity = 1;
    });
}

function updateCardContent(card, meta, tableIndex) {
    // Clear card
    card.innerHTML = '';

    const tableData = meta.meta;
    const info = tableData.Info || {};
    const vpx = tableData.VPXFile || {};

    // --- Left side: Rotated playfield video (falls back to image) ---
    const tableObj = vpin.tableData[tableIndex];
    const rawVideoPath = tableObj ? tableObj.TableVideoPath : null;
    const videoUrl = vpin.getVideoURL(tableIndex, 'table');
    const imageUrl = vpin.getImageURL(tableIndex, 'table');

    vpin.call("console_out", `[slider-video] rawVideoPath=${rawVideoPath}, videoUrl=${videoUrl}, imageUrl=${imageUrl}`);

    if (videoUrl && !videoUrl.includes('file_missing')) {
        vpin.call("console_out", `[slider-video] Creating VIDEO element with src=${videoUrl}`);
        const preview = document.createElement('video');
        preview.className = 'preview';
        preview.poster = imageUrl;  // gives stable dimensions while video loads
        preview.src = videoUrl;
        preview.autoplay = true;
        preview.loop = true;
        preview.muted = true;
        preview.playsInline = true;
        // Fall back to image if video fails to load
        preview.onerror = (e) => {
            vpin.call("console_out", `[slider-video] Video onerror fired: ${e.type}`);
            const fallback = document.createElement('img');
            fallback.className = 'preview';
            fallback.src = imageUrl;
            preview.replaceWith(fallback);
        };
        card.appendChild(preview);
    } else {
        vpin.call("console_out", `[slider-video] No video, falling back to IMAGE`);
        const preview = document.createElement('img');
        preview.className = 'preview';
        preview.src = imageUrl;
        card.appendChild(preview);
    }

    // --- Right side: Text container ---
    const textContainer = document.createElement('div');
    textContainer.className = 'text-container';
    card.appendChild(textContainer);

    // Title
    const title = document.createElement('h2');
    title.textContent = info.Title || vpx.filename || 'Unknown Table';
    title.style.lineHeight = '1';
    textContainer.appendChild(title);

    // Metadata container
    const metaDiv = document.createElement('div');
    metaDiv.className = 'table-meta';

    // Authors (Info.Authors is an array)
    let authors = "Unknown";
    if (Array.isArray(info.Authors) && info.Authors.length > 0) {
        authors = info.Authors.join(", ");
    }

    // Type, Manufacturer, Year
    const typeMap = { EM: "Electro Mechanical", SS: "Solid State", PM: "Pure Mechanical" };
    const tableType = typeMap[info.Type] || vpx.type || "Unknown";
    const manufacturer = info.Manufacturer || vpx.manufacturer || "Unknown";
    const year = info.Year || vpx.year || "";

    metaDiv.innerHTML = `
        <div style="font-size: 2.2vh; color: rgba(94, 113, 114, 1);">${authors}</div>
        <div style="font-size: 1.8vh; color: rgba(126, 182, 182, 1)">${year} / ${manufacturer} / ${tableType}</div>
    `;
    textContainer.appendChild(metaDiv);

    // ---- Table Features Section ----
    const tablefeatDiv = document.createElement("div");
    tablefeatDiv.className = "tablefeat";

    const featContainer = document.createElement("div");
    featContainer.className = "tablefeat-container";

    const section = document.createElement("div");
    section.className = "tablefeat-section";

    const titleFeat = document.createElement("div");
    titleFeat.className = "tablefeat-section-title";
    titleFeat.textContent = "Detected Features:";
    section.appendChild(titleFeat);

    const featGrid = document.createElement("div");
    featGrid.className = "tablefeat-grid";
    section.appendChild(featGrid);
    featContainer.appendChild(section);
    tablefeatDiv.appendChild(featContainer);
    textContainer.appendChild(tablefeatDiv);

    // Build features list dynamically
    const features = [
        ["detectnfozzy", vpx.detectnfozzy, "Nfozzy"],
        ["detectfleep", vpx.detectfleep, "Fleep"],
        ["detectssf", vpx.detectssf, "SSF"],
        ["detectfastflips", vpx.detectfastflips, "FastFlips"],
        ["detectlut", vpx.detectlut, "LUT"],
        ["detectscorebit", vpx.detectscorebit, "ScoreBit"],
        ["detectflex", vpx.detectflex, "FlexDMD"],
        ["altsound", vpx.altSoundExists, "AltSound"],
        ["altcolor", vpx.altColorExists, "AltColor"],
        ["pupack", vpx.pupPackExists, "PuP-Pack"],
    ];



    // Create feature lights
    // Create feature lights
    features.forEach(([id, condition, label]) => {
        const light = document.createElement("div");
        light.classList.add("tablefeat-light");
        light.id = id; // IMPORTANT: real DOM identity

        // Normalize to boolean (handles true, "true", 1)
        const isOn =
            condition === true ||
            condition === "true" ||
            condition === 1;

        light.classList.add(isOn ? "tablefeat-green" : "tablefeat-red");
        light.textContent = label;

        featGrid.appendChild(light);
    });

}

//
// MISC suuport functions
//

// circular table index
function wrapIndex(index, length) {
    return (index + length) % length;
}

function fadeOutScreen() {
  document.getElementById("fadeOverlay").classList.add("show");
}
function fadeInScreen() {
  document.getElementById("fadeOverlay").classList.remove("show");
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

