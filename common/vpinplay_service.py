import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from common.app_version import get_version
from common.config_access import SettingsConfig, VPinPlayConfig
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


def _normalize_score(value):
    return value if isinstance(value, dict) else None


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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
            "score": _normalize_score(user.get("Score")),
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
            "detectnfozzy": bool(vpx.get("detectnfozzy", False)),
            "detectfleep": bool(vpx.get("detectfleep", False)),
            "detectssf": bool(vpx.get("detectssf", False)),
            "detectlut": bool(vpx.get("detectlut", False)),
            "detectscorebit": bool(vpx.get("detectscorebit", False)),
            "detectfastflips": bool(vpx.get("detectfastflips", False)),
            "detectflex": bool(vpx.get("detectflex", False)),
        },
        "vpinfe": {
            "alttitle": str(vpinfe.get("alttitle", "") or ""),
            "altvpsid": str(vpinfe.get("altvpsid", "") or ""),
        },
    }


def _build_sync_payload(user_id: str, initials: str, machine_id: str, tables: list[dict]) -> dict:
    return {
        "source": {
            "program": "VPinFE",
            "programVersion": get_version(),
        },
        "client": {
            "userId": user_id,
            "initials": initials,
            "machineId": machine_id,
        },
        "sentAt": _utc_now_iso(),
        "tables": tables,
    }


def _post_sync_payload(endpoint: str, payload: dict, timeout_seconds: int) -> dict:
    response = requests.post(endpoint, json=payload, timeout=timeout_seconds)
    response_body = response.text
    try:
        response_json = response.json()
        response_body = json.dumps(response_json, indent=2)
    except Exception:
        response_json = None

    return {
        "endpoint": endpoint,
        "status_code": response.status_code,
        "ok": response.ok,
        "response_body": response_body,
        "response_json": response_json,
        "payload": payload,
    }


def sync_installed_tables(
    service_ip: str,
    user_id: str,
    initials: str,
    machine_id: str,
    table_root_dir: str,
    timeout_seconds: int = 30,
) -> dict:
    endpoint = _normalize_service_endpoint(service_ip)
    user_id = str(user_id or "").strip()
    initials = str(initials or "").strip()
    machine_id = str(machine_id or "").strip()
    table_root_dir = str(table_root_dir or "").strip()

    if not user_id:
        raise ValueError("User ID is required.")
    if not initials:
        raise ValueError("Initials is required.")
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

    payload = _build_sync_payload(user_id, initials, machine_id, payload_tables)

    logger.info(
        "Syncing %s table(s) to %s for user=%s (skipped=%s)",
        len(payload_tables),
        endpoint,
        user_id,
        skipped,
    )

    post_result = _post_sync_payload(endpoint, payload, timeout_seconds)

    return {
        "tables_scanned": len(tables),
        "tables_sent": len(payload_tables),
        "tables_skipped": skipped,
        **post_result,
    }


def sync_single_table_meta(
    service_ip: str,
    user_id: str,
    initials: str,
    machine_id: str,
    table_meta: dict,
    timeout_seconds: int = 30,
) -> dict:
    endpoint = _normalize_service_endpoint(service_ip)
    user_id = str(user_id or "").strip()
    initials = str(initials or "").strip()
    machine_id = str(machine_id or "").strip()

    if not user_id:
        raise ValueError("User ID is required.")
    if not initials:
        raise ValueError("Initials is required.")
    if not machine_id:
        raise ValueError("Machine ID is required.")
    if not isinstance(table_meta, dict):
        raise ValueError("Table metadata is required.")

    table_payload = _build_table_payload(table_meta)
    if table_payload is None:
        raise ValueError("Table metadata is missing VPSId.")

    payload = _build_sync_payload(user_id, initials, machine_id, [table_payload])
    logger.info("Syncing alternate VPinPlay payload for user=%s to %s", user_id, endpoint)
    result = _post_sync_payload(endpoint, payload, timeout_seconds)
    return {
        "tables_scanned": 1,
        "tables_sent": 1,
        "tables_skipped": 0,
        **result,
    }


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def sync_on_shutdown(iniconfig, timeout_seconds: int = 10) -> dict | None:
    section = "vpinplay"
    if not iniconfig.config.has_section("vpinplay"):
        logger.info("Skipping VPinPlay shutdown sync: [%s] section not found.", section)
        return None

    vpinplay = VPinPlayConfig.from_config(iniconfig)
    settings = SettingsConfig.from_config(iniconfig)
    if not vpinplay.sync_on_exit:
        logger.info("Skipping VPinPlay shutdown sync: vpinplay.synconexit is false.")
        return None

    service_ip = vpinplay.api_endpoint
    user_id = vpinplay.user_id
    initials = vpinplay.initials
    machine_id = vpinplay.machine_id
    table_root_dir = settings.table_root_dir

    if not service_ip or not user_id or not initials or not machine_id or not table_root_dir:
        logger.warning(
            "Skipping VPinPlay shutdown sync: missing required settings "
            "(apiendpoint=%s, userid=%s, initials=%s, machineid=%s, tablerootdir=%s).",
            bool(service_ip),
            bool(user_id),
            bool(initials),
            bool(machine_id),
            bool(table_root_dir),
        )
        return None

    try:
        result = sync_installed_tables(
            service_ip=service_ip,
            user_id=user_id,
            initials=initials,
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
