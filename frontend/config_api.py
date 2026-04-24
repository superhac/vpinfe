from __future__ import annotations

from common.table_metadata import is_truthy


def get_mainmenu_config(iniconfig):
    try:
        iniconfig.config.read(iniconfig.configfilepath)
    except Exception:
        raise
    return {
        "hideQuitButton": iniconfig.config.getboolean("Settings", "MMhideQuitButton", fallback=False),
    }


def get_splashscreen_enabled(config):
    return config["Settings"].get("splashscreen", "true")


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
    return str(config["vpinplay"].get("apiendpoint", "")).strip()


def get_table_orientation(config):
    return config["Displays"].get("tableorientation", "landscape")


def get_table_rotation(config):
    raw = str(config["Displays"].get("tablerotation", "0")).strip()
    if raw == "":
        return 0
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return 0


def get_cab_mode(config):
    raw = str(config["Displays"].get(
        "cabmode",
        config["Settings"].get("cabmode", "false"),
    )).strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_theme_assets_port(config):
    return int(config["Network"].get("themeassetsport", "8000"))
