#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as response, dest.open('wb') as out:
        shutil.copyfileobj(response, out)


def _download_with_headers(url: str, dest: Path, headers: dict | None = None) -> None:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as response, dest.open('wb') as out:
        shutil.copyfileobj(response, out)


def _read_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))


def _tag_candidates(version: str) -> list[str]:
    v = version.strip()
    if not v:
        return []
    if v.startswith('v'):
        return [v, v[1:]]
    return [v, f'v{v}']


def _download_manifest(repo: str, version: str, manifest_path: Path) -> str:
    last_err = None
    for tag in _tag_candidates(version):
        base = f"https://github.com/{repo}/releases/download/{tag}"
        manifest_url = f"{base}/manifest.json"
        try:
            print(f"[DOF FETCH] Downloading manifest: {manifest_url}")
            _download(manifest_url, manifest_path)
            return tag
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            last_err = e
            print(f"[DOF FETCH] Direct manifest URL not found for tag '{tag}' (404).")

        api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        headers = {
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'vpinfe-dof-fetcher',
        }
        try:
            release = _read_json(api_url, headers=headers)
            assets = release.get('assets', [])
            manifest_asset = None
            for asset in assets:
                if asset.get('name') == 'manifest.json':
                    manifest_asset = asset
                    break
            if manifest_asset is None:
                for asset in assets:
                    name = str(asset.get('name', '')).lower()
                    if 'manifest' in name and name.endswith('.json'):
                        manifest_asset = asset
                        break
            if manifest_asset:
                dl_url = manifest_asset.get('browser_download_url')
                if not dl_url:
                    raise RuntimeError("manifest asset missing browser_download_url")
                print(f"[DOF FETCH] Downloading manifest asset via API: {dl_url}")
                _download_with_headers(dl_url, manifest_path, headers={'User-Agent': 'vpinfe-dof-fetcher'})
                return tag
            print(f"[DOF FETCH] No manifest asset found for tag '{tag}'.")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"[DOF FETCH] Release tag not found via API: {tag}")
                last_err = e
                continue
            raise

    if last_err:
        raise last_err
    raise RuntimeError(f"Could not resolve manifest for {repo} {version}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Fetch and verify a DOF bundle from GitHub release manifest.'
    )
    parser.add_argument('--repo', required=True, help='GitHub repo owner/name')
    parser.add_argument('--version', required=True, help='Release tag, e.g. v1.0.1')
    parser.add_argument('--triplet', required=True, help='Manifest triplet, e.g. linux-x64')
    parser.add_argument('--outdir', default='third-party/dof', help='Output directory')
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix='vpinfe-dof-') as td:
        tmp = Path(td)
        manifest_path = tmp / 'manifest.json'
        bundle_zip = tmp / 'dof.zip'
        extract_dir = tmp / 'extract'

        resolved_tag = _download_manifest(args.repo, args.version, manifest_path)
        base = f"https://github.com/{args.repo}/releases/download/{resolved_tag}"

        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assets = manifest.get('assets', {})
        entry = assets.get(args.triplet)
        if not entry:
            raise SystemExit(
                f"[DOF FETCH] Triplet '{args.triplet}' not found in manifest assets."
            )

        file_name = entry.get('file', '').strip()
        expected_sha = entry.get('sha256', '').strip().lower()
        if not file_name or not expected_sha:
            raise SystemExit("[DOF FETCH] Manifest entry missing file or sha256.")

        zip_url = f"{base}/{file_name}"
        print(f"[DOF FETCH] Downloading bundle: {zip_url}")
        _download(zip_url, bundle_zip)

        actual_sha = _sha256_file(bundle_zip)
        if actual_sha != expected_sha:
            raise SystemExit(
                "[DOF FETCH] SHA256 mismatch.\n"
                f"  expected: {expected_sha}\n"
                f"  actual:   {actual_sha}"
            )

        print("[DOF FETCH] SHA256 verified.")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(bundle_zip, 'r') as zf:
            zf.extractall(extract_dir)

        # Normalize archive layout: if bundle contains a single top-level directory,
        # treat that directory as the actual payload root.
        payload_root = extract_dir
        children = [p for p in extract_dir.iterdir()]
        if len(children) == 1 and children[0].is_dir():
            payload_root = children[0]

        outdir = Path(args.outdir)
        outdir.parent.mkdir(parents=True, exist_ok=True)
        if outdir.exists():
            shutil.rmtree(outdir)
        shutil.move(str(payload_root), str(outdir))

        if not (outdir / 'dof_runner.py').exists():
            raise SystemExit(
                f"[DOF FETCH] dof_runner.py not found in extracted bundle at {outdir}"
            )

        print(f"[DOF FETCH] Installed bundle to: {outdir}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
