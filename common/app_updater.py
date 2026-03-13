from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
import urllib.request

from platformdirs import user_config_dir

from common.app_version import get_version


CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
UPDATES_DIR = CONFIG_DIR / "updates"
LAST_UPDATE_LOG = CONFIG_DIR / "last_update.log"
LATEST_RELEASE_URL = "https://api.github.com/repos/superhac/vpinfe/releases/latest"
USER_AGENT = "VPinFE-Updater"


class UpdateError(RuntimeError):
    """Raised when an update cannot be prepared or applied."""


def _parse_tag_version(tag: str) -> tuple[int, int, int] | None:
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", (tag or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _request_json(url: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_file(url: str, dest: Path) -> None:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=60) as response:
        with open(dest, "wb") as fh:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)


def _append_log_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(message.rstrip() + "\n")


def _get_windows_powershell() -> str:
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidates = [
        system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        Path("powershell.exe"),
    ]
    for candidate in candidates:
        if candidate.name.lower() == "powershell.exe" and str(candidate) == "powershell.exe":
            resolved = shutil.which(str(candidate))
            if resolved:
                return resolved
            continue
        if candidate.exists():
            return str(candidate)
    return "powershell.exe"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_release_asset(release_payload: dict, asset_name: str) -> dict | None:
    for asset in release_payload.get("assets", []):
        if asset.get("name") == asset_name:
            return asset
    return None


def _bundled_chromium_exists() -> bool:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))

    exe_dir = Path(sys.executable).resolve().parent
    roots.append(exe_dir)
    roots.append(exe_dir / "_internal")

    system = platform.system()
    candidates: list[Path] = []
    if system == "Linux":
        candidates = [Path("chromium/linux/chrome/chrome")]
    elif system == "Windows":
        candidates = [
            Path("chromium/windows/chrome-win/chrome.exe"),
            Path("chromium/windows/chrome.exe"),
        ]
    elif system == "Darwin":
        candidates = [Path("chromium/Chromium.app/Contents/MacOS/Chromium")]

    for root in roots:
        if not root:
            continue
        for candidate in candidates:
            if (root / candidate).exists():
                return True
    return False


def get_install_context() -> dict:
    version = get_version()
    system = platform.system()
    machine = platform.machine().lower()

    context = {
        "current_version": version,
        "supported": False,
        "reason": None,
        "triplet": None,
        "install_root": None,
        "launch_target": None,
        "platform": system,
        "is_frozen": bool(getattr(sys, "frozen", False)),
    }

    if not getattr(sys, "frozen", False):
        context["reason"] = "source_build"
        return context

    if _parse_tag_version(version) is None:
        context["reason"] = "non_release_build"
        return context

    exe_path = Path(sys.executable).resolve()
    slim = not _bundled_chromium_exists()

    if system == "Linux":
        triplet = "linux-x64"
        install_root = exe_path.parent
        launch_target = install_root / "vpinfe"
    elif system == "Windows":
        triplet = "win-x64"
        install_root = exe_path.parent
        launch_target = exe_path
    elif system == "Darwin":
        if machine not in {"arm64", "aarch64"}:
            context["reason"] = "unsupported_architecture"
            return context
        context["reason"] = "macos_not_supported_yet"
        return context
    else:
        context["reason"] = "unsupported_platform"
        return context

    if slim:
        triplet = f"{triplet}-slim"

    context.update(
        {
            "supported": True,
            "triplet": triplet,
            "install_root": install_root,
            "launch_target": launch_target,
            "slim": slim,
        }
    )
    return context


def _get_release_payload() -> dict:
    return _request_json(LATEST_RELEASE_URL)


def _get_release_manifest(release_payload: dict) -> dict:
    manifest_asset = _find_release_asset(release_payload, "manifest.json")
    if not manifest_asset:
        raise UpdateError("Release manifest is missing")
    manifest_url = manifest_asset.get("browser_download_url")
    if not manifest_url:
        raise UpdateError("Release manifest download URL is missing")
    return _request_json(manifest_url)


def check_for_updates() -> dict:
    context = get_install_context()
    result = {
        "update_available": False,
        "error": None,
        "current_version": context["current_version"],
        "latest_version": None,
        "update_supported": False,
        "support_reason": context["reason"],
        "triplet": context["triplet"],
        "asset_name": None,
    }

    try:
        release_payload = _get_release_payload()
        latest_tag = (release_payload.get("tag_name") or "").strip()
        if not latest_tag:
            result["error"] = "missing_latest_tag"
            return result

        result["latest_version"] = latest_tag

        current_ver = _parse_tag_version(context["current_version"])
        latest_ver = _parse_tag_version(latest_tag)

        if current_ver is None:
            result["update_available"] = True
            if result["error"] is None:
                result["error"] = "non_release_build"
            return result

        if latest_ver is None:
            result["error"] = "latest_tag_unparseable"
            return result

        result["update_available"] = latest_ver > current_ver
        if not result["update_available"]:
            return result

        if not context["supported"]:
            return result

        manifest = _get_release_manifest(release_payload)
        asset_info = (manifest.get("assets") or {}).get(context["triplet"] or "")
        if not asset_info:
            result["support_reason"] = "no_matching_asset"
            return result

        asset_name = asset_info.get("file")
        if not asset_name:
            result["support_reason"] = "asset_missing_file_name"
            return result

        asset = _find_release_asset(release_payload, asset_name)
        if not asset:
            result["support_reason"] = "asset_not_attached_to_release"
            return result

        result["update_supported"] = True
        result["support_reason"] = None
        result["asset_name"] = asset_name
        return result
    except URLError:
        result["error"] = "remote_check_failed"
        return result
    except Exception as exc:
        print(f"[Updater] Failed to check for updates: {exc}")
        result["error"] = "remote_check_failed"
        return result


def prepare_update() -> dict:
    context = get_install_context()
    if not context["supported"]:
        raise UpdateError(context["reason"] or "update_not_supported")

    release_payload = _get_release_payload()
    latest_tag = (release_payload.get("tag_name") or "").strip()
    current_ver = _parse_tag_version(context["current_version"])
    latest_ver = _parse_tag_version(latest_tag)

    if not latest_tag or latest_ver is None:
        raise UpdateError("Could not determine the latest release")
    if current_ver is None:
        raise UpdateError("Automatic updates require a tagged release build")
    if latest_ver <= current_ver:
        raise UpdateError("Already on the latest version")

    manifest = _get_release_manifest(release_payload)
    asset_info = (manifest.get("assets") or {}).get(context["triplet"] or "")
    if not asset_info:
        raise UpdateError(f"No release asset for {context['triplet']}")

    asset_name = asset_info.get("file")
    expected_sha = (asset_info.get("sha256") or "").strip().lower()
    if not asset_name or not expected_sha:
        raise UpdateError("Release manifest is incomplete")

    asset = _find_release_asset(release_payload, asset_name)
    if not asset:
        raise UpdateError(f"Release asset {asset_name} was not found")

    asset_url = asset.get("browser_download_url")
    if not asset_url:
        raise UpdateError(f"Release asset {asset_name} has no download URL")

    stage_dir = UPDATES_DIR / latest_tag / (context["triplet"] or "unknown")
    stage_dir.mkdir(parents=True, exist_ok=True)
    _append_log_line(LAST_UPDATE_LOG, f"[Updater] Preparing update {latest_tag} for {context['triplet']}")

    zip_path = stage_dir / asset_name
    if zip_path.exists() and _sha256_file(zip_path) != expected_sha:
        _append_log_line(LAST_UPDATE_LOG, f"[Updater] Removing stale cached asset {zip_path}")
        zip_path.unlink()

    if not zip_path.exists():
        temp_path = stage_dir / f"{asset_name}.part"
        if temp_path.exists():
            temp_path.unlink()
        _append_log_line(LAST_UPDATE_LOG, f"[Updater] Downloading {asset_name} to {temp_path}")
        _download_file(asset_url, temp_path)
        actual_sha = _sha256_file(temp_path)
        _append_log_line(LAST_UPDATE_LOG, f"[Updater] Downloaded asset sha256={actual_sha}")
        if actual_sha != expected_sha:
            temp_path.unlink(missing_ok=True)
            raise UpdateError("Downloaded update failed checksum verification")
        temp_path.replace(zip_path)
        _append_log_line(LAST_UPDATE_LOG, f"[Updater] Cached verified asset at {zip_path}")
    else:
        _append_log_line(LAST_UPDATE_LOG, f"[Updater] Reusing cached asset {zip_path}")

    return {
        "latest_version": latest_tag,
        "zip_path": str(zip_path),
        "stage_dir": str(stage_dir),
        "install_root": str(context["install_root"]),
        "launch_target": str(context["launch_target"]),
        "platform": context["platform"],
        "triplet": context["triplet"],
        "asset_name": asset_name,
        "last_update_log": str(LAST_UPDATE_LOG),
    }


def _build_posix_update_script(prepared: dict, current_pid: int, log_path: Path) -> str:
    zip_path = shlex.quote(prepared["zip_path"])
    stage_dir = shlex.quote(prepared["stage_dir"])
    install_root = shlex.quote(prepared["install_root"])
    launch_target = shlex.quote(prepared["launch_target"])
    log_file = shlex.quote(str(log_path))
    last_log = shlex.quote(prepared["last_update_log"])
    return f"""#!/bin/sh
set -eu

PID={current_pid}
ZIP_PATH={zip_path}
STAGE_DIR={stage_dir}
INSTALL_ROOT={install_root}
LAUNCH_TARGET={launch_target}
LOG_PATH={log_file}
LAST_LOG={last_log}
EXTRACT_ROOT="$STAGE_DIR/extracted"
NEW_ROOT="$EXTRACT_ROOT/vpinfe"
BACKUP_ROOT="${{INSTALL_ROOT}}.bak"

mkdir -p "$(dirname "$LOG_PATH")"
: >"$LOG_PATH"
exec >>"$LOG_PATH" 2>&1
echo "[Updater] Stage log: $LOG_PATH"
echo "[Updater] Stable log: $LAST_LOG"
echo "[Updater] Stage log: $LOG_PATH" >>"$LAST_LOG"
echo "[Updater] Install root: $INSTALL_ROOT" >>"$LAST_LOG"
echo "[Updater] Launch target: $LAUNCH_TARGET" >>"$LAST_LOG"
echo "[Updater] Waiting for pid $PID to exit"
while kill -0 "$PID" 2>/dev/null; do
    sleep 1
done
echo "[Updater] Source process exited"

rm -rf "$EXTRACT_ROOT"
mkdir -p "$EXTRACT_ROOT"
echo "[Updater] Extracting $ZIP_PATH"

if command -v unzip >/dev/null 2>&1; then
    unzip -q "$ZIP_PATH" -d "$EXTRACT_ROOT"
elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import pathlib, zipfile; zipfile.ZipFile(pathlib.Path(r'$ZIP_PATH')).extractall(pathlib.Path(r'$EXTRACT_ROOT'))"
else
    echo "[Updater] No unzip tool available"
    exit 1
fi

if [ ! -d "$NEW_ROOT" ]; then
    echo "[Updater] Extracted update missing vpinfe directory"
    exit 1
fi
echo "[Updater] Extraction complete"

rm -rf "$BACKUP_ROOT"
mv "$INSTALL_ROOT" "$BACKUP_ROOT"
echo "[Updater] Moved current install to backup: $BACKUP_ROOT"
if mv "$NEW_ROOT" "$INSTALL_ROOT"; then
    echo "[Updater] Installed new version into $INSTALL_ROOT"
    chmod +x "$LAUNCH_TARGET" 2>/dev/null || true
    cd "$INSTALL_ROOT"
    nohup "$LAUNCH_TARGET" >/dev/null 2>&1 &
    NEW_PID=$!
    echo "[Updater] Relaunch started with pid $NEW_PID"
    sleep 3
    if kill -0 "$NEW_PID" 2>/dev/null; then
        echo "[Updater] Relaunch appears to be running"
    else
        echo "[Updater] Relaunch process exited quickly"
    fi
    rm -rf "$BACKUP_ROOT"
    rm -rf "$EXTRACT_ROOT"
    echo "[Updater] Update applied successfully"
else
    echo "[Updater] Swap failed, restoring backup"
    rm -rf "$INSTALL_ROOT"
    mv "$BACKUP_ROOT" "$INSTALL_ROOT"
    exit 1
fi
"""


def _ps_literal(value: str) -> str:
    return value.replace("'", "''")


def _cmd_literal(value: str) -> str:
    return value.replace("^", "^^").replace("&", "^&").replace("<", "^<").replace(">", "^>").replace("|", "^|")


def _build_windows_update_script(prepared: dict, current_pid: int, log_path: Path) -> str:
    zip_path = _ps_literal(prepared["zip_path"])
    stage_dir = _ps_literal(prepared["stage_dir"])
    install_root = _ps_literal(prepared["install_root"])
    launch_target = _ps_literal(prepared["launch_target"])
    log_file = _ps_literal(str(log_path))
    last_log = _ps_literal(prepared["last_update_log"])
    return f"""$ErrorActionPreference = 'Stop'
$PidToWait = {current_pid}
$ZipPath = '{zip_path}'
$StageDir = '{stage_dir}'
$InstallRoot = '{install_root}'
$LaunchTarget = '{launch_target}'
$ExtractRoot = Join-Path $StageDir 'extracted'
$NewRoot = Join-Path $ExtractRoot 'vpinfe'
$BackupRoot = "$InstallRoot.bak"
$StableLog = '{last_log}'

function Write-Stable([string]$Message) {{
    Add-Content -Path $StableLog -Value $Message
}}

function Invoke-WithRetry([scriptblock]$Action, [string]$Description, [int]$Attempts = 20, [int]$DelayMs = 500) {{
    for ($i = 1; $i -le $Attempts; $i++) {{
        try {{
            & $Action
            if ($i -gt 1) {{
                Write-Output "[Updater] $Description succeeded on retry $i"
            }}
            return
        }}
        catch {{
            Write-Output "[Updater] $Description failed on attempt ${i}: $($_.Exception.Message)"
            if ($i -eq $Attempts) {{
                throw
            }}
            Start-Sleep -Milliseconds $DelayMs
        }}
    }}
}}

Start-Transcript -Path '{log_file}' -Append | Out-Null
try {{
    Write-Stable "[Updater] Stage log: {log_file}"
    Write-Stable "[Updater] Install root: $InstallRoot"
    Write-Stable "[Updater] Launch target: $LaunchTarget"
    Write-Output "[Updater] Waiting for pid $PidToWait to exit"
    while (Get-Process -Id $PidToWait -ErrorAction SilentlyContinue) {{
        Start-Sleep -Seconds 1
    }}
    Write-Output "[Updater] Source process exited"
    Start-Sleep -Seconds 2

    if (Test-Path -LiteralPath $ExtractRoot) {{
        Invoke-WithRetry {{ Remove-Item -LiteralPath $ExtractRoot -Recurse -Force }} "Removing previous extract root"
    }}
    Write-Output "[Updater] Extracting $ZipPath"
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractRoot -Force

    if (-not (Test-Path -LiteralPath $NewRoot)) {{
        throw "Extracted update missing vpinfe directory"
    }}
    Write-Output "[Updater] Extraction complete"

    if (Test-Path -LiteralPath $BackupRoot) {{
        Invoke-WithRetry {{ Remove-Item -LiteralPath $BackupRoot -Recurse -Force }} "Removing previous backup"
    }}

    Invoke-WithRetry {{ Rename-Item -LiteralPath $InstallRoot -NewName ([IO.Path]::GetFileName($BackupRoot)) }} "Renaming install root to backup"
    Write-Output "[Updater] Moved current install to backup: $BackupRoot"
    Invoke-WithRetry {{ Move-Item -LiteralPath $NewRoot -Destination $InstallRoot }} "Moving extracted install into place"
    Write-Output "[Updater] Installed new version into $InstallRoot"
    $proc = Start-Process -FilePath $LaunchTarget -WorkingDirectory $InstallRoot -PassThru
    Write-Output "[Updater] Relaunch started with pid $($proc.Id)"
    Start-Sleep -Seconds 3
    if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {{
        Write-Output "[Updater] Relaunch appears to be running"
    }}
    else {{
        Write-Output "[Updater] Relaunch process exited quickly"
    }}
    Invoke-WithRetry {{ Remove-Item -LiteralPath $BackupRoot -Recurse -Force }} "Removing backup after successful relaunch"
    Invoke-WithRetry {{ Remove-Item -LiteralPath $ExtractRoot -Recurse -Force }} "Removing extract root after successful relaunch"
    Write-Output "[Updater] Update applied successfully"
}}
catch {{
    Write-Output "[Updater] ERROR: $($_.Exception.Message)"
    Write-Stable "[Updater] ERROR: $($_.Exception.Message)"
    if (-not (Test-Path -LiteralPath $InstallRoot) -and (Test-Path -LiteralPath $BackupRoot)) {{
        Invoke-WithRetry {{ Rename-Item -LiteralPath $BackupRoot -NewName ([IO.Path]::GetFileName($InstallRoot)) }} "Restoring backup"
    }}
    throw
}}
finally {{
    Stop-Transcript | Out-Null
}}
"""


def _build_windows_bootstrap_script(powershell_exe: str, script_path: Path, stable_log: Path) -> str:
    ps_path = _cmd_literal(str(Path(powershell_exe)))
    updater_script = _cmd_literal(str(script_path))
    stable_log_path = _cmd_literal(str(stable_log))
    return f"""@echo off
setlocal
echo [Updater] Bootstrap starting >> "{stable_log_path}"
echo [Updater] Invoking PowerShell script {updater_script} >> "{stable_log_path}"
"{ps_path}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{updater_script}" >> "{stable_log_path}" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [Updater] Bootstrap launched PowerShell with exit code %EXIT_CODE% >> "{stable_log_path}"
exit /b %EXIT_CODE%
"""


def launch_prepared_update(prepared: dict) -> None:
    stage_dir = Path(prepared["stage_dir"])
    stage_dir.mkdir(parents=True, exist_ok=True)
    current_pid = os.getpid()
    log_path = stage_dir / "apply_update.log"
    _append_log_line(Path(prepared["last_update_log"]), f"[Updater] Launching detached updater for {prepared['latest_version']}")

    if platform.system() == "Windows":
        script_path = stage_dir / "apply_update.ps1"
        script_path.write_text(_build_windows_update_script(prepared, current_pid, log_path), encoding="utf-8")
        _append_log_line(Path(prepared["last_update_log"]), f"[Updater] PowerShell script written to {script_path}")
        powershell_exe = _get_windows_powershell()
        _append_log_line(Path(prepared["last_update_log"]), f"[Updater] Using PowerShell at {powershell_exe}")
        bootstrap_path = stage_dir / "launch_update.cmd"
        bootstrap_path.write_text(
            _build_windows_bootstrap_script(
                powershell_exe=powershell_exe,
                script_path=script_path,
                stable_log=Path(prepared["last_update_log"]),
            ),
            encoding="utf-8",
        )
        _append_log_line(Path(prepared["last_update_log"]), f"[Updater] Bootstrap script written to {bootstrap_path}")
        cmd_exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
        _append_log_line(Path(prepared["last_update_log"]), f"[Updater] Launching bootstrap via {cmd_exe} /c {bootstrap_path}")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            [
                cmd_exe,
                "/c",
                str(bootstrap_path),
            ],
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        return

    script_path = stage_dir / "apply_update.sh"
    script_path.write_text(_build_posix_update_script(prepared, current_pid, log_path), encoding="utf-8")
    script_path.chmod(0o755)
    _append_log_line(Path(prepared["last_update_log"]), f"[Updater] Shell script written to {script_path}")
    subprocess.Popen(
        ["/bin/sh", str(script_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
