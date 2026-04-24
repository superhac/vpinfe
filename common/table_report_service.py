from __future__ import annotations

import logging

from common.iniconfig import IniConfig
from common.paths import get_ini_config
from common.tableparser import TableParser
from common.vpsdb import VPSdb


logger = logging.getLogger("vpinfe.common.table_report_service")


def _config(config: IniConfig | None = None) -> IniConfig:
    return config or get_ini_config()


def list_missing_tables(iniconfig: IniConfig | None = None, log=None) -> None:
    config = _config(iniconfig)
    log = log or logger.info
    table_root = config.config["Settings"]["tablerootdir"]
    tp = TableParser(table_root, config)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()
    log("Listing tables missing from %s", table_root)
    log("Found %s tables in %s", len(tables), table_root)

    vps = VPSdb(table_root, config)
    log("Found %s tables in VPSdb", len(vps))

    tables_found = []
    for table in tables:
        vps_search_data = vps.parseTableNameFromDir(table.tableDirName)
        vps_data = (
            vps.lookupName(
                vps_search_data["name"],
                vps_search_data["manufacturer"],
                vps_search_data["year"],
            )
            if vps_search_data
            else None
        )
        if vps_data:
            tables_found.append(vps_data)

    current = 0
    for vps_table in vps.tables():
        if vps_table not in tables_found:
            current += 1
            log(
                "Missing table %s: %s (%s %s)",
                current,
                vps_table["name"],
                vps_table["manufacturer"],
                vps_table["year"],
            )


def list_unknown_tables(iniconfig: IniConfig | None = None, log=None) -> None:
    config = _config(iniconfig)
    log = log or logger.info
    table_root = config.config["Settings"]["tablerootdir"]
    tp = TableParser(table_root, config)
    tp.loadTables(reload=True)
    tables = tp.getAllTables()
    log("Listing unknown tables from %s", table_root)
    log("Found %s tables in %s", len(tables), table_root)

    vps = VPSdb(table_root, config)
    log("Found %s tables in VPSdb", len(vps))

    current = 0
    for table in tables:
        vps_search_data = vps.parseTableNameFromDir(table.tableDirName)
        vps_data = (
            vps.lookupName(
                vps_search_data["name"],
                vps_search_data["manufacturer"],
                vps_search_data["year"],
            )
            if vps_search_data
            else None
        )
        if vps_data is None:
            current += 1
            log("Unknown table %s: %s Not found in VPSdb", current, table.tableDirName)
