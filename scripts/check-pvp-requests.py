#!/usr/bin/env python3
"""Check successful requests captured with ASSET_REPORT against a pack manifest."""
import argparse
import json
from pathlib import Path


def missing_files(manifest, reports):
    names = {entry['name'].replace('\\', '/').lower() for entry in manifest['files']}
    requested = {
        name.replace('\\', '/').lower()
        for report in reports for name, status in report.items()
        if 200 <= status < 300 and name != '__index'
    }
    return requested, requested - names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('reports', type=Path, nargs='+')
    args = parser.parse_args()
    requested, missing = missing_files(json.loads(args.manifest.read_text()),
                                      [json.loads(p.read_text()) for p in args.reports])
    for name in sorted(missing):
        print('MISSING:', name)
    print(f'{len(requested)} distinct successful asset requests; {len(missing)} missing from pack')
    raise SystemExit(bool(missing))


if __name__ == '__main__':
    main()
