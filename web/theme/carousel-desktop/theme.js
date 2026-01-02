/*
Testing theme with carousel layout
*/

// Globals
windowName = ""
currentTableIndex = 0;
lastTableIndex = 0;
config = undefined;

// init the core interface to VPinFE
const vpin = new VPinFECore();
vpin.init();
window.vpin = vpin // main menu needs this to call back in.

// wait for VPinFECore to be ready
vpin.ready.then(async () => {
    console.log("VPinFECore is fully initialized");

    await vpin.call("get_my_window_name")
        .then(result => {
            windowName = result;
        });

    vpin.registerInputHandler(handleInput);
    window.receiveEvent = receiveEvent;

    config = await vpin.call("get_theme_config");

    // Initialize the display
    updateScreen();
});

// listener for windows events.  VPinFECore uses this to send events to all windows.
async function receiveEvent(message) {
    vpin.call("console_out", message); // this is just example debug. you can send text to the CLI console that launched VPinFE

    // another window changed the table index.  Typcially the "table" window changes this when user selects a table.  So only BG/DMD window gets this event.
    if (message.type == "TableIndexUpdate") {
        this.currentTableIndex = message.index;
        updateScreen();
    }
    // the table is launching.
    else if (message.type == "TableLaunching") {
        await fadeOut();
    }
    // the table was exited and we are back to theme
    else if (message.type == "TableLaunchComplete") {
        fadeIn();
    }
    // the collection was changed.  All windows get (table,bg,dmd) this event.  The table window changes this when user selects a new collection in the main menu. we need a new table list.
    else if (message.type == "TableDataChange") {
        // if collection is "All" then reset to all tables, otherwise set to the selected collection.
        if (message.collection == "All") {
            await vpin.getTableData(reset = true);
        } else {
            vpin.call("console_out", "collection change.");
            await vpin.call("set_tables_by_collection", message.collection);
            await vpin.getTableData();
        }
        this.currentTableIndex = message.index;
        // NOW do something with the new table data. like update the images.
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
            vpin.sendMessageToAllWindows({ type: "TableLaunching" });
            await fadeOut();
            await vpin.launchTable(currentTableIndex);
            break;
        case "joyback":
            // do something on joyback if you want
            break;
    }
}

// Update the main BG image with smooth transition
function updateBGImage() {
    const container = document.getElementById('bgImageContainer');
    if (!container) return; // Window may not have this element

    const oldImg = container.querySelector('img');

    if (!vpin.tableData || vpin.tableData.length === 0) return;

    const bgUrl = vpin.getImageURL(currentTableIndex, "bg");

    if (oldImg) {
        oldImg.style.opacity = '0';
        setTimeout(() => {
            oldImg.src = bgUrl;
            oldImg.style.opacity = '1';
        }, 300);
    } else {
        const img = document.createElement('img');
        img.src = bgUrl;
        img.style.opacity = '0';
        img.onload = () => {
            requestAnimationFrame(() => {
                img.style.opacity = '1';
            });
        };
        container.appendChild(img);
    }
}

// Update DMD image for DMD window
function updateDMDImage() {
    const container = document.getElementById('dmdImageContainer');
    if (!container) return; // Window may not have this element

    const oldImg = container.querySelector('img');

    if (!vpin.tableData || vpin.tableData.length === 0) return;

    const dmdUrl = vpin.getImageURL(currentTableIndex, "dmd");

    if (oldImg) {
        oldImg.style.opacity = '0';
        setTimeout(() => {
            oldImg.src = dmdUrl;
            oldImg.style.opacity = '1';
        }, 300);
    } else {
        const img = document.createElement('img');
        img.src = dmdUrl;
        img.style.opacity = '0';
        img.onload = () => {
            requestAnimationFrame(() => {
                img.style.opacity = '1';
            });
        };
        container.appendChild(img);
    }
}

// Update table information text
function updateTableInfo() {
    if (!vpin.tableData || vpin.tableData.length === 0) return;

    const table = vpin.getTableMeta(currentTableIndex);
    const nameEl = document.getElementById('tableName');
    const metaEl = document.getElementById('tableMeta');
    const authorsEl = document.getElementById('authorsText');

    // Get table name from metadata
    const tableName = table?.meta?.VPSdb?.name ||
                     table?.meta?.VPXFile?.filename ||
                     table?.tableDirName ||
                     'Unknown Table';

    // Get manufacturer and year
    const manufacturer = table?.meta?.VPSdb?.manufacturer ||
                        table?.meta?.VPXFile?.manufacturer ||
                        'Unknown';
    const year = table?.meta?.VPSdb?.year ||
                table?.meta?.VPXFile?.year ||
                '';

    nameEl.textContent = tableName;
    metaEl.textContent = manufacturer + (year ? ' • ' + year : '');

    // Get authors
    const authors = table?.meta?.VPXFile?.author || 'Unknown';

    if (authorsEl) {
        authorsEl.textContent = authors;

        // Dynamically adjust authors font size based on text length
        const authorsLength = authors.length;
        let authorsFontSize;
        if (authorsLength <= 20) {
            authorsFontSize = '2vw';
        } else if (authorsLength <= 30) {
            authorsFontSize = '1.8vw';
        } else if (authorsLength <= 40) {
            authorsFontSize = '1.6vw';
        } else if (authorsLength <= 50) {
            authorsFontSize = '1.4vw';
        } else {
            authorsFontSize = '1.2vw';
        }
        authorsEl.style.fontSize = authorsFontSize;
    }

    // Dynamically adjust font size based on text length
    const textLength = tableName.length;
    let fontSize;
    if (textLength <= 20) {
        fontSize = '4vw';
    } else if (textLength <= 30) {
        fontSize = '3.5vw';
    } else if (textLength <= 40) {
        fontSize = '3vw';
    } else if (textLength <= 50) {
        fontSize = '2.5vw';
    } else {
        fontSize = '2vw';
    }
    nameEl.style.fontSize = fontSize;
}

// Build the carousel with wheel images
function buildCarousel() {
    const track = document.getElementById('carouselTrack');
    track.innerHTML = '';

    if (!vpin.tableData || vpin.tableData.length === 0) return;

    const totalTables = vpin.tableData.length;
    const visibleItems = Math.min(9, totalTables); // Show up to 9 items
    const sideItems = Math.floor(visibleItems / 2);

    for (let i = -sideItems; i <= sideItems; i++) {
        const idx = wrapIndex(currentTableIndex + i, totalTables);
        const wheelUrl = vpin.getImageURL(idx, "wheel");

        const item = document.createElement('div');
        item.className = 'carousel-item';
        if (i === 0) {
            item.classList.add('selected');
        }

        const img = document.createElement('img');
        img.src = wheelUrl;
        img.alt = 'Table ' + idx;

        // Handle missing images
        img.onerror = () => {
            const placeholder = document.createElement('div');
            placeholder.className = 'missing-placeholder';
            placeholder.textContent = 'No Image';
            item.innerHTML = '';
            item.appendChild(placeholder);
        };

        item.appendChild(img);
        track.appendChild(item);
    }
}

// Main update function
function updateScreen() {
    // Update based on window type
    if (windowName === "table") {
        updateBGImage();
        updateTableInfo();
        buildCarousel();
    } else if (windowName === "bg") {
        updateBGImage();
    } else if (windowName === "dmd") {
        updateDMDImage();
    }
}

// Smooth fade transition
async function fadeOut() {
    const fadeContainer = document.getElementById('fadeContainer');
    const bottomSection = document.querySelector('.bottom-section');
    fadeContainer.style.opacity = '0';
    if (bottomSection) bottomSection.style.opacity = '0';
    await new Promise(resolve => setTimeout(resolve, 300));
}

function fadeIn() {
    const fadeContainer = document.getElementById('fadeContainer');
    const bottomSection = document.querySelector('.bottom-section');
    fadeContainer.style.opacity = '1';
    if (bottomSection) bottomSection.style.opacity = '1';
}

//
// MISC suuport functions
//

// circular table index
function wrapIndex(index, length) {
    return (index + length) % length;
}
