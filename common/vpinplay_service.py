import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from common.app_version import get_version
from common.tableparser import TableParser


logger = logging.getLogger("vpinfe.common.vpinplay_service")


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_last_run(value):
    if value in (None, ""):
        return None
    return value


def _normalize_service_endpoint(service_ip: str) -> str:
    raw = str(service_ip or "").strip()
    if not raw:
        raise ValueError("Service IP is required.")

    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlparse(raw)
    if not parsed.netloc:
        raise ValueError("Service IP/host is invalid.")

    base = raw.rstrip("/")
    if base.endswith("/api/v1/sync"):
        return base
    if base.endswith("/api/v1"):
        return f"{base}/sync"
    return f"{base}/api/v1/sync"


def _build_table_payload(meta: dict) -> dict | None:
    info = meta.get("Info", {}) if isinstance(meta.get("Info"), dict) else {}
    user = meta.get("User", {}) if isinstance(meta.get("User"), dict) else {}
    vpx = meta.get("VPXFile", {}) if isinstance(meta.get("VPXFile"), dict) else {}
    vpinfe = meta.get("VPinFE", {}) if isinstance(meta.get("VPinFE"), dict) else {}

    vps_id = str(info.get("VPSId", "") or "").strip()
    if not vps_id:
        return None

    return {
        "info": {
            "vpsId": vps_id,
            "rom": str(info.get("Rom", "") or ""),
        },
        "user": {
            "rating": _to_int(user.get("Rating", 0), default=0),
            "lastRun": _normalize_last_run(user.get("LastRun")),
            "startCount": _to_int(user.get("StartCount", 0), default=0),
            "runTime": _to_int(user.get("RunTime", 0), default=0),
        },
        "vpxFile": {
            "filename": str(vpx.get("filename", "") or ""),
            "filehash": str(vpx.get("filehash", "") or ""),
            "version": str(vpx.get("version", "") or ""),
            "releaseDate": str(vpx.get("releaseDate", "") or ""),
            "saveDate": str(vpx.get("saveDate", "") or ""),
            "saveRev": str(vpx.get("saveRev", "") or ""),
            "manufacturer": str(vpx.get("manufacturer", "") or ""),
            "year": str(vpx.get("year", "") or ""),
            "type": str(vpx.get("type", "") or ""),
            "vbsHash": str(vpx.get("vbsHash", "") or ""),
            "rom": str(vpx.get("rom", "") or ""),
            "detectNfozzy": bool(vpx.get("detectNfozzy", False)),
            "detectFleep": bool(vpx.get("detectFleep", False)),
            "detectSSF": bool(vpx.get("detectSSF", False)),
            "detectLUT": bool(vpx.get("detectLUT", False)),
            "detectScorebit": bool(vpx.get("detectScorebit", False)),
            "detectFastflips": bool(vpx.get("detectFastflips", False)),
            "detectFlex": bool(vpx.get("detectFlex", False)),
        },
        "vpinfe": {
            "alttitle": str(vpinfe.get("alttitle", "") or ""),
            "altvpsid": str(vpinfe.get("altvpsid", "") or ""),
        },
    }


def sync_installed_tables(
    service_ip: str,
    user_id: str,
    machine_id: str,
    table_root_dir: str,
    timeout_seconds: int = 30,
) -> dict:
    endpoint = _normalize_service_endpoint(service_ip)
    user_id = str(user_id or "").strip()
    machine_id = str(machine_id or "").strip()
    table_root_dir = str(table_root_dir or "").strip()

    if not user_id:
        raise ValueError("User ID is required.")
    if not machine_id:
        raise ValueError("Machine ID is required.")
    if not table_root_dir:
        raise ValueError("Tables Directory is required.")

    table_root = Path(table_root_dir)
    if not table_root.exists() or not table_root.is_dir():
        raise ValueError(f"Tables Directory does not exist: {table_root_dir}")

    parser = TableParser(table_root_dir)
    parser.loadTables(reload=True)
    tables = parser.getAllTables()

    payload_tables = []
    skipped = 0
    for table in tables:
        meta = table.metaConfig if isinstance(table.metaConfig, dict) else {}
        table_payload = _build_table_payload(meta)
        if table_payload is None:
            skipped += 1
            continue
        payload_tables.append(table_payload)

    payload = {
        "source": {
            "program": "VPinFE",
            "programVersion": get_version(),
        },
        "client": {
            "userId": user_id,
            "machineId": machine_id,
        },
        "sentAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "tables": payload_tables,
    }

    logger.info(
        "Syncing %s table(s) to %s for user=%s (skipped=%s)",
        len(payload_tables),
        endpoint,
        user_id,
        skipped,
    )

    response = requests.post(endpoint, json=payload, timeout=timeout_seconds)
    response_body = response.text
    try:
        response_json = response.json()
        response_body = json.dumps(response_json, indent=2)
    except Exception:
        response_json = None

    return {
        "endpoint": endpoint,
        "tables_scanned": len(tables),
        "tables_sent": len(payload_tables),
        "tables_skipped": skipped,
        "status_code": response.status_code,
        "ok": response.ok,
        "response_body": response_body,
        "response_json": response_json,
    }


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def sync_on_shutdown(iniconfig, timeout_seconds: int = 10) -> dict | None:
    section = "vpinplay"
    if not iniconfig.config.has_section(section):
        logger.info("Skipping VPinPlay shutdown sync: [%s] section not found.", section)
        return None

    enabled = _as_bool(iniconfig.config.get(section, "synconexit", fallback="false"))
    if not enabled:
        logger.info("Skipping VPinPlay shutdown sync: vpinplay.synconexit is false.")
        return None

    service_ip = iniconfig.config.get(section, "apiendpoint", fallback="").strip()
    user_id = iniconfig.config.get(section, "userid", fallback="").strip()
    machine_id = iniconfig.config.get(section, "machineid", fallback="").strip()
    table_root_dir = iniconfig.config.get("Settings", "tablerootdir", fallback="").strip()

    if not service_ip or not user_id or not machine_id or not table_root_dir:
        logger.warning(
            "Skipping VPinPlay shutdown sync: missing required settings "
            "(apiendpoint=%s, userid=%s, machineid=%s, tablerootdir=%s).",
            bool(service_ip),
            bool(user_id),
            bool(machine_id),
            bool(table_root_dir),
        )
        return None

    try:
        result = sync_installed_tables(
            service_ip=service_ip,
            user_id=user_id,
            machine_id=machine_id,
            table_root_dir=table_root_dir,
            timeout_seconds=timeout_seconds,
        )
        logger.info(
            "VPinPlay shutdown sync complete: status=%s sent=%s skipped=%s",
            result.get("status_code"),
            result.get("tables_sent"),
            result.get("tables_skipped"),
        )
        if not result.get("ok"):
            logger.warning("VPinPlay shutdown sync failed response: %s", result.get("response_body"))
        return result
    except Exception:
        logger.exception("VPinPlay shutdown sync failed")
        return None
