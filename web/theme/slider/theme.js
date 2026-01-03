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
    else if (message.type == "TableDataChange") {
        currentTableIndex = message.index;
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
    joyfav
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

    // --- Left side: Rotated playfield image ---
    const preview = document.createElement('img');
    preview.className = 'preview';
    preview.src = vpin.getImageURL(tableIndex, 'table');
    card.appendChild(preview);

    // --- Right side: Text container ---
    const textContainer = document.createElement('div');
    textContainer.className = 'text-container';
    card.appendChild(textContainer);

    // Title
    const title = document.createElement('h2');
    title.textContent = meta['meta']['VPSdb']['name'] || 'Unknown Table';
    title.style.lineHeight = '1';
    textContainer.appendChild(title);

    // Metadata container
    const metaDiv = document.createElement('div');
    metaDiv.className = 'table-meta';
    
    // Each line as a block-level div to ensure vertical stacking
    metaDiv.innerHTML = `
        <div style="font-size: 2.2vh; color: rgba(94, 113, 114, 1);">${meta['meta']['VPXFile']['author'] || "Unknown"}</div>
        <div style="font-size: 1.8vh; color: rgba(126, 182, 182, 1)">${meta['meta']['VPSdb']['year'] + " / " +
             meta['meta']['VPSdb']['manufacturer'] + " / " + meta['meta']['VPSdb']['type']}</div>
        
    `;

    textContainer.appendChild(metaDiv);

    
    // ---- Table Features Section ----
    const tablefeatDiv = document.createElement("div");
    tablefeatDiv.className = "tablefeat";

    const featContainer = document.createElement("div");
    featContainer.className = "tablefeat-container";

    // You can have a single section for now; more later if you want to group features.
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
    const data = meta["meta"];
    const features = [
        ["nFozzy", data["VPXFile"]["detectnfozzy"]],
        ["Fleep", data["VPXFile"]["detectfleep"]],
        ["SSF", data["VPXFile"]["detectSSF"]],
        ["FastFlips", data["VPXFile"]["detectfastflips"]],
        ["LUT", data["VPXFile"]["detectlut"]],
        ["ScoreBit", data["VPXFile"]["detectscorebit"]],
        ["FlexDMD", data["VPXFile"]["detectflex"]],
        ["AltSound", vpin.tableData[currentTableIndex]["altSoundExists"]],
        ["AltColor", vpin.tableData[currentTableIndex]["altColorExists"]],
        ["PuP-Pack", vpin.tableData[currentTableIndex]["pupPackExists"]],
    ];

    // Create feature lights
    features.forEach(([label, condition]) => {
        const light = document.createElement("div");
        light.classList.add("tablefeat-light");
        const isOn = condition === "true" || condition === true;
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

