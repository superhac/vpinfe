from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManagerPage:
    key: str
    label: str
    icon: str
    tooltip: str | None = None


NAV_PAGES: tuple[ManagerPage, ...] = (
    ManagerPage("tables", "Tables", "view_list"),
    ManagerPage("collections", "Collections", "collections_bookmark"),
    ManagerPage("media", "Media", "image"),
    ManagerPage("themes", "Themes", "palette"),
    ManagerPage("mobile", "Mobile Uploader", "smartphone"),
    ManagerPage("system", "System", "monitor_heart"),
    ManagerPage("vpinfe", "Configuration", "tune"),
    ManagerPage("vpx_config", "VPX Config", "settings_applications"),
    ManagerPage("vpinplay", "VPinPlay", "science"),
    ManagerPage("vpinplay_player", "VPinPlay Multi", "badge"),
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
    "vpinplay_player": "vpinplay_player",
    "vpx": "vpx_config",
    "vpinballx": "vpx_config",
}
