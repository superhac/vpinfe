import json
import logging
import time
from typing import Any, Dict

from nicegui import ui


logger = logging.getLogger("vpinfe.manager.scroll")


def default_scroll_state() -> Dict[str, Any]:
    return {
        'winTop': 0,
        'elTop': 0,
        'anchor': '',
    }


async def capture_scroll_state(page_client: Any, selector: str, anchor_selector: str) -> Dict[str, Any]:
    started = time.perf_counter()
    if page_client is None:
        return default_scroll_state()

    try:
        with page_client:
            result = await ui.run_javascript('''
                (() => {
                    const selector = __SELECTOR__;
                    const elementTarget = document.querySelector(selector);
                    const winTop = window.scrollY || 0;
                    const elTop = elementTarget ? (elementTarget.scrollTop || 0) : 0;
                    return JSON.stringify({winTop, elTop, anchor: ''});
                })()
            '''
                .replace('__SELECTOR__', json.dumps(selector))
            )
        if not result:
            return default_scroll_state()
        parsed = json.loads(result)
        state = {
            'winTop': int(parsed.get('winTop') or 0),
            'elTop': int(parsed.get('elTop') or 0),
            'anchor': '',
        }
        elapsed = time.perf_counter() - started
        if elapsed >= 0.15:
            logger.info("Scroll capture slow: %.3fs selector=%s", elapsed, selector)
        return state
    except Exception:
        return default_scroll_state()


def restore_scroll_state(page_client: Any, state: Dict[str, Any], selector: str, anchor_selector: str) -> None:
    started = time.perf_counter()
    if page_client is None:
        return

    win_top = int((state or {}).get('winTop') or 0)
    el_top = int((state or {}).get('elTop') or 0)
    if win_top == 0 and el_top == 0:
        return
    state_json = json.dumps({'winTop': win_top, 'elTop': el_top})

    try:
        with page_client:
            ui.run_javascript('window.dispatchEvent(new Event("resize"));')
            ui.run_javascript('''
                var state = __STATE__;
                var selector = __SELECTOR__;
                var attempts = 0;
                var bindAndRestore = function() {
                    var elementTarget = document.querySelector(selector);
                    if (!elementTarget) {
                        if (attempts < 40) { attempts++; requestAnimationFrame(bindAndRestore); }
                        return;
                    }
                    window.scrollTo(0, Number(state.winTop || 0));
                    elementTarget.scrollTop = Number(state.elTop || 0);
                };
                requestAnimationFrame(bindAndRestore);
            '''
                .replace('__STATE__', state_json)
                .replace('__SELECTOR__', json.dumps(selector))
            )
        elapsed = time.perf_counter() - started
        if elapsed >= 0.15:
            logger.info("Scroll restore slow: %.3fs selector=%s", elapsed, selector)
    except RuntimeError:
        pass