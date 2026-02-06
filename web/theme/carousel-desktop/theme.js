/*
Testing theme with carousel layout
*/

// Globals
windowName = ""
currentTableIndex = 0;
isAnimating = false;

// init the core interface to VPinFE
const vpin = new VPinFECore();
vpin.init();
window.vpin = vpin // main menu needs this to call back in.

// Register receiveEvent globally BEFORE vpin.ready to avoid timing issues
window.receiveEvent = receiveEvent;

// wait for VPinFECore to be ready
vpin.ready.then(async () => {
    await vpin.call("get_my_window_name")
        .then(result => {
            windowName = result;
        });

    vpin.registerInputHandler(handleInput);

    // Initialize the display
    updateScreen();
});

// listener for windows events.  VPinFECore uses this to send events to all windows.
async function receiveEvent(message) {
    // Let VPinFECore handle the data refresh logic
    await vpin.handleEvent(message);

    // Handle UI updates based on event type
    if (message.type == "TableIndexUpdate") {
        currentTableIndex = message.index;
        updateScreen();
    }
    else if (message.type == "TableLaunching") {
        await fadeOut();
    }
    else if (message.type == "TableLaunchComplete") {
        fadeIn();
    }
    else if (message.type == "RemoteLaunching") {
        // Remote launch from manager UI
        showRemoteLaunchOverlay(message.table_name);
        await fadeOut();
    }
    else if (message.type == "RemoteLaunchComplete") {
        // Remote launch completed
        hideRemoteLaunchOverlay();
        fadeIn();
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
    joycollectionmenu
*/
async function handleInput(input) {
    if (isAnimating) return; // Prevent rapid inputs during animation

    switch (input) {
        case "joyleft":
            isAnimating = true;
            currentTableIndex = wrapIndex(currentTableIndex - 1, vpin.tableData.length);
            updateScreen('left');

            // tell other windows the table index changed
            vpin.sendMessageToAllWindows({
                type: 'TableIndexUpdate',
                index: this.currentTableIndex
            });
            break;
        case "joyright":
            isAnimating = true;
            currentTableIndex = wrapIndex(currentTableIndex + 1, vpin.tableData.length);
            updateScreen('right');

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

    if (!vpin.tableData || vpin.tableData.length === 0) {
        // Clear background image when no tables
        container.innerHTML = '';
        return;
    }

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

    if (!vpin.tableData || vpin.tableData.length === 0) {
        // Clear DMD image when no tables
        container.innerHTML = '';
        return;
    }

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
// Update table information text
function updateTableInfo() {
    if (!vpin.tableData || vpin.tableData.length === 0) {
        // Clear table info when no tables
        const nameEl = document.getElementById('tableName');
        const metaEl = document.getElementById('tableMeta');
        const authorsEl = document.getElementById('authorsText');
        if (nameEl) nameEl.textContent = 'No tables found';
        if (metaEl) metaEl.textContent = '';
        if (authorsEl) authorsEl.textContent = '';
        return;
    }

    const table = vpin.getTableMeta(currentTableIndex);
    const nameEl = document.getElementById('tableName');
    const metaEl = document.getElementById('tableMeta');
    const authorsEl = document.getElementById('authorsText');

    const info = table?.meta?.Info || {};
    const vpx = table?.meta?.VPXFile || {};

    // Get table name from Info.Title first, fallback to filename
    const tableName = info.Title || vpx.filename || table?.tableDirName || 'Unknown Table';

    // Get manufacturer and year from Info first, fallback to VPXFile
    const manufacturer = info.Manufacturer || vpx.manufacturer || 'Unknown';
    const year = info.Year || vpx.year || '';

    nameEl.textContent = tableName;
    metaEl.textContent = manufacturer + (year ? ' • ' + year : '');

    // Get authors from Info.Authors (array) or fallback
    let authors = 'Unknown';
    if (Array.isArray(info.Authors) && info.Authors.length > 0) {
        authors = info.Authors.join(', ');
    }

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

    // Dynamically adjust font size for table name
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
function buildCarousel(direction = null) {
    const track = document.getElementById('carouselTrack');

    if (!vpin.tableData || vpin.tableData.length === 0) {
        // Clear carousel when no tables
        track.innerHTML = '';
        isAnimating = false;
        return;
    }

    const totalTables = vpin.tableData.length;
    const visibleItems = Math.min(9, totalTables); // Show up to 9 items
    const sideItems = Math.floor(visibleItems / 2);

    // Get existing items
    const existingItems = Array.from(track.children);

    // If first build, number of items changed, or no direction (collection/filter change), rebuild completely
    if (existingItems.length === 0 || existingItems.length !== visibleItems || direction === null) {
        track.innerHTML = ''; // Clear all existing items
        for (let i = -sideItems; i <= sideItems; i++) {
            const idx = wrapIndex(currentTableIndex + i, totalTables);
            createCarouselItem(idx, i === 0, track);
        }
        isAnimating = false;
    } else if (direction !== null) {
        // Update with animation (only for left/right navigation)
        updateCarouselItems(existingItems, sideItems, totalTables, true);
    }

}

// Update carousel items in place
function updateCarouselItems(existingItems, sideItems, totalTables, animated = false) {
    existingItems.forEach((item, index) => {
        const offset = index - sideItems;
        const idx = wrapIndex(currentTableIndex + offset, totalTables);
        const wheelUrl = vpin.getImageURL(idx, "wheel");

        // Update selected class
        if (offset === 0) {
            item.classList.add('selected');

            // Add jiggle animation when animated
            if (animated) {
                // Remove jiggle first in case it's already there
                item.classList.remove('jiggle');

                // Use requestAnimationFrame to ensure the removal is processed
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        item.classList.add('jiggle');

                        // Remove jiggle class after animation completes
                        setTimeout(() => {
                            item.classList.remove('jiggle');
                        }, 500);
                    });
                });
            }
        } else {
            item.classList.remove('selected');
            item.classList.remove('jiggle');
        }

        // Update image
        const img = item.querySelector('img');
        if (img && img.src !== wheelUrl) {
            img.src = wheelUrl;
            img.alt = 'Table ' + idx;
        }
    });

    // If animated, wait for CSS transition to complete
    if (animated) {
        setTimeout(() => {
            isAnimating = false;
        }, 600);
    }
}

// Helper function to create a carousel item
function createCarouselItem(idx, isSelected, track) {
    const wheelUrl = vpin.getImageURL(idx, "wheel");

    const item = document.createElement('div');
    item.className = 'carousel-item';
    if (isSelected) {
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

// Main update function
function updateScreen(direction = null) {
    // Update based on window type
    if (windowName === "table") {
        updateBGImage();
        updateTableInfo();
        buildCarousel(direction);
    } else if (windowName === "bg") {
        updateBGImage();
    } else if (windowName === "dmd") {
        updateDMDImage();
    }
}

// Smooth fade transition - wait for CSS transition to complete
async function fadeOut() {
    const fadeContainer = document.getElementById('fadeContainer');

    return new Promise(resolve => {
        fadeContainer.addEventListener('transitionend', e => {
            if (e.propertyName === 'opacity') resolve();
        }, { once: true });

        fadeContainer.style.opacity = '0';
    });
}

function fadeIn() {
    const fadeContainer = document.getElementById('fadeContainer');
    fadeContainer.style.opacity = '1';
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

//
// MISC suuport functions
//

// circular table index
function wrapIndex(index, length) {
    return (index + length) % length;
}
