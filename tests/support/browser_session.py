"""Drive a real Chromium over the DevTools protocol, with no new dependencies.

`websockets` is already here for the bridge and `get_chromium_path` already finds the
browser VPinFE ships, so a render test costs a fixture theme and this file rather than a
toolchain. Puppeteer and Playwright would each add an ecosystem to a repo that has no
JavaScript tooling at all.

Only what a smoke test needs: open a page, wait for the DOM to say something, read
attributes back, press a key, and report every request that did not return 200. Anything
more belongs in a real driver, not here.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import tempfile
import urllib.request
from contextlib import suppress
from dataclasses import dataclass, field
from functools import lru_cache

import websockets


def free_port() -> int:
    """A port nothing holds. Probed the way the instance binds, not on loopback.

    `http_bind` defaults to 0.0.0.0, so a port free on 127.0.0.1 can still be taken on
    another interface and the instance then fails with "address already in use". Asking
    for the same wildcard the instance asks for removes that half of it. The window
    between this close and the instance's bind is still a race, and still open.
    """
    with socket.socket() as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


def _installed_browser() -> str | None:
    with suppress(Exception):
        from frontend.chromium_manager import get_chromium_path

        found = get_chromium_path()
        path = getattr(found, "path", None)
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


@lru_cache(maxsize=1)
def chromium_path() -> str | None:
    """A browser this machine can actually be driven through, or None.

    Answers by launching one and connecting, not by finding a file: a browser that is
    installed and cannot be driven makes every test using it fail rather than skip.
    Cached, so the cost is one launch per run.
    """
    path = _installed_browser()
    if path is None:
        return None

    async def drivable() -> bool:
        with suppress(Exception):
            async with BrowserSession(path) as session:
                # Navigating, not just connecting: a browser can do the second and
                # not the first.
                await session.navigate("about:blank")
                return True
        return False

    return path if asyncio.run(drivable()) else None


@dataclass
class PageResult:
    body: dict = field(default_factory=dict)
    console: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)


class BrowserSession:
    """One headless Chromium, one tab. Use as an async context manager."""

    def __init__(self, binary: str, timeout: float = 30.0):
        self.binary = binary
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._profile: str | None = None
        self._ws = None
        self._next_id = 0
        self._responses: dict[int, dict] = {}
        self.console: list[str] = []
        self.failed_requests: list[str] = []
        self._status: dict[str, int] = {}

    async def __aenter__(self) -> BrowserSession:
        port = free_port()
        self._profile = tempfile.mkdtemp(prefix="vpinfe-smoke-")
        self._proc = subprocess.Popen(
            [self.binary, "--headless=new", f"--remote-debugging-port={port}",
             f"--user-data-dir={self._profile}", "--no-first-run",
             "--no-default-browser-check", "--disable-gpu", "--disable-dev-shm-usage",
             # A CI runner has no user namespaces to build a sandbox in, so Chrome exits
             # immediately without this. Safe here: the only pages it opens are ours, on
             # loopback, in a profile thrown away afterwards.
             "--no-sandbox", "--disable-setuid-sandbox",
             "--window-size=1280,720", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

        endpoint = await self._page_endpoint(port)
        # 30s, not the 10s default: a cold CI runner can take longer than that to
        # get Chrome to the point of answering a WebSocket upgrade, and the failure
        # reads as a render regression rather than as a slow machine.
        self._ws = await websockets.connect(endpoint, max_size=None, open_timeout=30)
        asyncio.create_task(self._pump())
        for domain in ("Page", "Runtime", "Network", "Log"):
            await self.send(f"{domain}.enable")
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._ws is not None:
            with suppress(Exception):
                await self._ws.close()
        if self._proc is not None:
            self._proc.terminate()
            with suppress(Exception):
                self._proc.wait(timeout=10)
        if self._profile:
            shutil.rmtree(self._profile, ignore_errors=True)

    async def _page_endpoint(self, port: int) -> str:
        """The tab's own socket, not the browser's.

        Page, Network and Log are page domains: on the browser-level endpoint they do not
        exist, and `Page.enable` comes back "wasn't found" rather than doing nothing.
        """
        deadline = asyncio.get_event_loop().time() + self.timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/json/list", timeout=1) as handle:
                    targets = json.load(handle)
                for target in targets:
                    if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                        return target["webSocketDebuggerUrl"]
            except Exception:
                pass
            if self._proc.poll() is not None:
                break
            await asyncio.sleep(0.1)
        raise RuntimeError(
            "Chromium never opened a page to attach to. It exited "
            f"{self._proc.returncode}; stderr:\n{self._stderr()}")

    def _stderr(self) -> str:
        """Why the browser gave up, which a timeout on its own never says."""
        if self._proc is None or self._proc.stderr is None:
            return "(none)"
        with suppress(Exception):
            return (self._proc.stderr.read() or "(silent)")[-2000:]
        return "(unreadable)"

    async def _pump(self) -> None:
        """Read every frame once, so replies and events cannot consume each other."""
        with suppress(Exception):
            async for raw in self._ws:
                message = json.loads(raw)
                if "id" in message:
                    self._responses[message["id"]] = message
                    continue
                self._on_event(message.get("method", ""), message.get("params") or {})

    def _on_event(self, method: str, params: dict) -> None:
        if method == "Runtime.consoleAPICalled":
            text = " ".join(str(a.get("value", a.get("description", "")))
                            for a in params.get("args", []))
            self.console.append(f"{params.get('type', 'log')}: {text}")
        elif method == "Log.entryAdded":
            entry = params.get("entry") or {}
            if entry.get("level") in ("error", "warning"):
                self.console.append(f"{entry['level']}: {entry.get('text', '')}")
        elif method == "Network.responseReceived":
            response = params.get("response") or {}
            status, url = response.get("status", 0), response.get("url", "")
            self._status[url] = status
            # The browser asks for a favicon on its own. A theme never requests one, so
            # counting it would mean every page "failed" and the assertion would have to
            # be loosened - which is how a real 404 gets waved through.
            if status >= 400 and not url.endswith("/favicon.ico"):
                self.failed_requests.append(f"{status} {url}")
        elif method == "Network.loadingFailed":
            # A request that never got a response at all - a dead port, a blocked scheme.
            if not params.get("canceled"):
                self.failed_requests.append(
                    f"failed {params.get('errorText', '?')} ({params.get('type', '?')})")

    async def send(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        message_id = self._next_id
        await self._ws.send(json.dumps(
            {"id": message_id, "method": method, "params": params or {}}))
        deadline = asyncio.get_event_loop().time() + self.timeout
        while asyncio.get_event_loop().time() < deadline:
            if message_id in self._responses:
                reply = self._responses.pop(message_id)
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result") or {}
            await asyncio.sleep(0.02)
        raise TimeoutError(f"{method} did not answer")

    async def navigate(self, url: str) -> None:
        await self.send("Page.navigate", {"url": url})

    async def evaluate(self, expression: str):
        result = await self.send("Runtime.evaluate", {
            "expression": expression, "awaitPromise": True, "returnByValue": True})
        if result.get("exceptionDetails"):
            raise RuntimeError(str(result["exceptionDetails"]))
        return (result.get("result") or {}).get("value")

    async def wait_for(self, expression: str, timeout: float = 20.0):
        """Poll a JavaScript expression until it is truthy. Returns its value."""
        deadline = asyncio.get_event_loop().time() + timeout
        last = None
        while asyncio.get_event_loop().time() < deadline:
            with suppress(Exception):
                last = await self.evaluate(expression)
                if last:
                    return last
            await asyncio.sleep(0.1)
        raise TimeoutError(f"never became truthy: {expression} (last={last!r})")

    async def click(self, selector: str, *, nth: int = 0) -> None:
        """Click something the way a finger does, at its own coordinates.

        A real mouse event, not `element.click()`. Quasar builds several of its controls
        - a select, a menu item - out of listeners that a synthetic click never reaches,
        so a test that drives them with `.click()` reports success and changes nothing.
        """
        where = await self.evaluate(
            "(() => {"
            f" const found = document.querySelectorAll({json.dumps(selector)});"
            f" const el = found[{int(nth)}]; if (!el) return null;"
            " el.scrollIntoView({block: 'center'});"
            " const box = el.getBoundingClientRect();"
            " if (!box.width || !box.height) return null;"
            " return {x: box.left + box.width / 2, y: box.top + box.height / 2};"
            " })()")
        if not where:
            raise AssertionError(f"nothing to click at {selector!r}[{nth}]")
        for event in ("mousePressed", "mouseReleased"):
            await self.send("Input.dispatchMouseEvent",
                            {"type": event, "x": where["x"], "y": where["y"],
                             "button": "left", "clickCount": 1})

    async def press(self, key: str, code: str) -> None:
        for event in ("keyDown", "keyUp"):
            await self.send("Input.dispatchKeyEvent",
                            {"type": event, "key": key, "code": code,
                             "windowsVirtualKeyCode": 0})

    async def body_data(self) -> dict:
        return await self.evaluate("Object.assign({}, document.body.dataset)") or {}

    def status_of(self, url_fragment: str) -> int | None:
        for url, status in self._status.items():
            if url_fragment in url:
                return status
        return None
