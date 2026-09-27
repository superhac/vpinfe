"""The Console in a real browser, read only once the page says it is drawn.

The page says so itself: `window.did_handshake`, and nothing on it marked
`aria-busy="true"` (`console/busy.py`). Every wait here is on that, or on the change an
action causes. Quiet is asked for only after the page has said it is drawn.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from tests.support.browser_session import BrowserSession

DRAWN = ("window.did_handshake === true"
         " && document.querySelector('[aria-busy=\"true\"]') === null")

QUIET_MS = 200
LISTEN_MS = 500

# For an action's `mark`: the newest element the server has drawn, for `newer`, and
# every notice on screen, for `notice`. What either finds afterwards is the action's.
MARK = ("window.__walkNewest = Math.max(0, ...Object.keys(mounted_app.elements).map(Number));"
        " document.querySelectorAll('.q-notification')"
        ".forEach(n => { n.dataset.walkSeen = '1'; })")


def newer(selector: str) -> str:
    """Something matching `selector` that the server drew since `MARK`."""
    return (f"[...document.querySelectorAll({json.dumps(selector)})]"
            ".some(el => Number(el.id.slice(1)) > window.__walkNewest)")


def notice(text: str) -> str:
    """A notice holding `text` said since `MARK`, as its words and classes, else null."""
    return ("(() => { const n = [...document.querySelectorAll('.q-notification')]"
            f".find(n => !n.dataset.walkSeen && n.innerText.includes({json.dumps(text)}));"
            " return n ? [n.innerText, n.className] : null; })()")


class Served(Protocol):
    def console_url(self, path: str = "/") -> str: ...

_POLL_S = 0.025
_LOAD_S = 90.0
_ACT_S = 30.0
_QUIET_CAP_S = 5.0

# Installed before any of the page's own scripts: when the page last changed, and when
# the server last said anything.
_WATCH = """(() => {
  const watch = window.__walk = {changed: performance.now(), said: performance.now()};
  new MutationObserver(() => { watch.changed = performance.now(); }).observe(
    document, {subtree: true, childList: true, attributes: true, characterData: true});
  let socket;
  Object.defineProperty(window, 'socket', {
    configurable: true,
    get: () => socket,
    set: (value) => {
      socket = value;
      value.prependAny(() => { watch.said = performance.now(); });
    },
  });
})()"""

_SHOWN = ("el => el.getClientRects().length > 0"
          " && getComputedStyle(el).visibility !== 'hidden'")
_ROWS = f"[...document.querySelectorAll('.console-section-row')].filter({_SHOWN})"
_WORK = f"[...document.querySelectorAll('.console-section-work')].find({_SHOWN})"
# Something a person reads or uses, outside the section's own heading and bar.
_HAS_CONTENT = f"""(() => {{
  const shown = {_SHOWN};
  const area = {_WORK};
  if (!area) return false;
  const aside = [...area.querySelectorAll('.console-panel-heading, .console-section-bar')];
  const own = el => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  return [...area.querySelectorAll('*')]
    .filter(el => !aside.some(a => a.contains(el)))
    .some(el => shown(el) && (own(el) || el.matches(
      'input,textarea,img,video,canvas,.q-field,.q-btn,.q-toggle,.q-checkbox')));
}})()"""
_PANE = "document.querySelector('.console-sections')"


class ConsoleWalk:
    """One browser tab on one instance's Console, or on any page NiceGUI serves."""

    def __init__(self, browser: BrowserSession, instance: Served) -> None:
        self.browser = browser
        self.instance = instance
        self.path = ""
        self._watching = False

    async def visit(self, path: str, *, listen: bool = False) -> list[str]:
        """Load `path` afresh and wait until it is drawn. What the browser logged from the
        navigation on - with `listen`, until the server has also said nothing for
        `LISTEN_MS`."""
        if not self._watching:
            await self.browser.send("Page.addScriptToEvaluateOnNewDocument",
                                     {"source": _WATCH})
            self._watching = True
        self.path = path
        await self.browser.evaluate("window.__walkLeft = true")
        self.browser.console.clear()
        await self.browser.navigate(self.instance.console_url(path))
        await self._until(f"!window.__walkLeft && {DRAWN}", _LOAD_S)
        await self.drawn()
        if listen:
            await self.listen()
        return list(self.browser.console)

    async def listen(self) -> None:
        """Until the server has said nothing for `LISTEN_MS`, or `_QUIET_CAP_S`."""
        await self._until(f"performance.now() - window.__walk.said >= {LISTEN_MS}",
                          _QUIET_CAP_S, required=False)

    async def answered(self, action: Callable[[], Awaitable[Any]]) -> None:
        """`action`, the server's answer to it, and then nothing more from the server
        for `LISTEN_MS`: the window a check that `action` changed nothing reads after."""
        await self.act(action, mark="window.__walkHeard = window.__walk.said",
                       until="window.__walk.said > window.__walkHeard")
        await self.listen()

    async def drawn(self, timeout: float = _ACT_S) -> None:
        """The page says it is drawn, then nothing changes for `QUIET_MS`, and it still
        says so. A page that never goes quiet is read after `_QUIET_CAP_S`."""
        for _attempt in range(10):
            await self._until(DRAWN, timeout)
            await self._until(f"performance.now() - window.__walk.changed >= {QUIET_MS}",
                              _QUIET_CAP_S, required=False)
            if await self.browser.evaluate(DRAWN):
                return
        raise AssertionError(f"{self.path}: never stayed drawn")

    async def act(self, action: Callable[[], Awaitable[Any]], *, until: str,
                  mark: str = "") -> None:
        """`action`, then `until` - a change the action causes, so false before it - then
        the page drawn again. `mark` runs first, to note what `until` compares against."""
        if mark:
            await self.browser.evaluate(mark)
        if await self.browser.evaluate(until):
            raise AssertionError(f"{self.path}: already true before acting: {until}")
        await action()
        await self._until(until, _ACT_S)
        await self.drawn()

    async def open_pane(self, action: Callable[[], Awaitable[Any]]) -> None:
        """`action`, which selects a subject, until the side pane is a new one."""
        await self.act(action, mark=f"window.__walkPane = {_PANE}",
                       until=f"(p => p !== null && p !== window.__walkPane)({_PANE})")

    async def sections(self) -> AsyncIterator[str]:
        """Open each row of the rail in turn, yielding its name once its section is
        drawn. A row that starts open closes on the click, and is opened again.

        Raises on a section that opened onto no content.
        """
        count = await self.browser.evaluate(f"{_ROWS}.length")
        for nth in range(count):
            name = await self.browser.evaluate(
                f"{_ROWS}[{nth}].innerText.trim().split('\\n')[0]")
            await self._press_row(nth)
            if not await self.browser.evaluate(f"!!{_WORK}"):
                await self._press_row(nth)
            if not await self.browser.evaluate(_HAS_CONTENT):
                raise AssertionError(f"{self.path}: {name!r} opened onto no content")
            yield name

    async def _press_row(self, nth: int) -> None:
        row = f"{_ROWS}[{nth}]"

        async def press() -> None:
            await self.browser.evaluate(
                "(row => (row.querySelector('.console-section-hit') || row).click())"
                "(window.__walkRow)")

        await self.act(press, mark=f"window.__walkRow = {row}",
                       until="!window.__walkRow.isConnected")

    async def _until(self, expression: str, timeout: float, *,
                     required: bool = True) -> Any:
        deadline = asyncio.get_running_loop().time() + timeout
        last = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                last = await self.browser.evaluate(expression)
            except RuntimeError:
                last = None     # the old document going away under the evaluate
            if last:
                return last
            await asyncio.sleep(_POLL_S)
        if required:
            raise TimeoutError(f"{self.path}: never true: {expression} (last={last!r})")
        return last


def clicked(browser: BrowserSession, expression: str) -> Callable[[], Awaitable[None]]:
    """An action that evaluates `expression`, which clicks something and says whether it
    found it."""
    async def click() -> None:
        if not await browser.evaluate(expression):
            raise AssertionError(f"nothing to click: {json.dumps(expression)[:120]}")
    return click
