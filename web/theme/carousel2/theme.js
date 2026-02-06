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

// Hook for Python events
async function receiveEvent(message) {
    vpin.call("console_out", message);

    // Let VPinFECore handle the data refresh logic
    await vpin.handleEvent(message);

    // Handle UI updates based on event type
    if (message.type == "TableIndexUpdate") {
        currentTableIndex = message.index;
        updateImages();
    }
    else if (message.type == "TableLaunching") {
        fadeOut();
    }
    else if (message.type == "TableLaunchComplete") {
        fadeInScreen();
    }
    else if (message.type == "RemoteLaunching") {
        // Remote launch from manager UI
        showRemoteLaunchOverlay(message.table_name);
        fadeOut();
    }
    else if (message.type == "RemoteLaunchComplete") {
        // Remote launch completed
        hideRemoteLaunchOverlay();
        fadeInScreen();
    }
    else if (message.type == "TableDataChange") {
        currentTableIndex = message.index;
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
    // Check for empty table data
    if (!vpin.tableData || vpin.tableData.length === 0) {
        clearAllDisplays();
        return;
    }

    setCarouselWheels();
    setMainGfxImage();
    setTableImage();
}

function clearAllDisplays() {
    // Clear carousel
    const carouselContainer = document.getElementById('carouselImages');
    if (carouselContainer) carouselContainer.innerHTML = '';

    // Clear main graphics
    const maingfxContainer = document.getElementById('maingfx');
    if (maingfxContainer) maingfxContainer.innerHTML = '';

    // Clear cab image
    const cabContainer = document.getElementById('cab');
    if (cabContainer) {
        const imgs = cabContainer.querySelectorAll('img');
        imgs.forEach(img => img.remove());
    }
}

function setTableImage() {
    const bgUrl = vpin.getImageURL(currentTableIndex, "cab");
    const container = document.getElementById('cab');
    const label = document.getElementById('cab-missing-label');
    const oldImg = container.querySelector('img');
    const isMissing = bgUrl.includes('file_missing.png');

    function getTableName(table) {
        const info = table.meta?.Info || {};
        const vpx = table.meta?.VPXFile || {};
        return info.Title || vpx.filename || table.tableDirName || 'Unknown Table';
    }

    if (oldImg) {
        oldImg.style.opacity = 0;

        setTimeout(() => {
            // Remove old image but keep the label
            const imgs = container.querySelectorAll('img');
            imgs.forEach(img => img.remove());

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

            // Show table name if image is missing
            if (isMissing && vpin.tableData[currentTableIndex]) {
                const table = vpin.tableData[currentTableIndex];
                const tableName = getTableName(table);
                vpin.call("console_out", "CAB Missing image detected, showing: " + tableName);
                label.textContent = tableName;
                label.style.display = 'block';
            } else {
                label.style.display = 'none';
            }
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

        // Show table name if image is missing
        if (isMissing && vpin.tableData[currentTableIndex]) {
            const table = vpin.tableData[currentTableIndex];
            const tableName = getTableName(table);
            vpin.call("console_out", "CAB Missing image detected (no old img), showing: " + tableName);
            label.textContent = tableName;
            label.style.display = 'block';
        } else {
            label.style.display = 'none';
        }
    }
}

function setMainGfxImage() {
    let gfx = 'bg';
    if (config) gfx = config.maingfx;

    const container = document.getElementById('bg');
    const label = document.getElementById('bg-missing-label');
    const oldImg = container.querySelector('img');
    const imageUrl = vpin.getImageURL(currentTableIndex, gfx);
    const isMissing = imageUrl.includes('file_missing.png');

    if (oldImg) {
        oldImg.style.opacity = 0;

        setTimeout(() => {
            // Remove old image but keep the label
            const imgs = container.querySelectorAll('img');
            imgs.forEach(img => img.remove());

            const newImg = new Image();
            newImg.src = imageUrl;
            newImg.alt = "bgImage";
            newImg.style.opacity = 0;

            newImg.onload = () => {
                requestAnimationFrame(() => {
                    newImg.style.opacity = 1;
                });
            };

            container.appendChild(newImg);

            // Show table name if image is missing
            if (isMissing && vpin.tableData[currentTableIndex]) {
                const table = vpin.tableData[currentTableIndex];
                const tableName = table.meta?.VPSdb?.name ||
                                  table.meta?.VPXFile?.filename ||
                                  table.tableDirName ||
                                  'Unknown Table';
                vpin.call("console_out", "BG Missing image detected, showing: " + tableName);
                label.textContent = tableName;
                label.style.display = 'block';
            } else {
                label.style.display = 'none';
            }
        }, 300); // match transition duration
    } else {
        const img = new Image();
        img.src = imageUrl;
        img.alt = "bgImage";
        img.style.opacity = 0;

        img.onload = () => {
            requestAnimationFrame(() => {
                img.style.opacity = 1;
            });
        };

        container.appendChild(img);

        // Show table name if image is missing
        if (isMissing && vpin.tableData[currentTableIndex]) {
            const table = vpin.tableData[currentTableIndex];
            const tableName = table.meta?.VPSdb?.name ||
                              table.meta?.VPXFile?.filename ||
                              table.tableDirName ||
                              'Unknown Table';
            vpin.call("console_out", "BG Missing image detected (no old img), showing: " + tableName);
            label.textContent = tableName;
            label.style.display = 'block';
        } else {
            label.style.display = 'none';
        }
    }
}

function setCarouselWheels() {
    const imagesContainer = document.getElementById('carouselImages');
    imagesContainer.innerHTML = ""; // clear previous images

    const containerWidth = imagesContainer.clientWidth;
    const averageImageWidth = 7 * window.innerWidth / 100 + 30; // 6vw + 30px gap
    const total = vpin.tableData.length;

    if (total === 0) return; // no wheels, nothing to do

    // Calculate how many images fit, subtract 1 for the center image
    const maxVisible = Math.floor(containerWidth / averageImageWidth);
    const visibleCount = Math.min(total, maxVisible); // don't show more than we have

    const sideImages = Math.floor((visibleCount - 1) / 2);

    for (let i = -sideImages; i <= sideImages; i++) {
        // If we have fewer wheels than visible, just iterate over all
        const idx = (visibleCount < total)
            ? wrapIndex(currentTableIndex + i, total)
            : (currentTableIndex + i + total) % total;

        const wheelUrl = vpin.getImageURL(idx, "wheel");
        const img = document.createElement('img');
        img.src = wheelUrl;

        if (i === 0 || total <= visibleCount && idx === currentTableIndex) {
            img.classList.add('selected');
        }

        imagesContainer.appendChild(img);
    }
}


