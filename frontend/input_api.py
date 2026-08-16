"""What the browser is told about input.

One method now - `get_bindings` - handing back each action's whole binding list, rather
than a gamepad map and a keyboard map separately. The split existed only because a stored
value could not say which device it came from; a `key:` or `pad:` selector says it, so the
two halves were one thing written down twice.

`get_joymapping` and `get_keymapping` still answer, projected out of the same lists, for
anything built against them.
"""

from __future__ import annotations

from common import config_schema, input_registry
from common.config_access import cfg_get

PAGING_TYPES = config_schema.PAGING_TYPES
PAGING_TYPE_ALIASES = config_schema.PAGING_TYPE_ALIASES
PAGING_TYPE_DEFAULT = config_schema.PAGING_TYPE_DEFAULT
PAGING_SIZE_DEFAULT = 10


def _parser(config):
    return getattr(config, "config", config)


def _raw(config, section, key) -> str | None:
    """Read exactly this key, or None. Deliberately not cfg_get: every legacy key of an
    action resolves to the same option, so cfg_get would answer `keytutorial` with
    whatever `joytutorial` holds."""
    try:
        parser = _parser(config)
        return parser.get(section, key) if parser.has_option(section, key) else None
    except Exception:
        return None


def get_bindings(config) -> dict[str, list[str]]:
    """Every action and what is bound to it, in order.

    A parser the store has migrated holds the list directly. One it has not - a config
    an older build wrote, or one a caller assembled - still holds a key per device, and
    those are assembled here rather than read as if they were already selectors.
    """
    out: dict[str, list[str]] = {}
    for action in input_registry.actions():
        current = _raw(config, input_registry.SECTION, action.name)
        if current is not None:
            out[action.name] = [p.strip() for p in current.split(",") if p.strip()]
            continue
        found: list[str] = []
        for old in action.legacy:
            value = _raw(config, "Input", old)
            if value is not None:
                found += input_registry.binding_for_legacy(old, value)
        out[action.name] = found or list(action.bindings)
    return out


def get_paging_config(config):
    """Return (paging_type, page_size), normalized to sane values."""
    paging_type = cfg_get(config, input_registry.SECTION, "paging_type",
                          PAGING_TYPE_DEFAULT).strip().lower()
    paging_type = PAGING_TYPE_ALIASES.get(paging_type, paging_type)
    if paging_type not in PAGING_TYPES:
        paging_type = PAGING_TYPE_DEFAULT
    try:
        page_size = int(cfg_get(config, input_registry.SECTION, "paging_size",
                                str(PAGING_SIZE_DEFAULT)).strip())
    except (TypeError, ValueError):
        page_size = PAGING_SIZE_DEFAULT
    if page_size < 1:
        page_size = PAGING_SIZE_DEFAULT
    return paging_type, page_size


def get_joymapping(config):
    """The gamepad half, under the key names it used to have. Projected, never stored."""
    bindings = get_bindings(config)
    return {action.legacy_joy_key:
            ",".join(input_registry.pad_buttons_in(bindings[action.name]))
            for action in input_registry.actions() if action.legacy_joy_key}


def get_keymapping(config):
    """The keyboard half, under the key names it used to have."""
    bindings = get_bindings(config)
    return {action.legacy_key_key:
            ",".join(input_registry.keys_in(bindings[action.name]))
            for action in input_registry.actions() if action.legacy_key_key}


def set_button_mapping(iniconfig, action_name, button_index):
    """Bind a gamepad button to an action, keeping everything else bound to it.

    Accepts an action name or any `[Input]` key that used to be one, so the gamepad
    binding page keeps working while it is repointed.
    """
    name = input_registry.action_for_legacy_key(action_name)
    if not name:
        return {"success": False, "message": f"Invalid action: {action_name}"}
    try:
        parser = _parser(iniconfig)
        if not parser.has_section(input_registry.SECTION):
            parser.add_section(input_registry.SECTION)
        current = get_bindings(iniconfig)[name]
        # Replace this action's gamepad binding; leave its keys and anything richer.
        kept = [b for b in current if not b.startswith(input_registry.PAD_PREFIX)]
        kept.append(f"{input_registry.PAD_PREFIX}0/button:{button_index}")
        parser.set(input_registry.SECTION, name, ",".join(kept))
        iniconfig.save()
        return {"success": True, "message": f"Mapped {name} to button {button_index}"}
    except Exception as exc:
        return {"success": False, "message": f"Error saving mapping: {exc}"}
