"""The list of pages the shell builds its navigation from."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManagerPage:
    key: str
    label: str
    icon: str
    tooltip: str | None = None


NAV_PAGES: tuple[ManagerPage, ...] = (
    ManagerPage("games", "Tables", "view_list"),
    ManagerPage("collections", "Collections", "collections_bookmark"),
    ManagerPage("media", "Media", "image"),
    ManagerPage("themes", "Themes", "palette"),
    ManagerPage("mobile", "Mobile Uploader", "smartphone"),
    ManagerPage("system", "System", "monitor_heart"),
    ManagerPage("vpinfe", "Configuration", "tune"),
    ManagerPage("vpx_config", "VPX Config", "settings_applications"),
    ManagerPage("vpx_plugins", "VPX-Plugins", "extension"),
    ManagerPage("vpinplay", "VPinPlay", "science"),
    ManagerPage("vpinplay_account", "VPinPlay Multi", "badge"),
    ManagerPage("logs", "Logs", "article"),
)


PAGE_ALIASES = {
    page.key: page.key for page in NAV_PAGES
} | {
    "vpinfe_config": "vpinfe",
    "configuration": "vpinfe",
    "config": "vpinfe",
    "log": "logs",
    "logs": "logs",
    "vpinplay": "vpinplay",
    "vpinplay_config": "vpinplay",
    # Shipped in 2.x, so it can be sitting in a user's manager-ui-state.json.
    "vpinplay_player": "vpinplay_account",
    "vpx": "vpx_config",
    "vpinballx": "vpx_config",
    "plugins": "vpx_plugins",
    "vpx-plugins": "vpx_plugins",
}
