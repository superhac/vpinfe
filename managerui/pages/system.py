from __future__ import annotations

import shutil
import socket
import platform
import subprocess
from datetime import datetime
from pathlib import Path

from nicegui import context, run, ui
from platformdirs import user_config_dir

from common.iniconfig import IniConfig
from common.app_updater import get_install_context
from frontend.chromium_manager import get_chromium_path

try:
    import psutil
except ImportError:  # pragma: no cover - handled gracefully in UI
    psutil = None


CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
INI_PATH = CONFIG_DIR / "vpinfe.ini"


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


def _get_system_metrics() -> dict:
    usage_path = _resolve_usage_path()
    total, used, free = shutil.disk_usage(usage_path)
    disk_percent = (used / total * 100) if total else 0.0
    install_context = get_install_context()
    browser_path = _get_frontend_browser_path()
    browser_name = _get_frontend_browser_name(browser_path)
    browser_version = _get_frontend_browser_version(browser_path)

    metrics = {
        "hostname": socket.gethostname(),
        "os_name": platform.system() or "Unknown",
        "os_version": platform.version() or platform.release() or "Unknown",
        "build_flavor": _get_build_flavor(install_context),
        "release_target": install_context.get("triplet") or "Unknown",
        "browser_name": browser_name,
        "browser_path": browser_path or "Unavailable",
        "browser_version": browser_version or "Unknown",
        "usage_path": str(usage_path),
        "disk_total": total,
        "disk_used": used,
        "disk_free": free,
        "disk_percent": disk_percent,
        "cpu_percent": None,
        "memory_total": None,
        "memory_available": None,
        "memory_percent": None,
    }

    if psutil is not None:
        metrics["cpu_percent"] = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        metrics["memory_total"] = memory.total
        metrics["memory_available"] = memory.available
        metrics["memory_percent"] = memory.percent

    return metrics


def _metric_color(value: float, warn: float, critical: float) -> str:
    if value >= critical:
        return "text-red-400"
    if value >= warn:
        return "text-amber-400"
    return "text-emerald-400"


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


def render_panel(tab=None):
    ui.add_head_html(
        '''
        <style>
            .system-hero {
                background: linear-gradient(135deg, #134e4a 0%, #0f172a 100%);
                border-radius: 12px;
            }
            .system-card {
                background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%) !important;
                border: 1px solid #334155 !important;
                border-radius: 12px !important;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2) !important;
            }
            .system-value {
                font-size: 2rem;
                font-weight: 700;
                line-height: 1;
            }
            .system-subtle {
                color: #94a3b8;
                font-size: 0.875rem;
            }
        </style>
        '''
    )

    page_client = context.client
    refresh_state = {"busy": False}

    with ui.column().classes("w-full gap-4"):
        with ui.card().classes("w-full system-hero"):
            with ui.row().classes("w-full justify-between items-center p-4 gap-4"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("monitor_heart", size="32px").classes("text-teal-200")
                    with ui.column().classes("gap-0"):
                        ui.label("System Monitor").classes("text-2xl font-bold text-white")
                        ui.label("Live CPU and storage metrics for the current host.").classes(
                            "text-teal-100 text-sm"
                        )
                refresh_button = ui.button("Refresh", icon="refresh").props("color=primary rounded")

        with ui.row().classes("w-full gap-4 items-stretch flex-wrap"):
            with ui.card().classes("system-card p-5").style("flex: 1 1 320px; min-width: 280px;"):
                with ui.column().classes("gap-2"):
                    ui.label("CPU Utilization").classes("text-sm uppercase tracking-wide text-slate-400")
                    cpu_value = ui.label("--").classes("system-value text-slate-200")
                    cpu_detail = ui.label("Waiting for sample...").classes("system-subtle")

            with ui.card().classes("system-card p-5").style("flex: 1 1 320px; min-width: 280px;"):
                with ui.column().classes("gap-2"):
                    ui.label("Memory Utilization").classes("text-sm uppercase tracking-wide text-slate-400")
                    memory_value = ui.label("--").classes("system-value text-slate-200")
                    memory_detail = ui.label("Waiting for sample...").classes("system-subtle")

            with ui.card().classes("system-card p-5").style("flex: 1 1 320px; min-width: 280px;"):
                with ui.column().classes("gap-2"):
                    ui.label("Free Disk Space").classes("text-sm uppercase tracking-wide text-slate-400")
                    disk_value = ui.label("--").classes("system-value text-slate-200")
                    disk_detail = ui.label("Waiting for sample...").classes("system-subtle")

        with ui.card().classes("system-card w-full p-5"):
            with ui.column().classes("gap-2"):
                ui.label("System Details").classes("text-lg font-semibold text-white")
                host_label = ui.label("Host: --").classes("text-slate-300")
                os_label = ui.label("Operating system: --").classes("text-slate-300")
                build_label = ui.label("VPinFE build: --").classes("text-slate-300")
                release_label = ui.label("Release target: --").classes("text-slate-300")
                browser_label = ui.label("Frontend browser: --").classes("text-slate-300")
                browser_version_label = ui.label("Browser version: --").classes("text-slate-300")
                browser_path_label = ui.label("Browser path: --").classes("text-slate-400 break-all")
                path_label = ui.label("Monitored path: --").classes("text-slate-400 break-all")
                updated_label = ui.label("Last updated: --").classes("text-slate-500 text-sm")

    async def refresh_metrics():
        if refresh_state["busy"]:
            return

        refresh_state["busy"] = True
        refresh_button.disable()
        try:
            metrics = await run.io_bound(_get_system_metrics)
            cpu_percent = metrics["cpu_percent"]
            memory_percent = metrics["memory_percent"]
            disk_percent = metrics["disk_percent"]
            memory_total = metrics["memory_total"]
            memory_available = metrics["memory_available"]
            disk_used = _format_bytes(metrics["disk_used"])
            disk_total = _format_bytes(metrics["disk_total"])
            disk_free = _format_bytes(metrics["disk_free"])

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
                host_label.set_text(f"Host: {metrics['hostname']}")
                os_label.set_text(f"Operating system: {metrics['os_name']} {metrics['os_version']}")
                build_label.set_text(f"VPinFE build: {metrics['build_flavor']}")
                release_label.set_text(f"Release target: {metrics['release_target']}")
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
        finally:
            refresh_button.enable()
            refresh_state["busy"] = False

    refresh_button.on_click(refresh_metrics)
    ui.timer(0.1, refresh_metrics, once=True)
    ui.timer(2.0, refresh_metrics)
