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

    // Gamepad mapping
    this.joyButtonMap = {}
    this.previousButtonStates = {};
    this.gamepadEnabled = true;

    // menu is up?
    this.menuUP = false;
  }

  // ***********************************
  // Public api
  // ***********************************

  init() {
    // Set up other event listeners (TODO) - NOT USED
    window.addEventListener('keydown', (e) => this.onKeyDown(e));

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

  // Keybaord input processing to handlers (TODO)
  async onKeyDown(e) {
    windowName = await this.call("get_my_window_name");
    if (windowName == "table") {
      if (!this.menuUP) {
        if (e.key == "Escape") window.pywebview.api.close_app();
        else if (e.key == 'Control' && e.location === 1) this.inputHandlers.forEach(handler => handler("joyleft"));
        else if (e.key == 'Control' && e.location === 2) this.inputHandlers.forEach(handler => handler("joyright"));
        else if (e.key == 'Enter') this.inputHandlers.forEach(handler => handler("joyselect"));
        else if (e.key == 'm') this.#showmenu();
      }
      else { // Menu is up route to its handler
        if (e.key == 'Control' && e.location === 1) this.inputHandlerMenu.forEach(handler => handler("joyup"));
        else if (e.key == 'Control' && e.location === 2) this.inputHandlerMenu.forEach(handler => handler("joydown"));
        else if (e.key == 'Enter') this.inputHandlerMenu.forEach(handler => handler("joyselect"));
        else if (e.key == 'm') this.#showmenu();
      }

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
      this.call("console_out", this.#convertImagePathToURL(table.TableImagePath))
      return this.#convertImagePathToURL(table.TableImagePath);
    }
    else if (type == "bg") {
      this.call("console_out", this.#convertImagePathToURL(table.BGImagePath))
      return this.#convertImagePathToURL(table.BGImagePath);

    }
    else if (type == "dmd") {
      this.call("console_out", this.#convertImagePathToURL(table.DMDImagePath))
      return this.#convertImagePathToURL(table.DMDImagePath);

    }
    else if (type == "wheel") {
      this.call("console_out", this.#convertImagePathToURL(table.WheelImagePath))
      return this.#convertImagePathToURL(table.WheelImagePath);
    }
    else if (type == "cab") {
      this.call("console_out", this.#convertImagePathToURL(table.CabImagePath))
      return this.#convertImagePathToURL(table.CabImagePath);
    }
  }

  // send a message to all windows except "self"
  sendMessageToAllWindows(message) {
    this.call("send_event_all_windows", message);
  }

  // send a message to all windows including "self"
  sendMessageToAllWindowsIncSelf(message) {
    this.call("send_event_all_windows_incself", message);
  }

  // launch a table
  async launchTable(index) {
    this.gamepadEnabled = false;
    await this.call("launch_table", index);
    this.call("console_out", "vpinfe-core returning")
    this.gamepadEnabled = true;
  }

  // **********************************************
  // private functions
  // **********************************************

  async #onPyWebviewReady() {
    console.log("pywebview is ready!");
    await this.#loadMonitors();
    await this.#getTableData();
    this.#overrideConsole();

    // only run on the table window.. Its the master controller for all screens/windows
    if (await vpin.call("get_my_window_name") == "table") {
      await this.#initGamepadMapping();
      this.#updateGamepads();           // No await needed here — runs loop
    }
  }

  async #getTableData() {
    this.tableData = JSON.parse(await window.pywebview.api.get_tables());
  }

  async #loadMonitors() {
    this.monitors = await window.pywebview.api.get_monitors();
  }

  // Gamepad handling
  async #initGamepadMapping() {
    const joymap = await this.call("get_joymaping");
    this.joyButtonMap = Object.fromEntries(
      Object.entries(joymap).map(([key, val]) => [val, key])
    );
  }

  async #onButtonPressed(buttonIndex, gamepadIndex) {
    const action = this.joyButtonMap[buttonIndex.toString()];
    if (action) {
      if (action === "joyexit" && windowName == "table") { //DELETE. Menu handles this now
        //window.pywebview.api.close_app();
      }
      else if (action === "joymenu" && windowName == "table") {

        this.#showmenu();
      }
      else {
        if (!this.menuUP) {
          this.inputHandlers.forEach(handler => handler(action));
        }
        else { // Menu is up route to its handler
          this.inputHandlerMenu.forEach(handler => handler(action));
        }
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
            this.call("console_out", "Button: " + index);
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
      return "../../images/file_missing.png";  // fallback default
    }
    const parts = localPath.split('/');
    const dir = parts[parts.length - 2];     // second-to-last part = folder
    const file = parts[parts.length - 1];    // last part = filename
    return `http://127.0.0.1:8000/tables/${encodeURIComponent(dir)}/${encodeURIComponent(file)}`;
  }

  async #showmenu() {
    const overlayRoot = document.getElementById('overlay-root');
    let iframe = document.getElementById("menu-frame");

    if (!this.menuUP) {
      this.menuUP = true;
      overlayRoot.classList.add("active"); // fade in

      if (!iframe) {
        iframe = document.createElement("iframe");
        iframe.src = "../../mainmenu/mainmenu.html";
        iframe.id = "menu-frame";
        iframe.style.display = "none"; // start hidden to prevent flash
        overlayRoot.appendChild(iframe);
        await new Promise(resolve => setTimeout(resolve, 10)); // tiny delay to allow DOM update
      }

      iframe.style.display = "block"; // show iframe
    } else {
      this.menuUP = false;
      overlayRoot.classList.remove("active"); // fade out

      if (iframe) {
        iframe.style.display = "none"; // just hide, don’t remove
        iframe.contentWindow.postMessage({ event: "reset state" }, "*");
      }
      //this.#deregisterAllInputHandlersMenu();  // only need this when we destory it.
    }
  }

  // Menu deregister for Input Events
  async #deregisterAllInputHandlersMenu() {
    this.inputHandlerMenu = [];
    this.call("console_out", "cleared the menu gamepad handler. aka menu closed");
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