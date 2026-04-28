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


def get_joymapping(config):
    return {key: config["Input"].get(key, "0") for key in JOY_MAPPING_KEYS}


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
