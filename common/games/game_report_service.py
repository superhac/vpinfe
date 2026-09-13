"""The two library reports the CLI prints: what is missing, and what we cannot place."""

from __future__ import annotations

import logging

from common.config_access import SettingsConfig
from common.config_store import ConfigStore
from common.games.game_repository import games_under
from common.online.vpsdb import VPSdb
from common.paths import get_ini_config

logger = logging.getLogger("vpinfe.common.games.game_report_service")


def _config(config: ConfigStore | None = None) -> ConfigStore:
    return config or get_ini_config()


def list_missing_games(iniconfig: ConfigStore | None = None, log=None) -> None:
    config = _config(iniconfig)
    log = log or logger.info
    game_root = SettingsConfig.from_config(config).game_root_dir
    games = games_under(game_root, config)
    log("Listing tables missing from %s", game_root)
    log("Found %s tables in %s", len(games), game_root)

    vps = VPSdb(game_root, config)
    log("Found %s tables in VPSdb", len(vps))

    games_found = []
    for game in games:
        vps_search_data = vps.parseGameNameFromDir(game.gameDirName)
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
    for vps_game in vps.games():
        if vps_game not in games_found:
            current += 1
            log(
                "Missing table %s: %s (%s %s)",
                current,
                vps_game["name"],
                vps_game["manufacturer"],
                vps_game["year"],
            )


def list_unknown_games(iniconfig: ConfigStore | None = None, log=None) -> None:
    config = _config(iniconfig)
    log = log or logger.info
    game_root = SettingsConfig.from_config(config).game_root_dir
    games = games_under(game_root, config)
    log("Listing unknown tables from %s", game_root)
    log("Found %s tables in %s", len(games), game_root)

    vps = VPSdb(game_root, config)
    log("Found %s tables in VPSdb", len(vps))

    current = 0
    for game in games:
        vps_search_data = vps.parseGameNameFromDir(game.gameDirName)
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
            log("Unknown table %s: %s Not found in VPSdb", current, game.gameDirName)
