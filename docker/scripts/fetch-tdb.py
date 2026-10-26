#!/usr/bin/env python3
"""Cache a verified upstream world seed. Never connect to or reset a database."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request


def verify(path, expected):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f'Checksum mismatch: {path.name}; remove the corrupt cache file and retry')


def fetch(manifest, destination):
    spec = json.loads(manifest.read_text())
    destination.mkdir(parents=True, exist_ok=True)
    for key in ('archive', 'sql'):
        if Path(spec[key]).name != spec[key] or spec[key] in ('.', '..'):
            raise ValueError(f'Invalid {key} filename in manifest')
    sql = destination / spec['sql']
    if sql.exists():
        verify(sql, spec['sql_sha256'])
        print(f"Verified cached {spec['release']}", flush=True)
        return
    archive = destination / spec['archive']
    with tempfile.TemporaryDirectory(prefix='.tdb-', dir=destination) as directory:
        staging = Path(directory)
        if not archive.exists():
            download = staging / spec['archive']
            print(f"Downloading {spec['release']} from upstream", flush=True)
            request = urllib.request.Request(spec['url'], headers={'User-Agent': 'wenilla-wotlk-setup'})
            with urllib.request.urlopen(request, timeout=120) as response, download.open('wb') as output:
                shutil.copyfileobj(response, output, 1024 * 1024)
            verify(download, spec['archive_sha256'])
            download.replace(archive)
        else:
            verify(archive, spec['archive_sha256'])
        extracted = staging / spec['sql']
        with extracted.open('wb') as output:
            subprocess.run(['7z', 'e', '-so', str(archive.resolve()), spec['sql']],
                           stdout=output, check=True)
        verify(extracted, spec['sql_sha256'])
        extracted.replace(sql)
    print(f"Ready: {spec['sql']} (SHA-256 verified)", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('/tdb-release.json'))
    parser.add_argument('--directory', type=Path, default=Path('/tdb'))
    args = parser.parse_args()
    fetch(args.manifest, args.directory)
