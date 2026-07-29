from __future__ import annotations

import logging
import os

from common.config_access import MediaConfig, SettingsConfig
from common.iniconfig import IniConfig
from common.jobs import JobReporter
from common.media_paths import MEDIA_SPECS, resolve_media_files
from common.tables.metaconfig import MetaConfig
from common.paths import get_ini_config
from common.tables.standalonescripts import StandaloneScripts
from common.tables.tableparser import TableParser
from common.online.vpsdb import VPSdb
from common.tables.vpxparser import VPXParser


logger = logging.getLogger("vpinfe.common.tables.metadata_service")


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

    # Claim whatever actually resolves, not just the canonical filename. Asking the
    # resolver is the only way a hand-placed wheel.jpg, a spec-named
    # "(Wheel) <build>.png" or a file at the folder root gets claimed - checking
    # medias/wheel.png alone left every one of them unclaimed, and therefore still
    # replaceable by the next media download.
    table_dir = table.fullPathTable
    medias_dir = os.path.join(table_dir, "medias")
    try:
        table_contents = {entry.name for entry in os.scandir(table_dir) if entry.is_file()}
    except OSError:
        table_contents = set()
    medias_contents = set()
    for root, _dirs, files in os.walk(medias_dir):
        rel = os.path.relpath(root, medias_dir)
        prefix = "" if rel == "." else f"{rel.replace(os.sep, '/')}/"
        for filename in files:
            medias_contents.add(f"{prefix}{filename}")

    resolved = resolve_media_files(table_dir, table_contents, medias_contents, tabletype)

    meta = MetaConfig(info_path)
    claimed = 0

    for spec in MEDIA_SPECS:
        if spec.key == "audio" or (spec.key == "fss" and tabletype != "fss"):
            continue
        path = resolved.get(spec.key)
        if path is None:
            continue
        # A record, not a control. The download path used to consult this before
        # skipping a kind; it compares hashes now (common/online/vpsdb_media.py),
        # so a user's artwork is protected whether or not it was ever claimed.
        # What a claim still buys is a record of what came from where.
        media_key = (tabletype if spec.key == "table"
                     else f"{tabletype}_video" if spec.key == "table_video" else spec.key)
        existing = meta.getMedia(media_key)
        if existing and existing.get("Source") == "user":
            continue
        meta.addMedia(media_key, "user", str(path), "")
        log(f"  Claimed {media_key} ({path.name}) as user media")
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
