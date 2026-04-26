from __future__ import annotations

from common.config_access import DisplayConfig, NetworkConfig, SettingsConfig, VPinPlayConfig
from common.table_metadata import is_truthy


def get_mainmenu_config(iniconfig):
    try:
        iniconfig.config.read(iniconfig.configfilepath)
    except Exception:
        raise
    return {
        "hideQuitButton": SettingsConfig.from_config(iniconfig).hide_quit_button,
    }


def get_splashscreen_enabled(config):
    return "true" if SettingsConfig.from_config(config).splashscreen else "false"


def set_audio_muted(api, muted):
    muted_flag = muted if isinstance(muted, bool) else is_truthy(muted)
    api._iniConfig.config.set("Settings", "muteaudio", "true" if muted_flag else "false")
    api._iniConfig.save()
    api.send_event_all_windows_incself({
        "type": "AudioMuteChanged",
        "muted": muted_flag,
    })
    return muted_flag


def get_vpinplay_endpoint(config):
    return VPinPlayConfig.from_config(config).api_endpoint


def get_table_orientation(config):
    return DisplayConfig.from_config(config).table_orientation


def get_table_rotation(config):
    return DisplayConfig.from_config(config).table_rotation


def get_cab_mode(config):
    return DisplayConfig.from_config(config).cab_mode


def get_theme_assets_port(config):
    return NetworkConfig.from_config(config).theme_assets_port
