from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from typing import Any


PROFILE_TYPE = "vpinplay_identity"
PROFILE_VERSION = 1


@dataclass(frozen=True)
class AlternateVPinPlayProfile:
    profile_key: str
    user_id: str
    initials: str
    machine_id: str
    source_name: str = ""
    activated_at: int = 0


_LOCK = threading.Lock()
_PROFILES: dict[str, AlternateVPinPlayProfile] = {}
_ACTIVE_PROFILE_KEY: str | None = None
_TABLE_USER_STATE_BY_PROFILE: dict[str, dict[str, dict[str, Any]]] = {}


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("QR payload must be a JSON object.")

    profile_type = str(payload.get("type", "") or "").strip()
    version_raw = payload.get("version", 0)
    user_id = str(payload.get("userId", "") or "").strip()
    initials = str(payload.get("initials", "") or "").strip().upper()
    machine_id = str(payload.get("machineId", "") or "").strip()

    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        raise ValueError("QR payload version is invalid.") from None

    if profile_type != PROFILE_TYPE:
        raise ValueError(f"Unsupported QR payload type: {profile_type or 'missing'}.")
    if version != PROFILE_VERSION:
        raise ValueError(f"Unsupported QR payload version: {version}.")
    if not user_id:
        raise ValueError("QR payload is missing userId.")
    if not initials:
        raise ValueError("QR payload is missing initials.")
    if len(initials) > 3:
        raise ValueError("QR payload initials must be 3 characters or fewer.")
    if not machine_id:
        raise ValueError("QR payload is missing machineId.")

    return {
        "type": profile_type,
        "version": version,
        "userId": user_id,
        "initials": initials,
        "machineId": machine_id,
    }


def _build_profile_key(user_id: str, machine_id: str) -> str:
    return f"{str(user_id or '').strip()}::{str(machine_id or '').strip()}"


def _profile_to_dict(profile: AlternateVPinPlayProfile) -> dict[str, Any]:
    table_states = _TABLE_USER_STATE_BY_PROFILE.get(profile.profile_key, {})
    return {
        "profileKey": profile.profile_key,
        "userId": profile.user_id,
        "initials": profile.initials,
        "machineId": profile.machine_id,
        "sourceName": profile.source_name,
        "activatedAt": profile.activated_at,
        "trackedTables": len(table_states),
    }


def validate_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _normalize_payload(payload)


def activate_alternate_profile(payload: dict[str, Any], source_name: str = "") -> dict[str, Any]:
    normalized = _normalize_payload(payload)
    activated_at = int(time.time())
    profile_key = _build_profile_key(normalized["userId"], normalized["machineId"])
    profile = AlternateVPinPlayProfile(
        profile_key=profile_key,
        user_id=normalized["userId"],
        initials=normalized["initials"],
        machine_id=normalized["machineId"],
        source_name=str(source_name or "").strip(),
        activated_at=activated_at,
    )
    with _LOCK:
        global _ACTIVE_PROFILE_KEY
        _PROFILES[profile_key] = profile
        _TABLE_USER_STATE_BY_PROFILE.setdefault(profile_key, {})
        _ACTIVE_PROFILE_KEY = profile_key
    return get_alternate_profile_state()


def set_active_profile(profile_key: str) -> dict[str, Any]:
    normalized_key = str(profile_key or "").strip()
    with _LOCK:
        global _ACTIVE_PROFILE_KEY
        if not normalized_key or normalized_key not in _PROFILES:
            raise ValueError("Alternate VPinPlay player was not found.")
        _ACTIVE_PROFILE_KEY = normalized_key
    return get_alternate_profile_state()


def clear_alternate_profile(profile_key: str | None = None) -> dict[str, Any]:
    with _LOCK:
        global _ACTIVE_PROFILE_KEY
        if profile_key is None:
            _PROFILES.clear()
            _TABLE_USER_STATE_BY_PROFILE.clear()
            _ACTIVE_PROFILE_KEY = None
        else:
            normalized_key = str(profile_key or "").strip()
            if normalized_key:
                _PROFILES.pop(normalized_key, None)
                _TABLE_USER_STATE_BY_PROFILE.pop(normalized_key, None)
                if _ACTIVE_PROFILE_KEY == normalized_key:
                    _ACTIVE_PROFILE_KEY = next(iter(_PROFILES.keys()), None)
    return get_alternate_profile_state()


def get_alternate_profile_state() -> dict[str, Any]:
    with _LOCK:
        active_profile = _PROFILES.get(_ACTIVE_PROFILE_KEY) if _ACTIVE_PROFILE_KEY else None
        profiles = [_profile_to_dict(profile) for profile in _PROFILES.values()]
        profiles.sort(key=lambda item: (item.get("userId") or "").lower())
        active_table_count = len(_TABLE_USER_STATE_BY_PROFILE.get(_ACTIVE_PROFILE_KEY or "", {}))
        return {
            "active": active_profile is not None,
            "profile": _profile_to_dict(active_profile) if active_profile is not None else None,
            "active_tables": active_table_count,
            "profiles": profiles,
            "activeProfileKey": active_profile.profile_key if active_profile is not None else "",
        }


def get_active_profile() -> AlternateVPinPlayProfile | None:
    with _LOCK:
        return _PROFILES.get(_ACTIVE_PROFILE_KEY) if _ACTIVE_PROFILE_KEY else None


def has_active_profile() -> bool:
    return get_active_profile() is not None


def _ensure_profile_table_state(profile_key: str) -> dict[str, dict[str, Any]]:
    return _TABLE_USER_STATE_BY_PROFILE.setdefault(profile_key, {})


def _ensure_table_user_state(profile_key: str, table_key: str) -> dict[str, Any]:
    profile_state = _ensure_profile_table_state(profile_key)
    state = profile_state.setdefault(
        table_key,
        {
            "Rating": 0,
            "Favorite": 0,
            "LastRun": None,
            "StartCount": 0,
            "RunTime": 0,
            "Tags": [],
            "FrontendDOFEvent": "",
        },
    )
    return state


def record_table_start(table_key: str, played_at: int | None = None) -> dict[str, Any]:
    timestamp = int(played_at or time.time())
    with _LOCK:
        if _ACTIVE_PROFILE_KEY is None:
            return {}
        state = _ensure_table_user_state(_ACTIVE_PROFILE_KEY, table_key)
        try:
            state["StartCount"] = int(state.get("StartCount", 0)) + 1
        except (TypeError, ValueError):
            state["StartCount"] = 1
        state["LastRun"] = timestamp
        return copy.deepcopy(state)


def add_table_runtime(table_key: str, elapsed_seconds: float, profile_key: str | None = None) -> dict[str, Any]:
    session_minutes = int((max(0.0, float(elapsed_seconds)) + 59) // 60)
    with _LOCK:
        resolved_profile_key = str(profile_key or _ACTIVE_PROFILE_KEY or "").strip()
        if not resolved_profile_key:
            return {}
        state = _ensure_table_user_state(resolved_profile_key, table_key)
        try:
            prior_runtime = int(state.get("RunTime", 0))
        except (TypeError, ValueError):
            prior_runtime = 0
        state["RunTime"] = prior_runtime + session_minutes
        return copy.deepcopy(state)


def set_table_score(table_key: str, score_data: Any, profile_key: str | None = None) -> dict[str, Any]:
    with _LOCK:
        resolved_profile_key = str(profile_key or _ACTIVE_PROFILE_KEY or "").strip()
        if not resolved_profile_key:
            return {}
        state = _ensure_table_user_state(resolved_profile_key, table_key)
        state["Score"] = score_data
        return copy.deepcopy(state)


def get_table_user_state(table_key: str, profile_key: str | None = None) -> dict[str, Any]:
    with _LOCK:
        resolved_profile_key = str(profile_key or _ACTIVE_PROFILE_KEY or "").strip()
        if not resolved_profile_key:
            return {}
        state = _ensure_table_user_state(resolved_profile_key, table_key)
        return copy.deepcopy(state)
