from __future__ import annotations

import ipaddress
import socket
from io import BytesIO

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


def _managerui_remote_urls(config) -> list[str]:
    port = NetworkConfig.from_config(config).manager_ui_port
    hostname = socket.gethostname().strip()
    urls: list[str] = []
    seen_hosts: set[str] = set()

    def is_usable_ipv4(value: str) -> bool:
        try:
            ip = ipaddress.ip_address((value or "").strip())
        except ValueError:
            return False
        return ip.version == 4 and not ip.is_loopback and not ip.is_unspecified and not ip.is_link_local

    def detect_primary_ipv4() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                candidate = str(sock.getsockname()[0]).strip()
                return candidate if is_usable_ipv4(candidate) else ""
        except Exception:
            return ""

    def add_host(host: str) -> None:
        normalized = (host or "").strip()
        if not normalized:
            return
        key = normalized.lower()
        if key in seen_hosts:
            return
        seen_hosts.add(key)
        urls.append(f"http://{normalized}:{port}/remote")

    primary_ip = detect_primary_ipv4()
    if primary_ip:
        add_host(primary_ip)

    if hostname and hostname.lower() not in {"localhost", "ip6-localhost"}:
        add_host(hostname)

        try:
            for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, socket.AF_INET):
                if family != socket.AF_INET:
                    continue
                ip = str(sockaddr[0]).strip()
                if not is_usable_ipv4(ip):
                    continue
                add_host(ip)
        except Exception:
            pass

    add_host("localhost")
    return urls


def _build_remote_qr_svg(url: str) -> str:
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except Exception:
        return ""

    stream = BytesIO()
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    image.save(stream)
    return stream.getvalue().decode("utf-8")


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


def get_managerui_remote_link(config):
    urls = _managerui_remote_urls(config)
    preferred_url = next(
        (url for url in urls if url.startswith("http://") and url.split("://", 1)[1].split(":", 1)[0].count(".") == 3),
        next((url for url in urls if "://localhost:" not in url.lower()), urls[0] if urls else ""),
    )
    return {
        "url": preferred_url,
        "urls": urls,
        "qr_svg": _build_remote_qr_svg(preferred_url) if preferred_url else "",
    }
