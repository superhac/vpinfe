from __future__ import annotations

import logging
import time
from io import BytesIO

import requests

from common.http_client import get_json


logger = logging.getLogger("vpinfe.common.theme_registry_client")


class ThemeRegistryError(Exception):
    pass


class ThemeRegistryClient:
    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout

    def fetch_json(self, url: str) -> dict:
        try:
            payload = get_json(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ThemeRegistryError(f"Failed to fetch JSON from {url}: {exc}") from exc
        except ValueError as exc:
            raise ThemeRegistryError(str(exc)) from exc

        if not isinstance(payload, dict):
            raise ThemeRegistryError(f"Invalid JSON returned from {url}")
        return payload

    def download_zip(self, url: str, max_retries: int = 3) -> BytesIO:
        for attempt in range(max_retries):
            response = requests.get(url, timeout=60)
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", 5 * (attempt + 1)))
                logger.warning(
                    "429 on zip download, waiting %ss (attempt %s/%s)",
                    wait,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(wait)
                continue
            response.raise_for_status()
            return BytesIO(response.content)
        raise ThemeRegistryError(f"Failed to download {url} after {max_retries} retries (rate limited)")
