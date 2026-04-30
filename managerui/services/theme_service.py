from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common.iniconfig import IniConfig
from common.themes import ThemeRegistry

from managerui.paths import THEMES_DIR, VPINFE_INI_PATH


def get_active_theme() -> str:
    try:
        config = IniConfig(str(VPINFE_INI_PATH))
        theme_name = config.config.get("Settings", "theme", fallback="Revolution").strip()
        return theme_name or "Revolution"
    except Exception:
        return "Revolution"


def set_active_theme(theme_key: str) -> None:
    config = IniConfig(str(VPINFE_INI_PATH))
    config.config.set("Settings", "theme", theme_key)
    with open(VPINFE_INI_PATH, "w") as handle:
        config.config.write(handle)


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
            option["options"] = _normalize_select_options(raw_option.get("options"))
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

    values: dict[str, Any] = {}
    for option in schema["options"]:
        key = option["key"]
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

    schema_path = theme_dir / "theme.json"
    existing_schema = _read_json_object(schema_path)
    if not existing_schema or not isinstance(existing_schema.get("options"), list):
        raise ValueError(f'Theme "{theme_key}" has an invalid theme.json file.')

    existing_options = existing_schema["options"]
    schema_options_by_key = {option["key"]: option for option in schema["options"]}
    for raw_option in existing_options:
        if not isinstance(raw_option, dict):
            continue
        key = str(raw_option.get("key") or raw_option.get("id") or "").strip()
        if not key or key not in values or key not in schema_options_by_key:
            continue
        coerced_value = _coerce_theme_option_value(schema_options_by_key[key], values[key])
        raw_option["value"] = coerced_value

    schema_path.write_text(json.dumps(existing_schema, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return schema_path
