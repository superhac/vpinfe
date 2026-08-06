from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common.config_store import ConfigStore
from common import theme_options
from common.online.themes import ThemeRegistry

from managerui.paths import THEMES_DIR, VPINFE_INI_PATH
from common.config_access import cfg_get, cfg_set


def get_active_theme() -> str:
    try:
        config = ConfigStore(str(VPINFE_INI_PATH))
        theme_name = cfg_get(config, "general", "theme", "Revolution").strip()
        return theme_name or "Revolution"
    except Exception:
        return "Revolution"


def set_active_theme(theme_key: str) -> None:
    config = ConfigStore(str(VPINFE_INI_PATH))
    cfg_set(config, "general", "theme", theme_key)
    config.save()


def load_registry() -> ThemeRegistry:
    registry = ThemeRegistry()
    registry.load_registry()
    registry.load_theme_manifests()
    return registry


def install_theme(registry: ThemeRegistry, theme_key: str) -> None:
    registry.install_theme(theme_key, force=True)


def delete_theme(registry: ThemeRegistry, theme_key: str) -> None:
    registry.delete_theme(theme_key)


def get_installed_theme_dir(theme_key: str, registry: ThemeRegistry | None = None) -> Path | None:
    if registry is not None:
        try:
            folder_name = registry.get_installed_folder(theme_key)
        except Exception:
            folder_name = None
        if folder_name:
            theme_dir = THEMES_DIR / folder_name
            if theme_dir.is_dir():
                return theme_dir

    theme_dir = THEMES_DIR / str(theme_key or "").strip()
    return theme_dir if theme_dir.is_dir() else None


def _folder_for(theme_key: str, registry: ThemeRegistry | None = None) -> str:
    """The folder a theme is installed under - what its options file is keyed by.

    Falls back to the key, which is what a registry install renames the folder to.
    """
    theme_dir = get_installed_theme_dir(theme_key, registry)
    return theme_dir.name if theme_dir is not None else str(theme_key or "").strip()


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _normalize_option_type(raw_value: Any) -> str:
    normalized = str(raw_value or "text").strip().lower()
    return {
        "str": "text",
        "string": "text",
        "integer": "number",
        "int": "number",
        "float": "number",
        "bool": "boolean",
        "checkbox": "boolean",
        "choice": "select",
        "dropdown": "select",
        "multiline": "textarea",
        "object": "json",
    }.get(normalized, normalized or "text")


def _normalize_select_options(raw_options: Any) -> list[Any]:
    if not isinstance(raw_options, list):
        return []

    normalized: list[Any] = []
    for item in raw_options:
        if isinstance(item, dict):
            label = str(item.get("label", "") or "").strip()
            value = item.get("value")
            if value in ("", None):
                continue
            normalized.append({
                "label": label or str(value),
                "value": value,
            })
        elif item not in ("", None):
            normalized.append(item)
    return normalized


def _dynamic_select_options(source: str) -> list[dict[str, Any]] | None:
    """Options a theme cannot know ahead of time, discovered from the library.

    "wheelsets" is every wheel set folder across the games plus the virtual
    "logo" set. The leading Default entry saves as "" - no set, plain wheels.
    """
    if source != "wheelsets":
        return None
    from common.config_access import SettingsConfig
    from common.media_specs import list_media_sets

    names: list[str] = []
    try:
        config = ConfigStore(str(VPINFE_INI_PATH))
        root = SettingsConfig.from_config(config).game_root_dir
        if root:
            names = list_media_sets(root, "wheel")
    except Exception:
        pass
    return ([{"label": "Default", "value": ""}]
            + [{"label": name, "value": name} for name in names])


def load_theme_option_schema(theme_key: str, registry: ThemeRegistry | None = None) -> dict[str, Any] | None:
    theme_dir = get_installed_theme_dir(theme_key, registry)
    if theme_dir is None:
        return None

    schema = _read_json_object(theme_dir / "theme.json")
    if not schema:
        return None

    raw_options = schema.get("options")
    if not isinstance(raw_options, list):
        return None

    normalized_options: list[dict[str, Any]] = []
    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            continue
        key = str(raw_option.get("key") or raw_option.get("id") or "").strip()
        if not key:
            continue

        option_type = _normalize_option_type(raw_option.get("type"))
        option = dict(raw_option)
        option["key"] = key
        option["name"] = str(raw_option.get("name") or raw_option.get("label") or key).strip() or key
        option["description"] = str(raw_option.get("description") or "").strip()
        option["type"] = option_type
        if option_type == "select":
            dynamic = _dynamic_select_options(str(raw_option.get("source") or "").strip().lower())
            option["options"] = (dynamic if dynamic is not None
                                 else _normalize_select_options(raw_option.get("options")))
        normalized_options.append(option)

    if not normalized_options:
        return None

    return {
        "title": str(schema.get("title") or "").strip(),
        "description": str(schema.get("description") or "").strip(),
        "options": normalized_options,
    }


def get_theme_option_values(theme_key: str, registry: ThemeRegistry | None = None) -> dict[str, Any]:
    schema = load_theme_option_schema(theme_key, registry)
    if schema is None:
        return {}

    # The author's schema supplies the default; the user's own file supplies what they
    # chose. A `value` still sitting in the package is a pre-3.0 leftover and is read
    # only until the migration lifts it out.
    chosen = theme_options.load(_folder_for(theme_key, registry))
    values: dict[str, Any] = {}
    for option in schema["options"]:
        key = option["key"]
        if key in chosen:
            values[key] = chosen[key]
            continue
        current_value = option.get("value")
        if current_value is None and "default" in option:
            current_value = option.get("default")
        values[key] = current_value

    return values


def _coerce_theme_option_value(option: dict[str, Any], raw_value: Any) -> Any:
    option_type = option.get("type", "text")
    if option_type == "boolean":
        if isinstance(raw_value, bool):
            return raw_value
        return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}

    if option_type == "number":
        if raw_value in ("", None):
            return option.get("default") if "default" in option else None
        try:
            number = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{option["name"]} expects a number.') from exc
        return int(number) if number.is_integer() else number

    if option_type == "json":
        if raw_value in ("", None):
            return option.get("default", {})
        if isinstance(raw_value, (dict, list, int, float, bool)):
            return raw_value
        try:
            return json.loads(str(raw_value))
        except json.JSONDecodeError as exc:
            raise ValueError(f'{option["name"]} expects valid JSON.') from exc

    if option_type == "select":
        allowed_values = []
        for item in option.get("options", []):
            if isinstance(item, dict):
                allowed_values.append(item.get("value"))
            else:
                allowed_values.append(item)
        if raw_value in ("", None):
            return option.get("default") if "default" in option else ""
        if allowed_values and raw_value not in allowed_values:
            raise ValueError(f'{option["name"]} must be one of the configured options.')
        return raw_value

    if raw_value is None:
        return option.get("default") if "default" in option else ""
    return str(raw_value)


def save_theme_option_values(
    theme_key: str,
    values: dict[str, Any],
    registry: ThemeRegistry | None = None,
) -> Path:
    if not isinstance(values, dict):
        raise ValueError("Theme option values must be a mapping.")

    schema = load_theme_option_schema(theme_key, registry)
    theme_dir = get_installed_theme_dir(theme_key, registry)
    if schema is None or theme_dir is None:
        raise ValueError(f'Theme "{theme_key}" does not expose configurable options.')

    # Written outside the theme, because an update deletes the package: values saved
    # into it were reset by the next update, every time, with no backup and no warning.
    schema_options_by_key = {option["key"]: option for option in schema["options"]}
    keep = dict(theme_options.load(_folder_for(theme_key, registry)))
    for key, raw_value in values.items():
        if key in schema_options_by_key:
            keep[key] = _coerce_theme_option_value(schema_options_by_key[key], raw_value)

    return theme_options.save(_folder_for(theme_key, registry), keep)
