from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests


DEFAULT_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 60


def get_json(url: str, *, timeout: int = DEFAULT_TIMEOUT, headers: dict[str, str] | None = None) -> Any:
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON returned from {url}") from exc


def get_text(url: str, *, timeout: int = DEFAULT_TIMEOUT, headers: dict[str, str] | None = None) -> str:
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def get_bytes(url: str, *, timeout: int = DOWNLOAD_TIMEOUT, headers: dict[str, str] | None = None) -> bytes:
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.content


def download_file(
    url: str,
    dest: Path,
    *,
    timeout: int = DOWNLOAD_TIMEOUT,
    headers: dict[str, str] | None = None,
    chunk_size: int = 1024 * 1024,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=timeout, headers=headers, stream=True) as response:
        response.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
