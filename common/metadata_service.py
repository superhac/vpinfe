from __future__ import annotations

import logging
import os

from common.config_access import MediaConfig, SettingsConfig
from common.iniconfig import IniConfig
from common.jobs import JobReporter
from common.media_paths import media_filename_map
from common.metaconfig import MetaConfig
from common.paths import get_ini_config
from common.standalonescripts import StandaloneScripts
from common.tableparser import TableParser
from common.vpsdb import VPSdb
from common.vpxparser import VPXParser


logger = logging.getLogger("vpinfe.common.metadata_service")


def _config(config: IniConfig | None = None) -> IniConfig:
    return config or get_ini_config()


def build_metadata(
    downloadMedia: bool = True,
    updateAll: bool = True,
    tableName: str | None = None,
    userMedia: bool = False,
    progress_cb=None,
    log_cb=None,
    iniconfig: IniConfig | None = None,
):
    config = _config(iniconfig)

    reporter = JobReporter(logger, progress_cb=progress_cb, log_cb=log_cb)
    log = reporter.log

    not_found_tables = 0
    parservpx = VPXParser()

    settings = SettingsConfig.from_config(config)
    media_config = MediaConfig.from_config(config)

    tp = TableParser(settings.table_root_dir, config)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()

    if tableName:
        tables = [table for table in tables if table.tableDirName == tableName]
        if not tables:
            log(f"Table folder '{tableName}' not found")
            return {"found": 0, "not_found": 0}
        log(f"Processing single table: {tableName}")

    total = len(tables)

    vps = VPSdb(settings.table_root_dir, config)
    log(f"Found {len(vps)} tables in VPSdb")

    if progress_cb:
        reporter.progress(0, total, "Starting")

    for current, table in enumerate(tables, 1):
        info_path = os.path.join(table.fullPathTable, f"{table.tableDirName}.info")

        if os.path.exists(info_path) and not updateAll:
            if progress_cb:
                reporter.progress(current, total, f"Skipping {table.tableDirName}")
            continue

        meta = MetaConfig(info_path)

        log(f"Checking VPSdb for {table.tableDirName}")
        if progress_cb:
            reporter.progress(current, total, f"Processing {table.tableDirName}")

        vpsSearchData = vps.parseTableNameFromDir(table.tableDirName)
        vpsData = (
            vps.lookupName(
                vpsSearchData["name"],
                vpsSearchData["manufacturer"],
                vpsSearchData["year"],
            )
            if vpsSearchData
            else None
        )

        if not vpsData:
            log("  - Not found in VPS")
            not_found_tables += 1
            continue

        log(f"Parsing VPX file: {table.fullPathVPXfile}")
        vpxData = parservpx.singleFileExtract(table.fullPathVPXfile)

        if not vpxData:
            log(f"  - VPX file not found or failed to parse: {table.fullPathVPXfile}")
            not_found_tables += 1
            continue

        meta.writeConfigMeta({
            "vpsdata": vpsData,
            "vpxdata": vpxData,
        })

        log(f"Created {table.tableDirName}.info")

        if userMedia:
            claimed = claim_media_for_table(table, media_config.table_type, log)
            if claimed:
                log(f"  Claimed {claimed} media file(s) as user-sourced")
        elif downloadMedia:
            try:
                vps.downloadMediaForTable(table, vpsData["id"], metaConfig=meta)
                log("Downloaded media")
            except KeyError:
                log("No media found")

    if progress_cb:
        reporter.progress(total, total, "Complete")

    return {"found": total, "not_found": not_found_tables}


def apply_vpx_patches(progress_cb=None, iniconfig: IniConfig | None = None):
    config = _config(iniconfig)
    settings = SettingsConfig.from_config(config)
    tp = TableParser(settings.table_root_dir, config)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()
    StandaloneScripts(tables, progress_cb=progress_cb)


def claim_media_for_table(table, tabletype, log=None):
    log = log or logger.info
    info_path = os.path.join(table.fullPathTable, f"{table.tableDirName}.info")
    if not os.path.exists(info_path):
        log(f"  Skipping {table.tableDirName}: no .info file")
        return 0

    media_files = {
        key: filename
        for key, filename in media_filename_map(tabletype).items()
        if key != "audio" and (key != "fss" or tabletype == "fss")
    }

    medias_dir = os.path.join(table.fullPathTable, "medias")
    meta = MetaConfig(info_path)
    claimed = 0

    for media_key, filename in media_files.items():
        filepath = os.path.join(medias_dir, filename)
        if os.path.exists(filepath):
            existing = meta.getMedia(media_key)
            if existing and existing.get("Source") == "user":
                continue
            meta.addMedia(media_key, "user", filepath, "")
            log(f"  Claimed {media_key} ({filename}) as user media")
            claimed += 1

    return claimed


def claim_user_media(tableName=None, progress_cb=None, log_cb=None, iniconfig: IniConfig | None = None):
    config = _config(iniconfig)

    reporter = JobReporter(logger, progress_cb=progress_cb, log_cb=log_cb)
    log = reporter.log

    settings = SettingsConfig.from_config(config)
    media_config = MediaConfig.from_config(config)

    tp = TableParser(settings.table_root_dir, config)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()

    if tableName:
        tables = [table for table in tables if table.tableDirName == tableName]
        if not tables:
            log(f"Table folder '{tableName}' not found")
            return {"tables_processed": 0, "media_claimed": 0}
        log(f"Processing single table: {tableName}")

    total = len(tables)
    total_claimed = 0

    if progress_cb:
        reporter.progress(0, total, "Starting")

    for current, table in enumerate(tables, 1):
        log(f"Scanning {table.tableDirName}")
        if progress_cb:
            reporter.progress(current, total, f"Scanning {table.tableDirName}")
        total_claimed += claim_media_for_table(table, media_config.table_type, log)

    if progress_cb:
        reporter.progress(total, total, "Complete")

    log(f"\nDone. Scanned {total} tables, claimed {total_claimed} media files as user-sourced.")
    return {"tables_processed": total, "media_claimed": total_claimed}
