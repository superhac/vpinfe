from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

from common import table_play_service
from common.config_access import SettingsConfig, VPinPlayConfig
from common.vpinplay_runtime import (
    add_table_runtime,
    get_active_profile,
    get_table_user_state,
    record_table_start,
    set_table_score,
)
from common.vpinplay_service import sync_single_table_meta


logger = logging.getLogger("vpinfe.frontend.launch_service")


def _submit_alternate_vpinplay_result(api, table, elapsed_seconds: float, profile) -> None:
    if profile is None:
        return

    table_key = str(table.fullPathTable or table.tableDirName or "")
    if not table_key:
        logger.warning("Skipping alternate VPinPlay submission: missing table key")
        return

    add_table_runtime(table_key, elapsed_seconds, profile.profile_key)
    score_data, score_path = table_play_service.parse_score_from_nvram(table)
    if score_data:
        set_table_score(table_key, score_data, profile.profile_key)
        logger.info("Captured alternate User.Score for %s from %s", table.tableDirName, score_path)

    table_meta = table_play_service.build_runtime_submission_meta(
        table,
        get_table_user_state(table_key, profile.profile_key),
    )
    if not table_meta:
        return

    vpinplay = VPinPlayConfig.from_config(api._iniConfig)
    if not vpinplay.api_endpoint:
        logger.warning("Skipping alternate VPinPlay submission: API endpoint is not configured.")
        return

    try:
        result = sync_single_table_meta(
            service_ip=vpinplay.api_endpoint,
            user_id=profile.user_id,
            initials=profile.initials,
            machine_id=profile.machine_id,
            table_meta=table_meta,
        )
        logger.info(
            "Alternate VPinPlay submit complete for %s: status=%s ok=%s",
            table.tableDirName,
            result.get("status_code"),
            result.get("ok"),
        )
        if not result.get("ok"):
            logger.warning("Alternate VPinPlay submit failed response: %s", result.get("response_body"))
    except Exception:
        logger.exception("Alternate VPinPlay submit failed for %s", table.tableDirName)


def launch_table(
    api,
    index,
    *,
    get_effective_launcher,
    build_vpx_launch_command,
    parse_launch_env_overrides,
    resolve_launch_tableini_override,
    stop_dof_service,
    stop_libdmdutil_service,
    start_dof_service_if_enabled,
    popen=subprocess.Popen,
) -> None:
    table = api.filteredTables[index]
    vpx = table.fullPathVPXfile
    settings = SettingsConfig.from_config(api._iniConfig)
    vpxbin = settings.vpx_bin_path
    vpxbin_path, source_key, _ = get_effective_launcher(vpxbin, table.metaConfig)
    if not vpxbin_path:
        logger.warning("No launcher configured (checked VPinFE.%s and Settings.vpxbinpath)", source_key)
        return
    if not vpxbin_path.exists():
        logger.warning("Launcher not found (%s): %s", source_key, vpxbin_path)
        return

    table_play_service.track_table_play(table)
    api.send_event_all_windows_incself({"type": "TableLaunching"})

    stop_dof_service()
    stop_libdmdutil_service(clear=False)
    launch_started_at = None
    launch_profile = None
    try:
        global_ini_override = settings.global_ini_override
        tableini_override = resolve_launch_tableini_override(
            vpx,
            settings.global_table_ini_override_enabled,
            settings.global_table_ini_override_mask,
        )
        cmd = build_vpx_launch_command(
            launcher_path=str(vpxbin_path),
            vpx_table_path=vpx,
            global_ini_override=global_ini_override,
            tableini_override=tableini_override,
        )
        logger.info("Launching: %s", cmd)
        launch_env = os.environ.copy()
        launch_env.update(parse_launch_env_overrides(settings.vpx_launch_env))

        process = popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env=launch_env,
        )
        launch_started_at = time.time()
        launch_profile = get_active_profile()
        if launch_profile is not None:
            record_table_start(str(table.fullPathTable or table.tableDirName or ""))
        else:
            table_play_service.increment_start_count(table)

        startup_detected = False
        for line in process.stdout:
            if not startup_detected and "Startup done" in line:
                startup_detected = True
                api.send_event_all_windows_incself({"type": "TableRunning"})
                logger.info("table running")

        process.wait()
    finally:
        start_dof_service_if_enabled(api._iniConfig)

    if launch_started_at is not None:
        elapsed_seconds = max(0.0, time.time() - launch_started_at)
        if launch_profile is not None:
            _submit_alternate_vpinplay_result(api, table, elapsed_seconds, launch_profile)
        else:
            table_play_service.add_runtime_minutes(table, elapsed_seconds)
            table_play_service.update_score_from_nvram(table)

    if sys.platform == "darwin" and api.frontend_browser:
        api.frontend_browser.activate_all_mac()

    table_play_service.delete_nvram_if_configured(table)
    api.send_event_all_windows_incself({"type": "TableLaunchComplete"})
