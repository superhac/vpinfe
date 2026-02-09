//console methods for overriding
const originalConsole = {
  log: console.log,
  info: console.info,
  warn: console.warn,
  error: console.error,
  debug: console.debug,
};


class VPinFECore {
  constructor() {
    this.tableData = {};
    this.monitors = [];
    this._resolveReady = null;
    this.ready = new Promise(resolve => this._resolveReady = resolve);
    this.inputHandlers = []; // gamepad and joystick input handlers for theme
    this.inputHandlerMenu = []; // gamepad and joystick input handlers for menu
    this.inputHandlerCollectionMenu = []; // gamepad and joystick input handlers for collection menu

    // Gamepad mapping
    this.joyButtonMap = {}
    this.previousButtonStates = {};
    this.gamepadEnabled = true;

    // menu is up?
    this.menuUP = false;
    this.collectionMenuUP = false;

    // Event handling
    this.eventHandlers = {}; // Custom event handlers registered by themes

    // Network config
    this.themeAssetsPort = 8000; // default, will be updated from config
    this.managerUiPort = 8001; // default manager UI port

    // Remote launch state tracking
    this.remoteLaunchActive = false;

  }

  // ***********************************
  // Public api
  // ***********************************

  init() {
    // Set up keyboard listener
    window.addEventListener('keydown', (e) => this.#onKeyDown(e));
   
    // Wait for pywebview then run all async init
    window.addEventListener('pywebviewready', async () => {
      await this.#onPyWebviewReady();  // Wait until everything is done
      this._resolveReady();           // Now we're truly ready
    });
  }

  // theme register for Input events - Only for the table screen!
  async registerInputHandler(handler) {
    windowName = await this.call("get_my_window_name");
    if (typeof handler === 'function' && windowName == "table") {
      this.call("console_out", "registered gamepad handler");
      this.inputHandlers.push(handler);
    }
  }

  // Menu register for Input events
  async registerInputHandlerMenu(handler) {
    if (typeof handler === 'function') {
      this.call("console_out", "registered gamepad handler");
      this.inputHandlerMenu.push(handler);
    }
  }

  // Collection Menu register for Input events
  async registerInputHandlerCollectionMenu(handler) {
    if (typeof handler === 'function') {
      this.call("console_out", "registered collection menu gamepad handler");
      this.inputHandlerCollectionMenu.push(handler);
    }
  }

  async call(method, ...args) {
    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api[method] === 'function') {
      return await window.pywebview.api[method](...args);
    } else {
      const errMsg = `Method ${method} does not exist on window.pywebview.api`;
      console.error(errMsg);
      throw new Error(errMsg);
    }
  }

  // get table image url paths
  getImageURL(index, type) {
    const table = this.tableData[index];
    if (type == "table") {
      //this.call("console_out", this.#convertImagePathToURL(table.TableImagePath))
      return this.#convertImagePathToURL(table.TableImagePath);
    }
    else if (type == "bg") {
      //this.call("console_out", this.#convertImagePathToURL(table.BGImagePath))
      return this.#convertImagePathToURL(table.BGImagePath);

    }
    else if (type == "dmd") {
      //this.call("console_out", this.#convertImagePathToURL(table.DMDImagePath))
      return this.#convertImagePathToURL(table.DMDImagePath);

    }
    else if (type == "wheel") {
      //this.call("console_out", this.#convertImagePathToURL(table.WheelImagePath))
      return this.#convertImagePathToURL(table.WheelImagePath);
    }
    else if (type == "cab") {
      //this.call("console_out", this.#convertImagePathToURL(table.CabImagePath))
      return this.#convertImagePathToURL(table.CabImagePath);
    }
  }

  // get table video url paths
  getVideoURL(index, type) {
    const table = this.tableData[index];
    if (type == "table") {
      return this.#convertImagePathToURL(table.TableVideoPath);
    }
    else if (type == "bg") {
      return this.#convertImagePathToURL(table.BGVideoPath);
    }
    else if (type == "dmd") {
      return this.#convertImagePathToURL(table.DMDVideoPath);
    }
  }

  getTableMeta(index) {
    return this.tableData[index];
  }

  getTableCount() {
    return this.tableData.length;
  }

  // send a message to all windows except "self"
  sendMessageToAllWindows(message) {
    this.call("send_event_all_windows", message);
  }

  // send a message to all windows including "self"
  sendMessageToAllWindowsIncSelf(message) {
    this.call("send_event_all_windows_incself", message);
  }

  // Toggle collection menu (public method callable from collection menu)
  toggleCollectionMenu() {
    this.#showcollectionmenu();
  }

  // Toggle main menu (public method callable from main menu)
  toggleMenu() {
    this.#showmenu();
  }

  // launch a table
  async launchTable(index) {
    this.gamepadEnabled = false;
    await this.call("launch_table", index);
    this.call("console_out", "vpinfe-core returning")
    this.gamepadEnabled = true;
  }

  async getTableData(reset=false) {
    this.tableData = JSON.parse(await window.pywebview.api.get_tables(reset));
  }

  // Register an event handler for a specific event type
  // eventType: string (e.g., "TableIndexUpdate", "TableDataChange", etc.)
  // handler: function to call when event is received
  registerEventHandler(eventType, handler) {
    if (typeof handler === 'function') {
      if (!this.eventHandlers[eventType]) {
        this.eventHandlers[eventType] = [];
      }
      this.eventHandlers[eventType].push(handler);
      this.call("console_out", `Registered event handler for ${eventType}`);
    }
  }

  // Handle incoming events from window.receiveEvent
  // This should be called from the theme's receiveEvent function
  async handleEvent(message) {
    // Default handling for TableDataChange
    if (message.type === "TableDataChange") {
      await this.#handleTableDataChange(message);
    }

    // Call any custom handlers registered by the theme
    if (this.eventHandlers[message.type]) {
      for (const handler of this.eventHandlers[message.type]) {
        await handler(message);
      }
    }
  }

  // Default handler for TableDataChange events
  async #handleTableDataChange(message) {
    // Check if a collection filter was applied
    if (message.collection) {
      // if collection is "None" then reset to all tables, otherwise set to the selected collection.
      if (message.collection === "None") {
        await this.getTableData(true);
      } else {
        await this.call("set_tables_by_collection", message.collection);
        await this.getTableData();
      }
    } else if (message.filters) {
      // VPSdb filters - apply them to this window's API instance
      await this.call("apply_filters",
        message.filters.letter,
        message.filters.theme,
        message.filters.type,
        message.filters.manufacturer,
        message.filters.year
      );
      // If a sort order is also specified, apply it after filters
      if (message.sort) {
        await this.call("apply_sort", message.sort);
      }
      await this.getTableData();
    } else if (message.sort) {
      // Sort order change - apply it to this window's API instance
      await this.call("apply_sort", message.sort);
      await this.getTableData();
    } else {
      // No filters specified - just refresh table data
      await this.getTableData();
    }
  }


  // **********************************************
  // private functions
  // **********************************************

  async #onPyWebviewReady() {
    console.log("pywebview is ready!");
    // Load network config
    this.themeAssetsPort = await this.call("get_theme_assets_port");
    await this.#loadMonitors();
    await this.getTableData();
   //this.#overrideConsole(); //disabled for now...

    // only run on the table window.. Its the master controller for all screens/windows
    if (await vpin.call("get_my_window_name") == "table") {
      await this.#initGamepadMapping();
      this.#setupGamepadListeners();
      this.#updateGamepads();           // No await needed here — runs loop
      this.#pollRemoteLaunch();         // Poll for remote launch events
    }
  }

  #setupGamepadListeners() {
    // Listen for gamepad connection events
    window.addEventListener("gamepadconnected", (e) => {
      this.call("console_out", `Gamepad connected: ${e.gamepad.id} (index ${e.gamepad.index})`);
      // Reset button states for this gamepad
      this.previousButtonStates[e.gamepad.index] = new Array(e.gamepad.buttons.length).fill(false);
    });

    window.addEventListener("gamepaddisconnected", (e) => {
      this.call("console_out", `Gamepad disconnected: ${e.gamepad.id} (index ${e.gamepad.index})`);
      delete this.previousButtonStates[e.gamepad.index];
    });

    // Check if gamepad is already connected (may have been connected before page load)
    this.#waitForGamepad();
  }

  #waitForGamepad(attempts = 0, maxAttempts = 30) {
    const gamepads = navigator.getGamepads();
    const hasGamepad = Array.from(gamepads).some(gp => gp !== null);

    if (hasGamepad) {
      this.call("console_out", "Gamepad detected and ready");
      return;
    }

    if (attempts < maxAttempts) {
      // Retry every 500ms for up to 15 seconds
      setTimeout(() => this.#waitForGamepad(attempts + 1, maxAttempts), 500);
    } else {
      this.call("console_out", "No gamepad detected after waiting. Will detect when connected.");
    }
  }

  async #triggerInputAction(action) {
    if(this.collectionMenuUP) {
      // Collection menu is up, route to its handler
      this.inputHandlerCollectionMenu.forEach(handler => handler(action));
    }
    else if(this.menuUP) {
      // Menu is up route to its handler
      this.inputHandlerMenu.forEach(handler => handler(action));
    }
    else {
      // No menu is up, route to theme handler
      this.inputHandlers.forEach(handler => handler(action));
    }
  }

  // Keybaord input processing to handlers
  async #onKeyDown(e) {
    windowName = await this.call("get_my_window_name");
    if (windowName == "table") {
      if (e.key === "Escape" || e.key === 'q') window.pywebview.api.close_app();
      else if (e.key === 'ArrowLeft' || e.code === 'ShiftLeft') this.#triggerInputAction("joyleft");
      else if (e.key === 'ArrowRight' || e.code === 'ShiftRight') this.#triggerInputAction("joyright");
      else if (e.key === 'Enter') this.#triggerInputAction("joyselect");
      else if (e.key === 'm') this.#showmenu();
      else if (e.key === 'c') this.#showcollectionmenu();
    }
  }

  async #loadMonitors() {
    this.monitors = await window.pywebview.api.get_monitors();
  }

  // Gamepad handling
 async #initGamepadMapping() {
  const joymap = await this.call("get_joymaping");

  // Collect multiple actions per button. sometimes the same button has two mappings
  this.joyButtonMap = {};
  for (const [action, button] of Object.entries(joymap)) {
    if (!this.joyButtonMap[button]) {
      this.joyButtonMap[button] = [];
    }
    this.joyButtonMap[button].push(action);
  }

  //this.call("console_out", "Gamepad mapping loaded: " + JSON.stringify(this.joyButtonMap));
}

async #onButtonPressed(buttonIndex, gamepadIndex) {
  const actions = this.joyButtonMap[buttonIndex.toString()];
  if (!actions) return;

  // Handle all actions mapped to this button
  for (const action of actions) {
    //this.call("console_out", `Button action: ${action}, windowName: ${windowName}`);
    if (action === "joyexit" && windowName == "table") {
      window.pywebview.api.close_app();
    }
    else if (action === "joymenu" && windowName == "table") {
      this.#showmenu();
    }
    else if (action === "joycollectionmenu" && windowName == "table") {
      this.call("console_out", "Triggering collection menu");
      this.#showcollectionmenu();
    }
    else {
      this.#triggerInputAction(action);
    }
  }
}

  #updateGamepads() {
    if (this.gamepadEnabled) {
      const gamepads = navigator.getGamepads();
      for (let i = 0; i < gamepads.length; i++) {
        const gp = gamepads[i];
        if (!gp) continue;

        if (!this.previousButtonStates[i]) {
          this.previousButtonStates[i] = new Array(gp.buttons.length).fill(false);
        }

        gp.buttons.forEach((button, index) => {
          const wasPressed = this.previousButtonStates[i][index];
          const isPressed = button.pressed;

          if (isPressed && !wasPressed) {
            //this.call("console_out", "Button: " + index);
            this.#onButtonPressed(index, i); // new press
          }
          this.previousButtonStates[i][index] = isPressed;
        });
      }
    }
    requestAnimationFrame(() => this.#updateGamepads());
  }

  // convert the hard full local path to the web servers url map
  #convertImagePathToURL(localPath) {
    if (!localPath || typeof localPath !== 'string') {
      return "/web/images/file_missing.png";  // fallback default
    }
    const parts = localPath.split('/');
    const file = parts[parts.length - 1];    // last part = filename
    const port = this.themeAssetsPort;

    // Check if the path includes a medias/ subfolder
    if (parts.length >= 3 && parts[parts.length - 2] === 'medias') {
      const tableDir = parts[parts.length - 3];  // table folder is 3rd from end
      return `http://127.0.0.1:${port}/tables/${encodeURIComponent(tableDir)}/medias/${encodeURIComponent(file)}`;
    }

    // Fallback: image is directly in table folder
    const dir = parts[parts.length - 2];     // second-to-last part = folder
    return `http://127.0.0.1:${port}/tables/${encodeURIComponent(dir)}/${encodeURIComponent(file)}`;
  }

  async #showmenu() {
    const overlayRoot = document.getElementById('overlay-root');
    let iframe = document.getElementById("menu-frame");

    // Close collection menu if it's open
    if (this.collectionMenuUP) {
      await this.#showcollectionmenu();
    }

    if (!this.menuUP) {
      this.menuUP = true;
      overlayRoot.classList.add("active"); // fade in

      if (!iframe) {
        iframe = document.createElement("iframe");
        iframe.src = "/web/mainmenu/mainmenu.html";
        iframe.id = "menu-frame";
        iframe.setAttribute("allowTransparency", "true");
        iframe.style.display = "none"; // start hidden to prevent flash
        overlayRoot.appendChild(iframe);
        await new Promise(resolve => setTimeout(resolve, 10)); // tiny delay to allow DOM update
      }

      iframe.style.display = "block"; // show iframe
    } else {
      this.menuUP = false;
      overlayRoot.classList.remove("active"); // fade out

      if (iframe) {
        iframe.style.display = "none"; // just hide, don't remove
        iframe.contentWindow.postMessage({ event: "reset state" }, "*");
      }
      //this.#deregisterAllInputHandlersMenu();  // only need this when we destory it.
    }
  }

  async #showcollectionmenu() {
    const overlayRoot = document.getElementById('overlay-root');
    let iframe = document.getElementById("collection-menu-frame");

    // Close main menu if it's open
    if (this.menuUP) {
      await this.#showmenu();
    }

    if (!this.collectionMenuUP) {
      this.collectionMenuUP = true;
      overlayRoot.classList.add("active"); // fade in

      if (!iframe) {
        iframe = document.createElement("iframe");
        iframe.src = "/web/collectionmenu/collectionmenu.html";
        iframe.id = "collection-menu-frame";
        iframe.setAttribute("allowTransparency", "true");
        iframe.style.display = "none"; // start hidden to prevent flash
        overlayRoot.appendChild(iframe);
        await new Promise(resolve => setTimeout(resolve, 10)); // tiny delay to allow DOM update
      }

      iframe.style.display = "block"; // show iframe
    } else {
      this.collectionMenuUP = false;
      overlayRoot.classList.remove("active"); // fade out

      if (iframe) {
        iframe.style.display = "none"; // just hide, don't remove
        iframe.contentWindow.postMessage({ event: "reset state" }, "*");
      }
    }
  }

  // Menu deregister for Input Events
  async #deregisterAllInputHandlersMenu() {
    this.inputHandlerMenu = [];
    this.call("console_out", "cleared the menu gamepad handler. aka menu closed");
  }

  // Poll the manager UI for remote launch events
  #pollRemoteLaunch() {
    const pollInterval = 1000; // Poll every 1 second
    const managerUrl = `http://127.0.0.1:${this.managerUiPort}/api/remote-launch`;

    console.log("[RemoteLaunch] Starting poll to:", managerUrl);

    const poll = async () => {
      try {
        const response = await fetch(managerUrl);
        if (response.ok) {
          const data = await response.json();

          // Check if launch state changed
          if (data.launching && !this.remoteLaunchActive) {
            // Remote launch started
            this.remoteLaunchActive = true;
            console.log("[RemoteLaunch] Launch detected:", data.table_name);
            this.call("console_out", `Remote launching: ${data.table_name}`);
            // Send TableLaunching event to all windows with the table name
            this.sendMessageToAllWindowsIncSelf({
              type: "RemoteLaunching",
              table_name: data.table_name
            });
          } else if (!data.launching && this.remoteLaunchActive) {
            // Remote launch completed
            this.remoteLaunchActive = false;
            console.log("[RemoteLaunch] Launch completed");
            this.call("console_out", "Remote launch completed");
            // Send completion event
            this.sendMessageToAllWindowsIncSelf({
              type: "RemoteLaunchComplete"
            });
          }
        }
      } catch (e) {
        // Manager UI might not be running, that's OK - silently ignore
        // But log first few failures for debugging
        console.log("[RemoteLaunch] Poll error (manager UI may not be running):", e.message);
      }

      // Continue polling
      setTimeout(poll, pollInterval);
    };

    // Start polling
    poll();
  }

  // override console and send them to the python console instead
  #overrideConsole() {
    Object.keys(originalConsole).forEach(method => {
      console[method] = function (...args) {
        // Call original method
        originalConsole[method].apply(console, args);
        // Append to page
        vpin.call("console_out", method + ':' + args);
      };
    });
  }

}