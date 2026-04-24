from __future__ import annotations

import shutil
import socket
import platform
import subprocess
import json
import os
from datetime import datetime
from pathlib import Path

from nicegui import context, run, ui

from common.iniconfig import IniConfig
from common.app_updater import get_install_context
from frontend.chromium_manager import get_chromium_path
from managerui.paths import CONFIG_DIR, VPINFE_INI_PATH
from managerui.ui_helpers import load_page_style

try:
    import psutil
except ImportError:  # pragma: no cover - handled gracefully in UI
    psutil = None


INI_PATH = VPINFE_INI_PATH
_STATIC_DETAILS_CACHE: dict | None = None
_GPU_FIELD_LABELS = {
    "gpu_clock": "GPU Clock",
    "mem_clock": "Memory Clock",
    "temp": "Temperature",
    "fan_speed": "Fan Speed",
    "power_draw": "Power Draw",
    "gpu_util": "GPU Utilization",
    "mem_util": "Memory Utilization",
}


def _gpu_monitoring_supported() -> bool:
    return platform.system() in {"Linux", "Darwin"}


def _resolve_usage_path() -> Path:
    """Choose an existing path on the filesystem whose volume we want to monitor."""
    candidate = Path.home()
    try:
        config = IniConfig(str(INI_PATH))
        tableroot = config.config.get("Settings", "tablerootdir", fallback="").strip()
        if tableroot:
            candidate = Path(tableroot).expanduser()
    except Exception:
        pass

    current = candidate
    while not current.exists() and current != current.parent:
        current = current.parent

    return current if current.exists() else Path.home()


def _format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _get_system_metrics(include_gpu: bool = False) -> dict:
    usage_path = _resolve_usage_path()
    total, used, free = shutil.disk_usage(usage_path)
    disk_percent = (used / total * 100) if total else 0.0
    static_details = _get_static_system_details()

    metrics = {
        "hostname": socket.gethostname(),
        "os_name": platform.system() or "Unknown",
        "os_version": platform.version() or platform.release() or "Unknown",
        "build_flavor": static_details["build_flavor"],
        "release_target": static_details["release_target"],
        "browser_name": static_details["browser_name"],
        "browser_path": static_details["browser_path"],
        "browser_version": static_details["browser_version"],
        "windowing_system": static_details["windowing_system"],
        "usage_path": str(usage_path),
        "disk_total": total,
        "disk_used": used,
        "disk_free": free,
        "disk_percent": disk_percent,
        "cpu_percent": None,
        "memory_total": None,
        "memory_available": None,
        "memory_percent": None,
        "gpu_supported": _gpu_monitoring_supported(),
        "gpu_available": False,
        "gpu_error": None,
        "gpu_name": None,
        "gpu_percent": None,
        "gpu_devices": [],
    }

    if psutil is not None:
        metrics["cpu_percent"] = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        metrics["memory_total"] = memory.total
        metrics["memory_available"] = memory.available
        metrics["memory_percent"] = memory.percent

    if include_gpu and metrics["gpu_supported"]:
        gpu_metrics = _get_nvtop_metrics()
        metrics.update(gpu_metrics)

    return metrics


def _get_nvtop_metrics() -> dict:
    empty_metrics = {
        "gpu_available": False,
        "gpu_error": None,
        "gpu_name": None,
        "gpu_percent": None,
        "gpu_devices": [],
    }

    nvtop_path = shutil.which("nvtop")
    if not nvtop_path:
        empty_metrics["gpu_error"] = "nvtop is not installed."
        return empty_metrics

    try:
        completed = subprocess.run(
            [nvtop_path, "-s"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        empty_metrics["gpu_error"] = "nvtop timed out."
        return empty_metrics
    except Exception as exc:
        empty_metrics["gpu_error"] = f"nvtop failed: {exc}"
        return empty_metrics

    stdout = (completed.stdout or "").strip()
    if not stdout:
        error_output = (completed.stderr or "").strip() or "No nvtop sample was returned."
        empty_metrics["gpu_error"] = error_output
        return empty_metrics

    if completed.returncode != 0:
        empty_metrics["gpu_error"] = (completed.stderr or stdout or "nvtop failed.").strip()
        return empty_metrics

    return _parse_nvtop_output(stdout, empty_metrics)


def _parse_nvtop_output(output: str, empty_metrics: dict) -> dict:
    metrics = empty_metrics.copy()
    try:
        devices = json.loads(output)
    except json.JSONDecodeError as exc:
        metrics["gpu_error"] = f"Could not parse nvtop output: {exc}"
        return metrics

    if not isinstance(devices, list) or not devices:
        metrics["gpu_error"] = "nvtop did not report any GPU devices."
        return metrics

    parsed_devices = []
    for index, device in enumerate(devices, start=1):
        if not isinstance(device, dict):
            continue
        parsed_devices.append(
            {
                "id": index,
                "device_name": device.get("device_name") or f"GPU {index}",
                "gpu_clock": device.get("gpu_clock"),
                "mem_clock": device.get("mem_clock"),
                "temp": device.get("temp"),
                "fan_speed": device.get("fan_speed"),
                "power_draw": device.get("power_draw"),
                "gpu_util": device.get("gpu_util"),
                "mem_util": device.get("mem_util"),
            }
        )

    if not parsed_devices:
        metrics["gpu_error"] = "nvtop returned no usable GPU devices."
        return metrics

    primary = parsed_devices[0]
    metrics["gpu_name"] = primary["device_name"]
    metrics["gpu_percent"] = _parse_percent_value(primary.get("gpu_util"))
    metrics["gpu_devices"] = parsed_devices
    metrics["gpu_available"] = True
    return metrics


def _parse_percent_value(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip().rstrip("%"))
    except Exception:
        return None


def _metric_color(value: float, warn: float, critical: float) -> str:
    if value >= critical:
        return "text-red-400"
    if value >= warn:
        return "text-amber-400"
    return "text-emerald-400"


def _metric_tone(value: float, warn: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= warn:
        return "warn"
    return "ok"


def _get_static_system_details() -> dict:
    global _STATIC_DETAILS_CACHE

    if _STATIC_DETAILS_CACHE is not None:
        return _STATIC_DETAILS_CACHE

    install_context = get_install_context()
    browser_path = _get_frontend_browser_path()
    _STATIC_DETAILS_CACHE = {
        "build_flavor": _get_build_flavor(install_context),
        "release_target": install_context.get("triplet") or "Unknown",
        "browser_name": _get_frontend_browser_name(browser_path),
        "browser_path": browser_path or "Unavailable",
        "browser_version": _get_frontend_browser_version(browser_path) or "Unknown",
        "windowing_system": _get_windowing_system(),
    }
    return _STATIC_DETAILS_CACHE


def _get_windowing_system() -> str:
    if platform.system() == "Windows":
        return "Windows"
    if platform.system() == "Darwin":
        return "macOS"

    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "").strip()
    display = os.environ.get("DISPLAY", "").strip()

    if wayland_display or session_type == "wayland":
        return "Wayland"
    if display or session_type == "x11":
        return "X11"
    if session_type:
        return session_type.capitalize()
    return "Unknown"


def _get_build_flavor(install_context: dict) -> str:
    if install_context.get("reason") == "source_build":
        return "source"
    if install_context.get("reason") == "non_release_build":
        return "non-release"
    if install_context.get("slim") is True:
        return "slim"
    if install_context.get("slim") is False:
        return "fat"
    return "unknown"


def _get_frontend_browser_path() -> str | None:
    try:
        return get_chromium_path()
    except Exception:
        return None


def _get_frontend_browser_name(browser_path: str | None) -> str:
    if not browser_path:
        return "Unavailable"

    lowered = browser_path.lower()
    if "msedge" in lowered or "edge" in lowered:
        return "Microsoft Edge"
    if "google chrome" in lowered or "google-chrome" in lowered:
        return "Google Chrome"
    if "chromium" in lowered:
        return "Chromium"
    if "chrome" in lowered:
        return "Chrome-compatible"
    return Path(browser_path).name


def _get_frontend_browser_version(browser_path: str | None) -> str | None:
    if not browser_path:
        return None

    if platform.system() == "Windows":
        return _get_windows_file_version(browser_path)

    try:
        completed = subprocess.run(
            [browser_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None

    output = (completed.stdout or completed.stderr or "").strip()
    return output or None


def _get_windows_file_version(browser_path: str) -> str | None:
    escaped_path = browser_path.replace("'", "''")
    powershell_cmd = f"(Get-Item '{escaped_path}').VersionInfo.ProductVersion"
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", powershell_cmd],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None

    output = (completed.stdout or completed.stderr or "").strip()
    return output or None


def render_panel(tab=None):
    load_page_style("system.css")

    page_client = context.client
    refresh_state = {"busy": False}
    gpu_state = {"enabled": False}

    with ui.column().classes("w-full gap-4"):
        with ui.card().classes("w-full system-hero"):
            with ui.row().classes("w-full justify-between items-center p-4 gap-4"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("monitor_heart", size="32px").style("color: var(--neon-cyan) !important;")
                    with ui.column().classes("gap-0"):
                        ui.label("System Monitor").classes("text-2xl font-bold").style("color: var(--ink) !important;")
                        ui.label("Live CPU and storage metrics for the current host.").classes("text-sm").style("color: var(--neon-cyan) !important;")
                refresh_button = ui.button("Refresh", icon="refresh").style('color: var(--neon-cyan) !important; background: var(--surface) !important; border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;')

        gpu_toggle_card = None
        gpu_toggle = None
        if _gpu_monitoring_supported():
            with ui.card().classes("system-card w-full p-5"):
                gpu_toggle_card = ui.card_section().classes("w-full")
                with gpu_toggle_card:
                    with ui.row().classes("w-full items-center justify-between gap-4"):
                        with ui.column().classes("gap-1"):
                            ui.label("GPU Monitoring").classes("text-lg font-semibold").style("color: var(--ink) !important;")
                            ui.label(
                                "Optional Linux and macOS monitoring. Requires `nvtop` to be installed and accessible."
                            ).style("color: var(--ink-muted) !important;")
                            ui.label(
                                "Turn this on to display GPU utilization, temperature, clocks, fan speed, and power draw when supported by nvtop."
                            ).classes("text-sm").style("color: var(--ink-muted) !important;")
                        gpu_toggle = ui.switch("Enable GPU metrics", value=False).style('color: var(--neon-cyan) !important; background: var(--surface) !important; border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;')

        with ui.row().classes("w-full gap-4 items-stretch flex-wrap"):
            with ui.card().classes("system-card p-5").style("flex: 1 1 320px; min-width: 280px;"):
                with ui.column().classes("gap-2"):
                    ui.label("CPU Utilization").classes("text-sm uppercase tracking-wide").style("color: var(--ink-muted) !important;")
                    cpu_value = ui.label("--").classes("system-value text-slate-200").style("color: var(--ink-muted) !important;")
                    cpu_detail = ui.label("Waiting for sample...").classes("system-subtle")

            with ui.card().classes("system-card p-5").style("flex: 1 1 320px; min-width: 280px;"):
                with ui.column().classes("gap-2"):
                    ui.label("Memory Utilization").classes("text-sm uppercase tracking-wide").style("color: var(--ink-muted) !important;")
                    memory_value = ui.label("--").classes("system-value").style("color: var(--ink-muted) !important;")
                    memory_detail = ui.label("Waiting for sample...").classes("system-subtle")

            with ui.card().classes("system-card p-5").style("flex: 1 1 320px; min-width: 280px;"):
                with ui.column().classes("gap-2"):
                    ui.label("Free Disk Space").classes("text-sm uppercase tracking-wide").style("color: var(--ink-muted) !important;")
                    disk_value = ui.label("--").classes("system-value").style("color: var(--ink-muted) !important;")
                    disk_detail = ui.label("Waiting for sample...").classes("system-subtle")

            gpu_value = None
            gpu_detail = None
            gpu_summary_card = None
            if _gpu_monitoring_supported():
                with ui.card().classes("system-card p-5").style("flex: 1 1 320px; min-width: 280px;") as gpu_summary_card:
                    with ui.column().classes("gap-2"):
                        ui.label("GPU Utilization").classes("text-sm uppercase tracking-wide").style("color: var(--ink-muted) !important;")
                        gpu_value = ui.label("--").classes("system-value").style("color: var(--ink-muted) !important;")
                        gpu_detail = ui.label("Waiting for sample...").classes("system-subtle")
                gpu_summary_card.visible = False

        gpu_blocks_label = None
        gpu_blocks_container = None
        gpu_details_card = None
        if _gpu_monitoring_supported():
            with ui.card().classes("system-card w-full p-5") as gpu_details_card:
                with ui.column().classes("gap-2"):
                    ui.label("GPU Details").classes("text-lg font-semibold").style("color: var(--ink) !important;")
                    gpu_blocks_label = ui.label("Waiting for sample...").classes("text-sm").style("color: var(--ink-muted) !important;")
                    gpu_blocks_container = ui.row().classes("w-full gap-2 items-stretch flex-wrap")
            gpu_details_card.visible = False

        with ui.card().classes("system-card w-full p-5"):
            with ui.column().classes("gap-2"):
                ui.label("System Details").classes("text-lg font-semibold").style("color: var(--ink) !important;")
                host_label = ui.label("Host: --").style("color: var(--ink-muted) !important;")
                os_label = ui.label("Operating system: --").style("color: var(--ink-muted) !important;")
                build_label = ui.label("VPinFE build: --").style("color: var(--ink-muted) !important;")
                release_label = ui.label("Release target: --").style("color: var(--ink-muted) !important;")
                windowing_label = ui.label("Windowing system: --").style("color: var(--ink-muted) !important;")
                browser_label = ui.label("Frontend browser: --").style("color: var(--ink-muted) !important;")
                browser_version_label = ui.label("Browser version: --").style("color: var(--ink-muted) !important;")
                browser_path_label = ui.label("Browser path: --").classes("break-all").style("color: var(--ink-muted) !important;")
                path_label = ui.label("Monitored path: --").classes("break-all").style("color: var(--ink-muted) !important;")
                updated_label = ui.label("Last updated: --").classes("text-sm").style("color: var(--ink-muted) !important;")

    async def refresh_metrics():
        if refresh_state["busy"]:
            return

        refresh_state["busy"] = True
        refresh_button.disable()
        try:
            metrics = await run.io_bound(_get_system_metrics, gpu_state["enabled"])
            cpu_percent = metrics["cpu_percent"]
            memory_percent = metrics["memory_percent"]
            disk_percent = metrics["disk_percent"]
            memory_total = metrics["memory_total"]
            memory_available = metrics["memory_available"]
            disk_used = _format_bytes(metrics["disk_used"])
            disk_total = _format_bytes(metrics["disk_total"])
            disk_free = _format_bytes(metrics["disk_free"])
            gpu_percent = metrics["gpu_percent"]

            with page_client:
                if cpu_percent is None:
                    cpu_value.set_text("Unavailable")
                    cpu_value.classes(remove="text-emerald-400 text-amber-400 text-red-400", add="text-slate-200")
                    cpu_detail.set_text("Install psutil to enable CPU metrics.")
                else:
                    cpu_value.set_text(f"{cpu_percent:.0f}%")
                    cpu_value.classes(
                        remove="text-slate-200 text-emerald-400 text-amber-400 text-red-400",
                        add=_metric_color(cpu_percent, warn=70.0, critical=90.0),
                    )
                    cpu_detail.set_text("Updated every 2 seconds")

                if memory_percent is None or memory_total is None or memory_available is None:
                    memory_value.set_text("Unavailable")
                    memory_value.classes(
                        remove="text-emerald-400 text-amber-400 text-red-400",
                        add="text-slate-200",
                    )
                    memory_detail.set_text("Install psutil to enable memory metrics.")
                else:
                    memory_value.set_text(f"{memory_percent:.0f}%")
                    memory_value.classes(
                        remove="text-slate-200 text-emerald-400 text-amber-400 text-red-400",
                        add=_metric_color(memory_percent, warn=75.0, critical=90.0),
                    )
                    memory_detail.set_text(
                        f"{_format_bytes(memory_available)} available of {_format_bytes(memory_total)} total"
                    )

                disk_value.set_text(disk_free)
                disk_value.classes(
                    remove="text-slate-200 text-emerald-400 text-amber-400 text-red-400",
                    add=_metric_color(disk_percent, warn=80.0, critical=90.0),
                )
                disk_detail.set_text(f"{disk_used} used of {disk_total} total ({disk_percent:.0f}% full)")

                if (
                    gpu_state["enabled"]
                    and gpu_value is not None
                    and gpu_detail is not None
                    and gpu_blocks_label is not None
                    and gpu_blocks_container is not None
                ):
                    if not metrics["gpu_available"]:
                        gpu_value.set_text("Unavailable")
                        gpu_value.classes(
                            remove="text-emerald-400 text-amber-400 text-red-400",
                            add="text-slate-200",
                        )
                        gpu_detail.set_text(metrics["gpu_error"] or "GPU metrics are unavailable.")
                        gpu_blocks_label.set_text("No GPU details available.")
                        gpu_blocks_container.clear()
                    else:
                        if gpu_percent is None:
                            gpu_value.set_text("N/A")
                            gpu_value.classes(
                                remove="text-emerald-400 text-amber-400 text-red-400",
                                add="text-slate-200",
                            )
                        else:
                            gpu_value.set_text(f"{gpu_percent:.0f}%")
                            gpu_value.classes(
                                remove="text-slate-200 text-emerald-400 text-amber-400 text-red-400",
                                add=_metric_color(gpu_percent, warn=70.0, critical=90.0),
                            )
                        gpu_parts = []
                        if metrics["gpu_name"]:
                            gpu_parts.append(metrics["gpu_name"])
                        if len(metrics["gpu_devices"]) > 1:
                            gpu_parts.append(f"{len(metrics['gpu_devices'])} GPUs detected")
                        primary = metrics["gpu_devices"][0]
                        for field in ("temp", "power_draw", "gpu_clock", "mem_clock"):
                            value = primary.get(field)
                            if value:
                                gpu_parts.append(f"{_GPU_FIELD_LABELS[field]} {value}")
                        gpu_detail.set_text(", ".join(gpu_parts) or "GPU metrics detected.")

                        gpu_blocks_label.set_text("Per-device GPU metrics")
                        gpu_blocks_container.clear()
                        with gpu_blocks_container:
                            for device in metrics["gpu_devices"]:
                                with ui.column().classes("w-full gap-2"):
                                    ui.label(device["device_name"]).classes("text-sm font-semibold text-slate-200")
                                    with ui.row().classes("w-full gap-2 items-stretch flex-wrap"):
                                        for field in (
                                            "gpu_util",
                                            "mem_util",
                                            "temp",
                                            "fan_speed",
                                            "power_draw",
                                            "gpu_clock",
                                            "mem_clock",
                                        ):
                                            value = device.get(field)
                                            if not value:
                                                continue
                                            percent_value = _parse_percent_value(value) if field in {"gpu_util", "mem_util", "fan_speed"} else None
                                            tone = _metric_tone(percent_value, warn=70.0, critical=90.0) if percent_value is not None else "ok"
                                            value_classes = "gpu-pill-value"
                                            if percent_value is not None:
                                                value_classes += f" {_metric_color(percent_value, warn=70.0, critical=90.0)}"
                                            with ui.column().classes(f"gpu-pill gpu-pill-{tone}").style("flex: 1 1 220px;"):
                                                ui.label(_GPU_FIELD_LABELS[field]).classes(f"gpu-pill-label gpu-pill-label-{tone}")
                                                ui.label(value).classes(value_classes)
                        if not metrics["gpu_devices"]:
                            gpu_blocks_label.set_text("No GPU device details were reported.")

                host_label.set_text(f"Host: {metrics['hostname']}")
                os_label.set_text(f"Operating system: {metrics['os_name']} {metrics['os_version']}")
                build_label.set_text(f"VPinFE build: {metrics['build_flavor']}")
                release_label.set_text(f"Release target: {metrics['release_target']}")
                windowing_label.set_text(f"Windowing system: {metrics['windowing_system']}")
                browser_label.set_text(f"Frontend browser: {metrics['browser_name']}")
                browser_version_label.set_text(f"Browser version: {metrics['browser_version']}")
                browser_path_label.set_text(f"Browser path: {metrics['browser_path']}")
                path_label.set_text(f"Monitored path: {metrics['usage_path']}")
                updated_label.set_text(f"Last updated: {datetime.now():%Y-%m-%d %H:%M:%S}")
        except Exception as exc:
            with page_client:
                cpu_value.set_text("Error")
                cpu_value.classes(remove="text-emerald-400 text-amber-400", add="text-red-400")
                cpu_detail.set_text(str(exc))
                memory_value.set_text("Error")
                memory_value.classes(remove="text-emerald-400 text-amber-400", add="text-red-400")
                memory_detail.set_text("Could not read memory usage.")
                disk_value.set_text("Error")
                disk_value.classes(remove="text-emerald-400 text-amber-400", add="text-red-400")
                disk_detail.set_text("Could not read disk usage.")
                if gpu_value is not None and gpu_detail is not None:
                    gpu_value.set_text("Error")
                    gpu_value.classes(remove="text-emerald-400 text-amber-400", add="text-red-400")
                    gpu_detail.set_text("Could not read GPU usage.")
                if gpu_blocks_label is not None:
                    gpu_blocks_label.set_text("Could not read GPU details.")
                if gpu_blocks_container is not None:
                    gpu_blocks_container.clear()
        finally:
            refresh_button.enable()
            refresh_state["busy"] = False

    def _apply_gpu_toggle() -> None:
        enabled = bool(gpu_toggle.value) if gpu_toggle is not None else False
        gpu_state["enabled"] = enabled
        if gpu_summary_card is not None:
            gpu_summary_card.visible = enabled
        if gpu_details_card is not None:
            gpu_details_card.visible = enabled
        if enabled:
            if gpu_detail is not None:
                gpu_detail.set_text("Waiting for sample...")
            if gpu_blocks_label is not None:
                gpu_blocks_label.set_text("Waiting for sample...")
        else:
            if gpu_blocks_container is not None:
                gpu_blocks_container.clear()

    if gpu_toggle is not None:
        async def handle_gpu_toggle(_event) -> None:
            _apply_gpu_toggle()
            await refresh_metrics()

        gpu_toggle.on_value_change(handle_gpu_toggle)
        _apply_gpu_toggle()

    refresh_button.on_click(refresh_metrics)
    ui.timer(0.1, refresh_metrics, once=True)
    ui.timer(2.0, refresh_metrics)
