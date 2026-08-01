from __future__ import annotations

import logging

from common.iniconfig import IniConfig
from common.config_access import SettingsConfig
from common.paths import get_ini_config
from common.tables.tableparser import GameParser
from common.online.vpsdb import VPSdb


logger = logging.getLogger("vpinfe.common.tables.table_report_service")


def _config(config: IniConfig | None = None) -> IniConfig:
    return config or get_ini_config()


def list_missing_games(iniconfig: IniConfig | None = None, log=None) -> None:
    config = _config(iniconfig)
    log = log or logger.info
    game_root = SettingsConfig.from_config(config).game_root_dir
    tp = GameParser(game_root, config)
    tables = tp.getAllGames()
    log("Listing tables missing from %s", game_root)
    log("Found %s tables in %s", len(tables), game_root)

    vps = VPSdb(game_root, config)
    log("Found %s tables in VPSdb", len(vps))

    games_found = []
    for game in tables:
        vps_search_data = vps.parseGameNameFromDir(game.tableDirName)
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
            games_found.append(vps_data)

    current = 0
    for vps_game in vps.tables():
        if vps_game not in games_found:
            current += 1
            log(
                "Missing table %s: %s (%s %s)",
                current,
                vps_game["name"],
                vps_game["manufacturer"],
                vps_game["year"],
            )


def list_unknown_games(iniconfig: IniConfig | None = None, log=None) -> None:
    config = _config(iniconfig)
    log = log or logger.info
    game_root = SettingsConfig.from_config(config).game_root_dir
    tp = GameParser(game_root, config)
    tables = tp.getAllGames()
    log("Listing unknown tables from %s", game_root)
    log("Found %s tables in %s", len(tables), game_root)

    vps = VPSdb(game_root, config)
    log("Found %s tables in VPSdb", len(vps))

    current = 0
    for game in tables:
        vps_search_data = vps.parseGameNameFromDir(game.tableDirName)
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
            log("Unknown table %s: %s Not found in VPSdb", current, game.tableDirName)
