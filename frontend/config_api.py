"""The settings a theme is allowed to read, answered one question at a time."""

from __future__ import annotations

import socket
from io import BytesIO
from typing import TYPE_CHECKING, Any

from common.config_access import (
    ConfigSource,
    DisplayConfig,
    MediaConfig,
    NetworkConfig,
    SettingsConfig,
    VPinPlayConfig,
    cfg_set,
)
from common.host.addresses import usable_ipv4
from common.values import is_truthy

if TYPE_CHECKING:
    from frontend.api import API


def get_mainmenu_config(iniconfig: ConfigSource) -> dict[str, bool]:
    # No re-read: the store holds the live config and every write goes through save().
    # This used to reload the ini here, which under JSON meant handing a configparser a
    # JSON file - it raised on every menu open, the caller fell back to its default, and
    # hide_quit_button silently did nothing.
    return {
        "hideQuitButton": SettingsConfig.from_config(iniconfig).hide_quit_button,
    }


def _managerui_remote_urls(config: ConfigSource) -> list[str]:
    port = NetworkConfig.from_config(config).http_port
    hostname = socket.gethostname().strip()
    urls: list[str] = []
    seen_hosts: set[str] = set()

    def detect_primary_ipv4() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                candidate = str(sock.getsockname()[0]).strip()
                return candidate if usable_ipv4(candidate) else ""
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
                if not usable_ipv4(ip):
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


def _managerui_page_urls(config: ConfigSource, page: str) -> list[str]:
    port = NetworkConfig.from_config(config).http_port
    hostname = socket.gethostname().strip()
    urls: list[str] = []
    seen_hosts: set[str] = set()

    def detect_primary_ipv4() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                candidate = str(sock.getsockname()[0]).strip()
                return candidate if usable_ipv4(candidate) else ""
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
        urls.append(f"http://{normalized}:{port}/?page={page}")

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
                if not usable_ipv4(ip):
                    continue
                add_host(ip)
        except Exception:
            pass

    add_host("localhost")
    return urls


def _preferred_managerui_url(urls: list[str]) -> str:
    return next(
        (url for url in urls if url.startswith("http://") and url.split("://", 1)[1].split(":",
                1)[0].count(".") == 3),
        next((url for url in urls if "://localhost:" not in url.lower()), urls[0] if urls else ""),
    )


def get_splashscreen_enabled(config: ConfigSource) -> str:
    return "true" if SettingsConfig.from_config(config).splashscreen else "false"


def set_audio_muted(api: API, muted: Any) -> bool:
    muted_flag = muted if isinstance(muted, bool) else is_truthy(muted)
    cfg_set(api._ini_config, "behavior", "mute_audio", bool(muted_flag))
    api._ini_config.save()
    api.send_event_all_windows_incself({
        "type": "AudioMuteChanged",
        "muted": muted_flag,
    })
    return muted_flag


def get_vpinplay_endpoint(config: ConfigSource) -> str:
    """Where VPinPlay is, for a theme that asks.

    A shim. Core does not fetch a rating any more - an extension does, and a theme reads
    the answer off the entry - but a published theme may still call this to build a URL
    of its own, and the section it reads is still in the config because the handover to
    that extension copies rather than moves.
    """
    return VPinPlayConfig.from_config(config).api_endpoint


def get_media_priorities(config: ConfigSource) -> dict[str, str]:
    return MediaConfig.from_config(config).priority_payload()


def get_playfield_orientation(config: ConfigSource) -> str:
    return DisplayConfig.from_config(config).playfield_orientation


def get_playfield_rotation(config: ConfigSource) -> int:
    return DisplayConfig.from_config(config).playfield_rotation


def get_playfield_media_rotation(config: ConfigSource) -> str:
    return MediaConfig.from_config(config).playfield_media_rotation


def get_cab_mode(config: ConfigSource) -> bool:
    return DisplayConfig.from_config(config).cab_mode


def get_theme_assets_port(config: ConfigSource) -> int:
    return NetworkConfig.from_config(config).theme_assets_port


def get_http_port(config: ConfigSource) -> int:
    return NetworkConfig.from_config(config).http_port


def get_managerui_remote_link(config: ConfigSource) -> dict[str, Any]:
    urls = _managerui_remote_urls(config)
    preferred_url = _preferred_managerui_url(urls)
    return {
        "url": preferred_url,
        "urls": urls,
        "qr_svg": _build_remote_qr_svg(preferred_url) if preferred_url else "",
    }


def get_managerui_vpinplay_multi_link(config: ConfigSource) -> dict[str, Any]:
    urls = _managerui_page_urls(config, "vpinplay_account")
    preferred_url = _preferred_managerui_url(urls)
    return {
        "url": preferred_url,
        "urls": urls,
        "qr_svg": _build_remote_qr_svg(preferred_url) if preferred_url else "",
    }
