from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from common.http_client import get_bytes, get_json, get_text


logger = logging.getLogger("vpinfe.common.vpsdb_cache")


class VPSDatabaseCache:
    def __init__(
        self,
        config_dir: Path,
        iniconfig,
        *,
        db_url: str,
        last_update_url: str,
        filename: str = "vpsdb.json",
    ) -> None:
        self.config_dir = config_dir
        self.iniconfig = iniconfig
        self.db_url = db_url
        self.last_update_url = last_update_url
        self.path = config_dir / filename

    def ensure_current(self) -> list[dict]:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        version = self.fetch_last_update()
        if version:
            self._update_if_needed(version)
        return self.load_local()

    def fetch_last_update(self) -> str | None:
        try:
            return get_text(self.last_update_url).strip()
        except requests.RequestException as exc:
            logger.warning("Failed to retrieve lastUpdate.json: %s", exc)
            return None

    def _update_if_needed(self, version: str) -> None:
        if not self.iniconfig.config.has_section("VPSdb"):
            self.iniconfig.config.add_section("VPSdb")
            self.download_db()
        else:
            current = self.iniconfig.config.get("VPSdb", "last", fallback="")
            if current < version:
                self.download_db()
            else:
                logger.info("VPSdb currently at latest revision.")

        self.iniconfig.config.set("VPSdb", "last", version)
        self.iniconfig.save()

    def download_db(self) -> None:
        try:
            self.path.write_bytes(get_bytes(self.db_url))
            logger.info("Successfully downloaded vpsdb.json from VPSdb")
        except requests.RequestException as exc:
            logger.warning("Failed to download vpsdb.json: %s", exc)

    def load_local(self) -> list[dict]:
        if not self.path.exists():
            logger.warning("JSON file %s not found.", self.path)
            return []

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.error("Invalid JSON format in %s", self.path)
            return []

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            items = data.get("tables") or data.get("items") or []
            return items if isinstance(items, list) else []
        return []


class VPinMediaDatabase:
    def __init__(self, url: str) -> None:
        self.url = url

    def load(self) -> dict | None:
        try:
            payload = get_json(self.url)
            return payload if isinstance(payload, dict) else None
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Failed to retrieve vpinmdb.json: %s", exc)
            return None
