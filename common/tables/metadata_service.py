from __future__ import annotations

import logging
import os

from common.config_access import SettingsConfig
from common.iniconfig import IniConfig
from common.jobs import JobReporter
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

    tp = TableParser(settings.table_root_dir, config)
    tables = tp.getAllTables()

    if tableName:
        tables = [game for game in tables if game.tableDirName == tableName]
        if not tables:
            log(f"Table folder '{tableName}' not found")
            return {"found": 0, "not_found": 0}
        log(f"Processing single table: {tableName}")

    total = len(tables)

    vps = VPSdb(settings.table_root_dir, config)
    log(f"Found {len(vps)} tables in VPSdb")

    if progress_cb:
        reporter.progress(0, total, "Starting")

    for current, game in enumerate(tables, 1):
        info_path = os.path.join(game.fullPathTable, f"{game.tableDirName}.info")

        if os.path.exists(info_path) and not updateAll:
            if progress_cb:
                reporter.progress(current, total, f"Skipping {game.tableDirName}")
            continue

        meta = MetaConfig(info_path)

        log(f"Checking VPSdb for {game.tableDirName}")
        if progress_cb:
            reporter.progress(current, total, f"Processing {game.tableDirName}")

        vpsSearchData = vps.parseTableNameFromDir(game.tableDirName)
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

        log(f"Parsing VPX file: {game.fullPathVPXfile}")
        vpxData = parservpx.singleFileExtract(game.fullPathVPXfile)

        if not vpxData:
            log(f"  - VPX file not found or failed to parse: {game.fullPathVPXfile}")
            not_found_tables += 1
            continue

        meta.writeConfigMeta({
            "vpsdata": vpsData,
            "vpxdata": vpxData,
        })

        log(f"Created {game.tableDirName}.info")

        # userMedia suppresses the fetch outright, for somebody supplying the whole
        # library themselves. Media already on disk needs no such flag: the
        # downloader compares hashes and leaves anything it cannot prove is ours
        # alone (common/online/vpsdb_media.py).
        if downloadMedia and not userMedia:
            try:
                vps.downloadMediaForTable(game, vpsData["id"], metaConfig=meta)
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
    tables = tp.getAllTables()
    StandaloneScripts(tables, progress_cb=progress_cb)
