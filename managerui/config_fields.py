from __future__ import annotations

INPUT_MAPPING_ACTION_ORDER = [
    "left",
    "right",
    "up",
    "down",
    "pageup",
    "pagedown",
    "select",
    "menu",
    "back",
    "exit",
    "collectionmenu",
    "tutorial",
]

# Which settings render as a checkbox. Derived from the schema rather than listed here:
# the hand-written list was still spelled the way the ini spelled it, so after the move to
# snake_case twelve of its fifteen entries matched nothing and those settings drew as text
# boxes. config_schema already knows a setting's type, and it is the only thing that has
# to be right.
def _checkbox_fields() -> frozenset[tuple[str, str]]:
    from common import config_schema
    return frozenset((option.section, option.key)
                     for option in config_schema.options() if option.type == "bool")


CHECKBOX_FIELDS = _checkbox_fields()


def is_checkbox_field(section: str, key: str) -> bool:
    """Whether this setting draws as a checkbox, under any spelling it has had."""
    from common import config_schema
    return config_schema.locate(section, key) in CHECKBOX_FIELDS


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
