from __future__ import annotations

import logging
import os

from common.config_access import SettingsConfig
from common.games.game_parser import GameParser
from common.games.meta_config import MetaConfig
from common.games.standalone_scripts import StandaloneScripts
from common.games.vpx_parser import VPXParser
from common.iniconfig import IniConfig
from common.jobs import JobReporter
from common.online.vpsdb import VPSdb
from common.paths import get_ini_config

logger = logging.getLogger("vpinfe.common.games.metadata_service")


def _config(config: IniConfig | None = None) -> IniConfig:
    return config or get_ini_config()


def build_metadata(
    downloadMedia: bool = True,
    updateAll: bool = True,
    gameName: str | None = None,
    userMedia: bool = False,
    progress_cb=None,
    log_cb=None,
    iniconfig: IniConfig | None = None,
):
    config = _config(iniconfig)

    reporter = JobReporter(logger, progress_cb=progress_cb, log_cb=log_cb)
    log = reporter.log

    not_found_games = 0
    parservpx = VPXParser()

    settings = SettingsConfig.from_config(config)

    tp = GameParser(settings.game_root_dir, config)
    games = tp.getAllGames()

    if gameName:
        games = [game for game in games if game.gameDirName == gameName]
        if not games:
            log(f"Table folder '{gameName}' not found")
            return {"found": 0, "not_found": 0}
        log(f"Processing single table: {gameName}")

    total = len(games)

    vps = VPSdb(settings.game_root_dir, config)
    log(f"Found {len(vps)} tables in VPSdb")

    if progress_cb:
        reporter.progress(0, total, "Starting")

    for current, game in enumerate(games, 1):
        info_path = os.path.join(game.fullPathGame, f"{game.gameDirName}.info")

        if os.path.exists(info_path) and not updateAll:
            if progress_cb:
                reporter.progress(current, total, f"Skipping {game.gameDirName}")
            continue

        meta = MetaConfig(info_path)

        log(f"Checking VPSdb for {game.gameDirName}")
        if progress_cb:
            reporter.progress(current, total, f"Processing {game.gameDirName}")

        vpsSearchData = vps.parseGameNameFromDir(game.gameDirName)
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
            not_found_games += 1
            continue

        log(f"Parsing VPX file: {game.fullPathVPXfile}")
        vpxData = parservpx.singleFileExtract(game.fullPathVPXfile)

        if not vpxData:
            log(f"  - VPX file not found or failed to parse: {game.fullPathVPXfile}")
            not_found_games += 1
            continue

        meta.writeConfigMeta({
            "vpsdata": vpsData,
            "vpxdata": vpxData,
        })

        log(f"Created {game.gameDirName}.info")

        # userMedia suppresses the fetch outright, for somebody supplying the whole
        # library themselves. Media already on disk needs no such flag: the
        # downloader compares hashes and leaves anything it cannot prove is ours
        # alone (common/online/vpsdb_media.py).
        if downloadMedia and not userMedia:
            try:
                vps.downloadMediaForGame(game, vpsData["id"], metaConfig=meta)
                log("Downloaded media")
            except KeyError:
                log("No media found")

    if progress_cb:
        reporter.progress(total, total, "Complete")

    return {"found": total, "not_found": not_found_games}


def apply_vpx_patches(progress_cb=None, iniconfig: IniConfig | None = None):
    config = _config(iniconfig)
    settings = SettingsConfig.from_config(config)
    tp = GameParser(settings.game_root_dir, config)
    games = tp.getAllGames()
    StandaloneScripts(games, progress_cb=progress_cb)
