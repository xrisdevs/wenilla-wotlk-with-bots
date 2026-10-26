#!/usr/bin/env python3
"""Verify retained data and register newly generated PvP navmesh tiles in its manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('data', type=Path)
    p.add_argument('--record-navigation', action='store_true')
    args = p.parse_args()
    root = args.data
    manifest_path = root/'pvp-profile.json'
    manifest = json.loads(manifest_path.read_text())
    allowed = set(manifest['profile']['pvp_maps'])
    recorded = {f['path']: f for f in manifest['files']}
    for name, entry in recorded.items():
        path = root/name
        if path.stat().st_size != entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise SystemExit('Retained data changed: '+name)
    additions = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path == manifest_path or str(path.relative_to(root)) in recorded:
            continue
        relative = str(path.relative_to(root))
        match = re.fullmatch(r'mmaps/(\d{3})(?:\d{4})?\.(mmap|mmtile)',relative)
        if not args.record_navigation or not match or int(match[1]) not in allowed:
            raise SystemExit('Unrecorded file: '+relative)
        data = path.read_bytes()
        if match[2] == 'mmtile':
            if len(data) < 20:
                raise SystemExit('Truncated navmesh tile: '+relative)
            magic, detour, version, size = struct.unpack_from('<4I',data)
            if magic != 0x4d4d4150 or version != 15 or len(data) != size+20:
                raise SystemExit('Invalid navmesh header: '+relative)
        elif len(data) != 28:
            raise SystemExit('Invalid navigation parameters: '+relative)
        additions.append({'path':relative,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    for map_id in allowed:
        if not (root/'mmaps'/f'{map_id:03}.mmap').is_file() or not list((root/'mmaps').glob(f'{map_id:03}*.mmtile')):
            raise SystemExit(f'Missing PvP navigation for map {map_id}')
    if additions:
        manifest['files'].extend(additions)
        manifest['files'].sort(key=lambda f:f['path'])
        manifest['packed_bytes']=sum(f['bytes'] for f in manifest['files'])
        temporary=manifest_path.with_suffix('.partial')
        temporary.write_text(json.dumps(manifest,indent=2)+'\n')
        temporary.replace(manifest_path)
    print(json.dumps({'verified_files':len(manifest['files']),'navigation_added':len(additions),
                      'packed_bytes':manifest['packed_bytes']},indent=2))


if __name__ == '__main__':
    main()
