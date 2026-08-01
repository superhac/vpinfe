import json
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

from common.app_version import get_version
from common.config_access import SettingsConfig, VPinPlayConfig
from common.tables.table_metadata import default_game_file, normalize_rating, vpinfe_section
from common.tables.tableparser import TableParser
from common.timestamps import utc_now_iso


logger = logging.getLogger("vpinfe.common.online.vpinplay_service")


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


def _build_table_payload(meta: dict) -> dict | None:
    """One table in the shape the VPinPlay service accepts.

    This is an adapter, and the only place the service's vocabulary belongs: every key
    and every bound here is theirs, read from a value that is ours. Their models reject
    nothing they do not recognize, so a name that drifts is dropped in silence.
    """
    info = meta.get("Info", {}) if isinstance(meta.get("Info"), dict) else {}
    user = meta.get("User", {}) if isinstance(meta.get("User"), dict) else {}
    gf_name, vpx = default_game_file(meta)
    vpinfe = vpinfe_section(meta)

    vps_id = str(info.get("VPSId", "") or "").strip()
    if not vps_id:
        return None

    return {
        "info": {
            "vpsId": vps_id,
            "rom": str(vpx.get("rom", "") or ""),
        },
        "user": {
            # Their bound is 0-5, and one table outside it fails the whole request.
            "rating": normalize_rating(user.get("Rating", 0)),
            "lastRun": _normalize_last_run(user.get("LastRun")),
            "startCount": _to_int(user.get("StartCount", 0), default=0),
            "runTime": _to_int(user.get("RunTime", 0), default=0),
            "score": _normalize_score(user.get("Score")),
        },
        "vpxFile": {
            "filename": gf_name,
            "filehash": str(vpx.get("file_hash", "") or ""),
            "version": str(vpx.get("version", "") or ""),
            # ISO since 9c6ba14, where 2.x sent the author's raw string. Stored there
            # without being parsed, but it is part of how they key a variation.
            "releaseDate": str(vpx.get("release_date", "") or ""),
            "saveDate": str(vpx.get("save_date", "") or ""),
            "saveRev": str(vpx.get("save_rev", "") or ""),
            "manufacturer": str(vpx.get("manufacturer", "") or ""),
            "year": str(vpx.get("year", "") or ""),
            "type": str(vpx.get("type", "") or ""),
            "vbsHash": str(vpx.get("vbs_hash", "") or ""),
            "rom": str(vpx.get("rom", "") or ""),
            "detectNfozzy": bool(vpx.get("detect_nfozzy", False)),
            "detectFleep": bool(vpx.get("detect_fleep", False)),
            "detectSSF": bool(vpx.get("detect_ssf", False)),
            "detectLUT": bool(vpx.get("detect_lut", False)),
            # Scorbit is the product; the service spells its field Scorebit.
            "detectScorebit": bool(vpx.get("detect_scorbit", False)),
            "detectFastflips": bool(vpx.get("detect_fastflips", False)),
            "detectFlex": bool(vpx.get("detect_flex", False)),
        },
        "vpinfe": {
            "alttitle": str(vpinfe.get("alt_title", "") or ""),
            "altvpsid": str(vpinfe.get("alt_vpsid", "") or ""),
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
        "sentAt": utc_now_iso(),
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

    game_root = Path(table_root_dir)
    if not game_root.exists() or not game_root.is_dir():
        raise ValueError(f"Tables Directory does not exist: {table_root_dir}")

    parser = TableParser(table_root_dir)
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
