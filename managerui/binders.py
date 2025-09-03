from __future__ import annotations
from typing import Tuple, List, Optional, Callable

# Centralized bind helpers for NiceGUI widgets <-> IniStore

def _bind_input(store, widget, sec_opt: Tuple[str, str]):
    """Bind a text-like input: widget.value (string) <-> store (string)."""
    sec, opt = sec_opt

    def push(val: str):
        widget.value = '' if val is None else str(val)

    push(store.get(sec, opt))
    store.on_change(sec, opt, push)

    # Support both generic value change and model-value updates
    handler = lambda e=None: store.set(sec, opt, '' if widget.value is None else str(widget.value))
    try:
        widget.on_value_change(handler)
    except Exception:
        pass
    widget.on('update:model-value', handler)


def _bind_select(store, sel, sec_opt: Tuple[str, str]):
    """Bind a NiceGUI select: read/write string; uses update:model-value."""
    sec, opt = sec_opt

    def push(val: str):
        sel.value = val

    push(store.get(sec, opt))
    store.on_change(sec, opt, push)
    sel.on('update:model-value', lambda e: store.set(sec, opt, sel.value or ''))


def _bind_indexed_select(store, sel, sec_opt: Tuple[str, str], options: List[str]):
    """Select with human labels that saves the index (as string) to INI."""
    sec, opt = sec_opt
    sel.options = options

    def push(index_str: str):
        try:
            idx = int(index_str)
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(options):
            idx = 0
        sel.value = options[idx]

    push(store.get(sec, opt))
    store.on_change(sec, opt, push)
    sel.on('update:model-value', lambda e: store.set(sec, opt, str(options.index(sel.value)) if sel.value in options else '0'))


def _bind_switch(store, sw, sec_opt: Tuple[str, str], on_toggle: Optional[Callable[[bool], None]] = None):
    """Switch visual; store as '1'/'0' (string). Optionally call on_toggle(bool)."""
    sec, opt = sec_opt

    def push(val: str):
        on = str(val).strip().lower() in ('1', 'true', 'on', 'yes')
        sw.value = on
        if on_toggle:
            on_toggle(on)

    push(store.get(sec, opt))
    store.on_change(sec, opt, push)

    handler = lambda e=None: (store.set(sec, opt, '1' if bool(sw.value) else '0'), on_toggle and on_toggle(bool(sw.value)))
    try:
        sw.on_value_change(handler)
    except Exception:
        pass
    sw.on('update:model-value', handler)

