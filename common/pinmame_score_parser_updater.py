from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests
from common.paths import CONFIG_DIR, USER_ROMS_PATH


logger = logging.getLogger("vpinfe.common.pinmame_score_parser_updater")


ROMS_JSON_PATH = USER_ROMS_PATH
LATEST_RELEASE_URL = "https://api.github.com/repos/superhac/pinmame-score-parser/releases/latest"
USER_AGENT = "VPinFE-pinmame-score-parser-updater"
RELEASE_SECTION = "pinmame-score-parser"
RELEASE_SHA_KEY = "romsupdatesha"


def get_user_roms_path() -> Path:
    return ROMS_JSON_PATH


def _request_json(url: str) -> dict:
    response = requests.get(
        url,
        timeout=15,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from {url}, got {type(payload).__name__}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_file(url: str, dest: Path) -> None:
    with requests.get(
        url,
        timeout=60,
        headers={"User-Agent": USER_AGENT},
        stream=True,
    ) as response:
        response.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


def _find_release_asset(release_payload: dict) -> dict:
    assets = release_payload.get("assets") or []
    exact = [asset for asset in assets if asset.get("name") == "roms.json"]
    if exact:
        return exact[0]

    fallback = [
        asset for asset in assets
        if str(asset.get("name", "")).lower().endswith("roms.json")
    ]
    if fallback:
        return fallback[0]

    raise ValueError("Latest pinmame-score-parser release does not contain a roms.json asset")


def _normalize_release_digest(asset: dict) -> str:
    digest = str(asset.get("digest", "")).strip()
    if digest.startswith("sha256:"):
        return digest.split(":", 1)[1].strip().lower()
    if digest:
        return digest.lower()
    return ""


def _release_fingerprint(release_payload: dict, asset: dict) -> str:
    remote_digest = _normalize_release_digest(asset)
    if remote_digest:
        return remote_digest

    for value in (
        asset.get("updated_at"),
        release_payload.get("published_at"),
        release_payload.get("tag_name"),
        asset.get("id"),
        release_payload.get("id"),
    ):
        if value:
            return str(value).strip()
    return ""


def ensure_latest_roms_json(iniconfig) -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not iniconfig.config.has_section(RELEASE_SECTION):
        iniconfig.config.add_section(RELEASE_SECTION)

    tracked_sha = iniconfig.config.get(RELEASE_SECTION, RELEASE_SHA_KEY, fallback="").strip().lower()

    release_payload = _request_json(LATEST_RELEASE_URL)
    asset = _find_release_asset(release_payload)
    download_url = asset.get("browser_download_url")
    if not download_url:
        raise ValueError("Latest pinmame-score-parser release asset is missing browser_download_url")

    fingerprint = _release_fingerprint(release_payload, asset).lower()
    needs_download = not ROMS_JSON_PATH.exists()
    if not needs_download and fingerprint:
        needs_download = tracked_sha != fingerprint

    if not needs_download:
        logger.info("roms.json is already up to date at %s", ROMS_JSON_PATH)
        return {
            "status": "up_to_date",
            "path": ROMS_JSON_PATH,
            "tracked_sha": tracked_sha,
        }

    with NamedTemporaryFile(delete=False, suffix=".roms.json", dir=str(CONFIG_DIR)) as tmp:
        temp_path = Path(tmp.name)

    try:
        logger.info("Downloading latest roms.json from %s", download_url)
        _download_file(download_url, temp_path)
        downloaded_sha = _sha256_file(temp_path)
        expected_sha = _normalize_release_digest(asset)
        if expected_sha and downloaded_sha.lower() != expected_sha:
            raise ValueError(
                "Downloaded roms.json SHA256 does not match the release digest: "
                f"expected {expected_sha}, got {downloaded_sha.lower()}"
            )

        ROMS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path.replace(ROMS_JSON_PATH)
        iniconfig.config.set(RELEASE_SECTION, RELEASE_SHA_KEY, fingerprint or downloaded_sha.lower())
        iniconfig.save()
        logger.info("Updated roms.json at %s", ROMS_JSON_PATH)
        return {
            "status": "downloaded",
            "path": ROMS_JSON_PATH,
            "tracked_sha": fingerprint or downloaded_sha.lower(),
            "file_sha": downloaded_sha.lower(),
        }
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            logger.debug("Could not remove temporary roms.json download: %s", temp_path, exc_info=True)
