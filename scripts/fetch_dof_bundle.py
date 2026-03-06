#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import tempfile
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Fetch and verify a DOF bundle from GitHub release manifest.'
    )
    parser.add_argument('--repo', required=True, help='GitHub repo owner/name')
    parser.add_argument('--version', required=True, help='Release tag, e.g. v1.0.1')
    parser.add_argument('--triplet', required=True, help='Manifest triplet, e.g. linux-x64')
    parser.add_argument('--outdir', default='third-party/dof', help='Output directory')
    args = parser.parse_args()

    base = f"https://github.com/{args.repo}/releases/download/{args.version}"
    manifest_url = f"{base}/manifest.json"

    with tempfile.TemporaryDirectory(prefix='vpinfe-dof-') as td:
        tmp = Path(td)
        manifest_path = tmp / 'manifest.json'
        bundle_zip = tmp / 'dof.zip'
        extract_dir = tmp / 'extract'

        print(f"[DOF FETCH] Downloading manifest: {manifest_url}")
        _download(manifest_url, manifest_path)

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

        outdir = Path(args.outdir)
        outdir.parent.mkdir(parents=True, exist_ok=True)
        if outdir.exists():
            shutil.rmtree(outdir)
        shutil.move(str(extract_dir), str(outdir))

        print(f"[DOF FETCH] Installed bundle to: {outdir}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
