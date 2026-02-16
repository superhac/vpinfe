"""
Chromium process manager for launching and managing embedded Chromium instances.

Based on the working vpinfe-chrome-test/embchrometest.py prototype.
Each configured display gets its own Chromium process in --app mode,
positioned on the correct monitor with fullscreen.
"""

import os
import sys
from shutil import which
import platform
import subprocess
import tempfile
import signal
import threading
import time


def resource_path(relative_path):
    """Get absolute path to resource, works for both dev and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Running from source - project root
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def get_chromium_path():
    """Get the platform-specific path to the Chromium binary."""
    system = platform.system()

    if system == "Windows":
        # Check common system Chrome/Chromium install paths first
        common_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Chromium\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Chromium\Application\chrome.exe"),
        ]
        for path in common_paths:
            if os.path.isfile(path):
                return path
        return resource_path("chromium/windows/chrome-win/chrome.exe")
    elif system == "Darwin":
        return resource_path("chromium/Chromium.app/Contents/MacOS/Chromium")
    elif system == "Linux":
        # Check if chromium is locally available on the system. 
        # If so use that instead of bundled chromium.
        if which("chromium") is not None:
            return which("chromium")
        return resource_path("chromium/linux/chrome/chrome")
    else:
        raise RuntimeError(f"Unsupported OS: {system}")


class ChromiumManager:
    """Manages Chromium subprocess lifecycle for multi-monitor display."""

    def __init__(self):
        self._processes = []   # [(window_name, process, temp_dir, monitor)]
        self._exit_event = threading.Event()

    def launch_window(self, window_name, url, monitor, index):
        """Launch one Chromium instance for a given monitor.

        Args:
            window_name: 'bg', 'dmd', or 'table'
            url: The URL to load (e.g. http://127.0.0.1:8000/web/splash.html?window=bg)
            monitor: screeninfo Monitor object with x, y, width, height
            index: Unique index for temp profile directory
        """
        chrome_path = get_chromium_path()
        if not os.path.exists(chrome_path):
            raise FileNotFoundError(f"Chromium binary not found: {chrome_path}")

        user_data_dir = tempfile.mkdtemp(prefix=f"vpinfe_chromium_{window_name}_{index}_")

        # Suppress "Google API keys missing" banner
        env = os.environ.copy()
        env["GOOGLE_API_KEY"] = "no"
        env["GOOGLE_DEFAULT_CLIENT_ID"] = "no"
        env["GOOGLE_DEFAULT_CLIENT_SECRET"] = "no"

        # Use --kiosk on Windows to avoid dual-window issue with --start-fullscreen
        #fullscreen_flag = "--kiosk" if platform.system() == "Windows" else "--start-fullscreen"

        fullscreen_flag = "--kiosk"

        args = [
            chrome_path,
            f"--app={url}",
            f"--window-name=vpinfe-{window_name}",
            fullscreen_flag,
            f"--window-position={monitor.x},{monitor.y}",
            f"--window-size={monitor.width},{monitor.height}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--disable-infobars",
            "--disable-session-crashed-bubble",
            "--disable-restore-session-state",
            "--log-level=3",
            # Prevent throttling/freezing when window is not focused. This is
            # important for Linux when an external game takes focus and occludes
            # the frontend window.
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-media-suspend",
            "--disable-features=CalculateNativeWindowOcclusion",
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-gpu-process-crash-limit",
            "--use-gl=desktop",
            # Fix for Gamepad API losing connection after focus switch on Linux.
            # Allows re-accessing /dev/input devices and bypasses gesture requirements.
            "--no-sandbox",
            "--disable-gpu-sandbox",
            "--autoplay-policy=no-user-gesture-required",
        ]

        print(f"[Chromium] Launching '{window_name}' on monitor {index} "
              f"({monitor.width}x{monitor.height} at {monitor.x},{monitor.y})")

        # Launch in its own process group so we can kill the entire tree on shutdown
        # (Chromium spawns renderers, GPU, zygote children that must all be killed)
        popen_kwargs = dict(env=env)
        if platform.system() != "Windows":
            popen_kwargs['start_new_session'] = True

        proc = subprocess.Popen(args, **popen_kwargs)
        self._processes.append((window_name, proc, user_data_dir, monitor))
        return proc

    def launch_all_windows(self, iniconfig, base_url="http://127.0.0.1"):
        """Launch Chromium windows for all configured displays.

        Args:
            iniconfig: IniConfig instance with display and network settings
            base_url: Base URL for the HTTP server
        """
        from screeninfo import get_monitors
        monitors = get_monitors()
        print(f"[Chromium] Detected {len(monitors)} monitors: {monitors}")

        theme_assets_port = int(iniconfig.config['Network'].get('themeassetsport', '8000'))

        # Launch windows in order: bg, dmd, table (table last so it gets focus)
        window_configs = [
            ('bg', 'bgscreenid'),
            ('dmd', 'dmdscreenid'),
            ('table', 'tablescreenid'),
        ]

        for window_name, config_key in window_configs:
            screen_id_str = iniconfig.config['Displays'].get(config_key, '').strip()
            if not screen_id_str:
                continue

            screen_id = int(screen_id_str)
            if screen_id >= len(monitors):
                print(f"[Chromium] Warning: {config_key}={screen_id} but only {len(monitors)} monitors found")
                continue

            monitor = monitors[screen_id]
            url = f"{base_url}:{theme_assets_port}/web/splash.html?window={window_name}"

            # Brief delay before launching the table window to ensure bg/dmd
            # are initialized first, so table gets focus as the last window
            if window_name == 'table':
                time.sleep(0.5)

            self.launch_window(window_name, url, monitor, screen_id)

        print(f"[Chromium] Launched {len(self._processes)} browser windows")

    @staticmethod
    def _get_descendant_pids(pid):
        """Recursively find all descendant PIDs via /proc on Linux."""
        descendants = []
        try:
            with open(f'/proc/{pid}/task/{pid}/children') as f:
                for child_str in f.read().split():
                    child_pid = int(child_str)
                    descendants.append(child_pid)
                    descendants.extend(ChromiumManager._get_descendant_pids(child_pid))
        except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
            pass
        return descendants

    def _kill_process_tree(self, proc, window_name, force=False):
        """Kill a Chromium process and all its children (renderers, GPU, zygote)."""
        if platform.system() == "Windows":
            # taskkill /T kills the entire process tree, /F forces it
            try:
                subprocess.call(
                    ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception as e:
                print(f"[Chromium] taskkill failed for '{window_name}': {e}")
        else:
            # Walk /proc to find ALL descendants (regardless of process group)
            # then kill children first, parent last
            sig = signal.SIGKILL if force else signal.SIGTERM
            all_pids = self._get_descendant_pids(proc.pid)
            all_pids.append(proc.pid)
            print(f"[Chromium] Killing '{window_name}' tree: {all_pids} with signal {sig}")
            for pid in all_pids:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
                except Exception as e:
                    print(f"[Chromium] kill {pid} failed: {e}")

    def terminate_all(self):
        """Terminate all Chromium processes immediately."""
        print("[Chromium] Terminating all browser windows...")
        for window_name, proc, temp_dir, _ in self._processes:
            try:
                if proc.poll() is None:  # still running
                    # Use force=True (SIGKILL) directly - no need for graceful shutdown
                    self._kill_process_tree(proc, window_name, force=True)
            except Exception as e:
                print(f"[Chromium] Error terminating '{window_name}': {e}")

        # Wait for parent processes to be reaped
        for window_name, proc, temp_dir, _ in self._processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"[Chromium] Warning: '{window_name}' still not reaped")

        self._processes.clear()
        self._exit_event.set()
        print("[Chromium] All browser windows closed.")

    def wait_for_exit(self):
        """Block until all Chromium processes have exited.

        This replaces webview.start() as the main blocking call.
        Monitors all processes and returns when any one exits
        (which typically means the user closed a window or the app is shutting down).
        """
        if not self._processes:
            return

        def _monitor():
            """Watch for any process to exit, then terminate all."""
            while self._processes and not self._exit_event.is_set():
                for window_name, proc, temp_dir, _ in list(self._processes):
                    if proc.poll() is not None:
                        print(f"[Chromium] Window '{window_name}' exited (code {proc.returncode})")
                        # One window exited - shut everything down
                        self.terminate_all()
                        return
                self._exit_event.wait(timeout=0.5)

        monitor_thread = threading.Thread(target=_monitor, daemon=True)
        monitor_thread.start()

        # Block the main thread until exit is signaled
        self._exit_event.wait()

    def get_process(self, window_name):
        """Get the process for a specific window."""
        for name, proc, temp_dir, _ in self._processes:
            if name == window_name:
                return proc
        return None

    @property
    def is_running(self):
        """Check if any Chromium processes are still running."""
        return any(proc.poll() is None for _, proc, _, _ in self._processes)
