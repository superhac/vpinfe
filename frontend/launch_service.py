from __future__ import annotations

import logging
import os
import subprocess
import sys
import time


logger = logging.getLogger("vpinfe.frontend.launch_service")


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
    vpxbin = api._iniConfig.config["Settings"].get("vpxbinpath", "")
    vpxbin_path, source_key, _ = get_effective_launcher(vpxbin, table.metaConfig)
    if not vpxbin_path:
        logger.warning("No launcher configured (checked VPinFE.%s and Settings.vpxbinpath)", source_key)
        return
    if not vpxbin_path.exists():
        logger.warning("Launcher not found (%s): %s", source_key, vpxbin_path)
        return

    api._track_table_play(table)
    api.send_event_all_windows_incself({"type": "TableLaunching"})

    stop_dof_service()
    stop_libdmdutil_service(clear=False)
    launch_started_at = None
    try:
        global_ini_override = api._iniConfig.config["Settings"].get("globalinioverride", "").strip()
        tableini_override = resolve_launch_tableini_override(
            vpx,
            api._iniConfig.config["Settings"].get("globaltableinioverrideenabled", "false"),
            api._iniConfig.config["Settings"].get("globaltableinioverridemask", ""),
        )
        cmd = build_vpx_launch_command(
            launcher_path=str(vpxbin_path),
            vpx_table_path=vpx,
            global_ini_override=global_ini_override,
            tableini_override=tableini_override,
        )
        logger.info("Launching: %s", cmd)
        launch_env = os.environ.copy()
        launch_env.update(parse_launch_env_overrides(api._iniConfig.config["Settings"].get("vpxlaunchenv", "")))

        process = popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env=launch_env,
        )
        launch_started_at = time.time()
        api._increment_user_start_count(table)

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
        api._add_user_runtime_minutes(table, elapsed_seconds)
        api._update_user_score_from_nvram(table)

    if sys.platform == "darwin" and api.frontend_browser:
        api.frontend_browser.activate_all_mac()

    api._delete_nvram_if_configured(table)
    api.send_event_all_windows_incself({"type": "TableLaunchComplete"})
