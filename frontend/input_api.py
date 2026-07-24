from __future__ import annotations


JOY_MAPPING_KEYS = [
    "joyleft",
    "joyright",
    "joyup",
    "joydown",
    "joypageup",
    "joypagedown",
    "joyselect",
    "joymenu",
    "joyback",
    "joytutorial",
    "joyexit",
    "joycollectionmenu",
]

KEY_MAPPING_DEFAULTS = {
    "keyleft": "ArrowLeft,ShiftLeft",
    "keyright": "ArrowRight,ShiftRight",
    "keyup": "ArrowUp",
    "keydown": "ArrowDown",
    "keypageup": "PageUp",
    "keypagedown": "PageDown",
    "keyselect": "Enter",
    "keymenu": "m",
    "keyback": "b",
    "keytutorial": "t",
    "keyexit": "Escape,q",
    "keycollectionmenu": "c",
}


PAGING_TYPES = ("alpha", "numeric")
PAGING_TYPE_DEFAULT = "alpha"
PAGING_SIZE_DEFAULT = 10


def get_joymapping(config):
    return {key: config["Input"].get(key, "0") for key in JOY_MAPPING_KEYS}


def get_paging_config(config):
    """Return (paging_type, page_size) from [Input], normalized to sane values."""
    paging_type = str(config["Input"].get("pagingtype", PAGING_TYPE_DEFAULT) or "").strip().lower()
    if paging_type not in PAGING_TYPES:
        paging_type = PAGING_TYPE_DEFAULT
    try:
        page_size = int(str(config["Input"].get("pagingsize", PAGING_SIZE_DEFAULT)).strip())
    except (TypeError, ValueError):
        page_size = PAGING_SIZE_DEFAULT
    if page_size < 1:
        page_size = PAGING_SIZE_DEFAULT
    return paging_type, page_size


def get_keymapping(config):
    return {key: config["Input"].get(key, default) for key, default in KEY_MAPPING_DEFAULTS.items()}


def set_button_mapping(iniconfig, button_name, button_index):
    if button_name not in JOY_MAPPING_KEYS:
        return {"success": False, "message": f"Invalid button name: {button_name}"}
    try:
        iniconfig.config.set("Input", button_name, str(button_index))
        iniconfig.save()
        return {"success": True, "message": f"Mapped {button_name} to button {button_index}"}
    except Exception as exc:
        return {"success": False, "message": f"Error saving mapping: {exc}"}
