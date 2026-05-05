from __future__ import annotations


INPUT_MAPPING_ACTION_ORDER = [
    "left",
    "right",
    "up",
    "down",
    "select",
    "menu",
    "back",
    "exit",
    "collectionmenu",
    "tutorial",
]

CHECKBOX_FIELDS = {
    ("Settings", "autoupdatemediaonstartup"),
    ("Settings", "splashscreen"),
    ("Settings", "muteaudio"),
    ("Settings", "mmhidequitbutton"),
    ("Settings", "globaltableinioverrideenabled"),
    ("Settings", "vpxlogdeleteonstart"),
    ("Displays", "cabmode"),
    ("Logger", "console"),
    ("DOF", "enabledof"),
    ("libdmdutil", "enabled"),
    ("libdmdutil", "pin2dmdenabled"),
    ("Mobile", "renamemasktodefaultini"),
    ("vpinplay", "synconexit"),
}


def is_checkbox_field(section: str, key: str) -> bool:
    return (section, key) in CHECKBOX_FIELDS


def sort_input_mapping_keys(keys: list[str], prefix: str) -> list[str]:
    ordered_keys: list[str] = []
    present_keys = set(keys)

    for action in INPUT_MAPPING_ACTION_ORDER:
        mapping_key = f"{prefix}{action}"
        if mapping_key in present_keys:
            ordered_keys.append(mapping_key)

    for key in keys:
        if key not in ordered_keys:
            ordered_keys.append(key)

    return ordered_keys
