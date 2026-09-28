"""The VPinPlay page: the account scores are submitted under."""

from __future__ import annotations

import json
import logging
from html import escape
from io import BytesIO
from urllib.parse import quote

from nicegui import ui

from common.config_store import ConfigStore
from managerui.config_fields import is_checkbox_field
from managerui.config_options import get_friendly_name
from managerui.paths import VPINFE_INI_PATH
from managerui.ui_helpers import attach_shell_save_bar, load_page_style

logger = logging.getLogger("vpinfe.manager.vpinplay")

INI_PATH = VPINFE_INI_PATH
VPINPLAY_BASE_URL = "https://www.vpinplay.com/"
SECTION = "vpinplay"


def _build_vpinplay_user_url(user_id: str) -> str:
    uid = (user_id or "").strip()
    if not uid:
        return f"{VPINPLAY_BASE_URL}players.html"
    return f"{VPINPLAY_BASE_URL}players.html?userid={quote(uid)}"


def _build_vpinplay_qr_payload(user_id: str, initials: str, machine_id: str) -> str:
    payload = {
        "type": "vpinplay_identity",
        "version": 1,
        "userId": (user_id or "").strip(),
        "initials": (initials or "").strip().upper(),
        "machineId": (machine_id or "").strip(),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _build_qr_svg(value: str) -> str:
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
    qr.add_data(value)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    image.save(stream)
    svg = stream.getvalue().decode("utf-8")
    svg_tag_start = svg.find("<svg")
    if svg_tag_start != -1 and "<rect" not in svg:
        svg_tag_end = svg.find(">", svg_tag_start)
        if svg_tag_end != -1:
            svg = (
                f"{svg[:svg_tag_end + 1]}"
                '<rect width="100%" height="100%" fill="white"/>'
                f"{svg[svg_tag_end + 1:]}"
            )
    return svg


def _embed_payload_in_svg(svg: str, payload: str) -> str:
    svg_tag_start = svg.find("<svg")
    if svg_tag_start == -1:
        return svg

    svg_tag_end = svg.find(">", svg_tag_start)
    if svg_tag_end == -1:
        return svg

    escaped_payload = escape(payload)
    comment_payload = payload.replace("--", r"\u002d\u002d")
    embedded = (
        f"{svg[:svg_tag_end + 1]}"
        f"<!--VPINPLAY_PAYLOAD:{comment_payload}-->"
        f'<metadata id="vpinplay-payload" data-type="application/json">{escaped_payload}</metadata>'
        f'<desc id="vpinplay-payload-desc">{escaped_payload}</desc>'
        f"{svg[svg_tag_end + 1:]}"
    )
    return embedded


def _build_qr_filename(user_id: str) -> str:
    safe_user_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (user_id or "").strip()) or "user"
    return f"vpinplay-{safe_user_id}.svg"


def render_panel():
    config = ConfigStore(str(INI_PATH))
    load_page_style("vpinfe_config.css")

    if not config.config.has_section(SECTION):
        config.config.add_section(SECTION)

    inputs = {SECTION: {}}
    vpinplay_user_link = None
    qr_preview = None
    qr_download_button = None

    def _input_value(key: str, fallback: str = "") -> str:
        return str(
            getattr(inputs[SECTION].get(key), "value", config.config.get(SECTION, key, fallback=fallback))
            or ""
        ).strip()

    def update_vpinplay_user_link():
        if vpinplay_user_link is None:
            return
        vpinplay_user_link.text = "Your Stats"
        vpinplay_user_link.props(f"href={_build_vpinplay_user_url(_input_value('user_id'))}")

    def update_vpinplay_qr():
        if qr_preview is None or qr_download_button is None:
            return

        user_id = _input_value("user_id")
        initials = _input_value("initials")
        machine_id = _input_value("machine_id")

        if not user_id or not initials or not machine_id:
            qr_preview.set_content(
                '<div class="config-vpinplay-qr-empty">'
                'Enter a User ID and Initials to generate your cabinet QR code.'
                '</div>'
            )
            qr_download_button.disable()
            return

        payload = _build_vpinplay_qr_payload(user_id, initials, machine_id)
        svg = _build_qr_svg(payload)
        if not svg:
            qr_preview.set_content(
                '<div class="config-vpinplay-qr-empty">'
                'Unable to generate QR code. Check the Python qrcode installation.'
                '</div>'
            )
            qr_download_button.disable()
            return

        qr_preview.set_content(svg)
        qr_download_button.enable()

    def download_vpinplay_qr():
        user_id = _input_value("user_id")
        initials = _input_value("initials")
        machine_id = _input_value("machine_id")
        if not user_id or not initials or not machine_id:
            ui.notify("User ID, Initials, and Machine ID are required.", type="warning")
            return

        payload = _build_vpinplay_qr_payload(user_id, initials, machine_id)
        svg = _embed_payload_in_svg(_build_qr_svg(payload), payload)
        if not svg:
            ui.notify("Unable to generate QR code.", type="negative")
            return

        ui.download(svg.encode("utf-8"), _build_qr_filename(user_id))

    def build_config_input(key: str, value: str):
        friendly_label = get_friendly_name(key)
        is_checkbox = is_checkbox_field(SECTION, key)

        with ui.element("div").classes("config-field-card compact" if is_checkbox else "config-field-card"):
            if not is_checkbox:
                ui.label(friendly_label).classes("config-field-label")

            if is_checkbox:
                inp = ui.checkbox(text=friendly_label, value=(value == "true")).classes("config-input")
            else:
                inp = ui.input(value=value).props("outlined dense").classes("config-input")
                if key == "machine_id":
                    inp.props("readonly disable")
                if key == "initials":
                    inp.props("maxlength=3").classes("config-uppercase-input")

                    def on_initials_change(e):
                        normalized = str(e.value or "").upper()
                        if inp.value != normalized:
                            inp.value = normalized
                        update_vpinplay_qr()

                    inp.on("input", on_initials_change)
                    inp.on_value_change(on_initials_change)

            inputs[SECTION][key] = inp
            if key == "user_id":
                inp.on_value_change(
                    lambda _: (update_vpinplay_user_link(), update_vpinplay_qr())
                )

    def save_config():
        for key, inp in inputs[SECTION].items():
            if type(inp.value) is bool:
                config.config.set(SECTION, key, str(inp.value).lower())
            else:
                value = inp.value
                if key == "initials":
                    value = str(value or "").upper()
                    inp.value = value
                config.config.set(SECTION, key, value)
        config.save()
        ui.notify("VPinPlay settings saved", type="positive")

    options = config.config.options(SECTION)
    sync_key = "sync_on_exit"
    endpoint_key = "api_endpoint"
    user_key = "user_id"
    initials_key = "initials"
    machine_key = "machine_id"

    with ui.column().classes("w-full config-page-shell"):
        with ui.card().classes("w-full config-hero").style("overflow: hidden;"):
            with ui.element("div").classes("w-full config-vpinplay-links p-6"):
                ui.image("/static/img/VPinPlay_Logo_1.0.png").style(
                    "width: 200px; height: 200px; object-fit: contain;"
                )
                with ui.column().classes("config-vpinplay-links-copy"):
                    ui.link("VPinPlay Home", VPINPLAY_BASE_URL, new_tab=True).style(
                        "color: var(--neon-cyan) !important;"
                    )
                    vpinplay_user_link = ui.link(
                        "",
                        _build_vpinplay_user_url(config.config.get(SECTION, user_key, fallback="")),
                        new_tab=True,
                    ).style("color: var(--neon-cyan) !important;")
                update_vpinplay_user_link()

        with ui.element("div").classes("config-panel-shell w-full"):
            with ui.card().classes("config-card w-full p-4"):
                with ui.element("div").classes("config-vpinplay-pair"):
                    with ui.column().classes("w-full gap-3"):
                        with ui.card().classes("config-side-card w-full p-4"):
                            ui.label("VPinPlay Settings").classes("text-lg font-semibold").style(
                                "color: var(--ink) !important;"
                            )
                            ui.label(
                                "Configure the VPinPlay service endpoint and cabinet identity."
                            ).classes("text-sm").style("color: var(--ink-muted) !important;")
                            with ui.element("div").classes("config-form-grid mt-3"):
                                if endpoint_key in options:
                                    build_config_input(endpoint_key, config.config.get(SECTION, endpoint_key, fallback=""))
                                if user_key in options:
                                    build_config_input(user_key, config.config.get(SECTION, user_key, fallback=""))
                                if initials_key in options:
                                    build_config_input(initials_key, config.config.get(SECTION, initials_key, fallback=""))
                                if machine_key in options:
                                    build_config_input(machine_key, config.config.get(SECTION, machine_key, fallback=""))

                        for key in options:
                            if key in (sync_key, endpoint_key, user_key, initials_key, machine_key):
                                continue
                            build_config_input(key, config.config.get(SECTION, key, fallback=""))

                    with ui.column().classes("w-full gap-3"):
                        with ui.card().classes("config-side-card w-full p-4"):
                            ui.label("My QR Code").classes("text-lg font-semibold").style(
                                "color: var(--ink) !important;"
                            )
                            qr_preview = ui.html("").classes("config-vpinplay-qr-preview mt-3")
                            qr_download_button = ui.button(
                                "Download QR Code",
                                icon="download",
                                on_click=download_vpinplay_qr,
                            ).classes("mt-3").style(
                                "color: var(--neon-purple) !important; background: var(--surface) !important; "
                                "border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;"
                            )
                            update_vpinplay_qr()

        # --- Save bar (shared shell footer) --------------------------------
        def _norm(value):
            return "" if value is None else str(value)

        initial_raw = {key: inp.value for key, inp in inputs[SECTION].items()}

        def changed_count():
            return sum(
                1
                for key, inp in inputs[SECTION].items()
                if _norm(inp.value) != _norm(initial_raw.get(key))
            )

        def on_save():
            save_config()
            for key, inp in inputs[SECTION].items():
                initial_raw[key] = inp.value

        def on_discard():
            for key, value in initial_raw.items():
                inp = inputs[SECTION].get(key)
                if inp is not None:
                    inp.value = value

        update_save_bar = attach_shell_save_bar(
            count=changed_count, on_save=on_save, on_discard=on_discard
        )
        for inp in inputs[SECTION].values():
            inp.on_value_change(lambda _: update_save_bar())
        update_save_bar()
