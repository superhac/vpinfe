from __future__ import annotations

import json
import os
import shutil
import zipfile
from io import BytesIO


class ThemeInstallStore:
    def __init__(self, themes_dir: str) -> None:
        self.themes_dir = themes_dir
        os.makedirs(self.themes_dir, exist_ok=True)

    @staticmethod
    def repo_name(base_url: str) -> str:
        return base_url.rstrip("/").split("/")[-1]

    @staticmethod
    def is_version_newer(remote: str, local: str) -> bool:
        def parse(version: str):
            return [int(part) for part in version.split(".")]
        return parse(remote) > parse(local)

    @staticmethod
    def build_zip_url(base_url: str) -> str:
        return f"{base_url}/archive/refs/heads/master.zip"

    def installed_folder(self, theme_key: str, base_url: str | None = None) -> str | None:
        if os.path.isdir(os.path.join(self.themes_dir, theme_key)):
            return theme_key

        if not base_url:
            return None

        repo_name = self.repo_name(base_url)
        for folder in os.listdir(self.themes_dir):
            if folder.startswith(repo_name):
                return folder
        return None

    def installed_version(self, theme_key: str, base_url: str | None = None) -> str | None:
        folder_name = self.installed_folder(theme_key, base_url)
        if not folder_name:
            return None

        manifest_path = os.path.join(self.themes_dir, folder_name, "manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data.get("version")
        return None

    def remove_existing_install(self, base_url: str) -> None:
        repo_name = self.repo_name(base_url)
        for folder in os.listdir(self.themes_dir):
            if folder.startswith(repo_name):
                shutil.rmtree(os.path.join(self.themes_dir, folder))

    def install_zip(self, theme_key: str, base_url: str, zip_data: BytesIO) -> None:
        self.remove_existing_install(base_url)
        with zipfile.ZipFile(zip_data) as archive:
            archive.extractall(self.themes_dir)

        repo_name = self.repo_name(base_url)
        for folder in os.listdir(self.themes_dir):
            if folder.startswith(repo_name) and folder != theme_key:
                src = os.path.join(self.themes_dir, folder)
                dst = os.path.join(self.themes_dir, theme_key)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                os.rename(src, dst)
                break

    def delete(self, folder: str) -> None:
        shutil.rmtree(os.path.join(self.themes_dir, folder))
