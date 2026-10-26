#!/usr/bin/env python3
"""Copy a PvP subset of extracted TrinityCore data into an EMPTY destination.

VMAP formats follow TrinityCore's ModelSpawn, StaticMapTree and BIH readers.
Keeps all dynamic GameObject collision models, plus models referenced by retained tiles.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct

MAGIC = b'VMAP_4.8'


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError('Truncated VMAP data')
        value = self.data[self.pos:self.pos+n]
        self.pos += n
        return value

    def u32(self):
        return struct.unpack('<I', self.take(4))[0]

    def name(self):
        n = self.u32()
        if not 0 < n < 500:
            raise ValueError('Invalid VMAP model name length')
        name = self.take(n).decode('utf-8')
        if '/' in name or '\\' in name or name in ('.', '..'):
            raise ValueError('Unsafe VMAP model name')
        return name + '.vmo'


def spawn(reader):
    flags = reader.u32()
    reader.take(2 + 4 + 12 + 12 + 4)
    if flags & 4:
        reader.take(24)
    return reader.name()


def models(path):
    r = Reader(path.read_bytes())
    if r.take(8) != MAGIC:
        raise ValueError(f'Unsupported VMAP format: {path.name}')
    names = set()
    if path.suffix == '.vmtile':
        for _ in range(r.u32()):
            names.add(spawn(r))
            r.take(4)  # BIH reference index
    elif path.suffix == '.vmtree':
        tiled = r.take(1)[0]
        if r.take(4) != b'NODE':
            raise ValueError('Missing VMAP NODE')
        r.take(24)  # BIH bounds
        r.take(r.u32() * 4)  # tree
        r.take(r.u32() * 4)  # objects
        if r.take(4) != b'GOBJ':
            raise ValueError('Missing VMAP GOBJ')
        if not tiled and r.pos < len(r.data):
            names.add(spawn(r))
    elif path.name == 'GameObjectModels.dtree':
        while r.pos < len(r.data):
            r.take(5)  # displayId, isWmo
            names.add(r.name())
            r.take(24)  # bounds
    return names


def keep_tile(map_id, x, y, profile):
    if map_id in profile['pvp_maps'] + profile['extra_maps']:
        return True
    for s in profile['staging']:
        if s['map'] == map_id:
            gx = math.floor(32 - s['x'] / (1600/3))
            gy = math.floor(32 - s['y'] / (1600/3))
            if abs(gx-x) <= s['radius'] and abs(gy-y) <= s['radius']:
                return True
    return False


def selected(path, profile):
    if path.parent.name in ('dbc', 'Cameras'):
        return True
    all_maps = set(profile['pvp_maps'] + profile['extra_maps']) | {s['map'] for s in profile['staging']}
    match = re.fullmatch(r'(\d{3})(\d{2})(\d{2})\.(map|mmtile)', path.name)
    if match:
        m, x, y = map(int, match.groups()[:3])
        return keep_tile(m, x, y, profile)
    match = re.fullmatch(r'(\d{3})_(\d{2})_(\d{2})\.vmtile', path.name)
    if match:
        m, y, x = map(int, match.groups())
        return keep_tile(m, x, y, profile)
    match = re.fullmatch(r'(\d{3})\.(vmtree|mmap)', path.name)
    return bool(match and int(match[1]) in all_maps) or path.name == 'GameObjectModels.dtree'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('destination', type=Path)
    p.add_argument('--profile', type=Path, required=True)
    args = p.parse_args()
    source, dest = args.source.resolve(), args.destination.resolve()
    if source == dest or source in dest.parents or (dest.exists() and any(dest.iterdir())):
        raise SystemExit('Destination must be empty and outside the source')
    profile = json.loads(args.profile.read_text())
    files = [x for x in source.rglob('*') if x.is_file()]
    keep = {x for x in files if selected(x, profile)}
    dependencies = set()
    for path in sorted(keep):
        if path.suffix in ('.vmtree', '.vmtile') or path.name == 'GameObjectModels.dtree':
            dependencies.update(models(path))
    missing = sorted(name for name in dependencies if not (source/'vmaps'/name).is_file())
    if missing:
        raise SystemExit('Source has missing collision models: ' + ', '.join(missing[:10]))
    keep.update(source/'vmaps'/name for name in dependencies)
    # Fail closed if a requested PvP map lacks its core terrain/collision definitions.
    for m in profile['pvp_maps'] + profile['extra_maps']:
        if not any(x.parent.name == 'maps' and x.name.startswith(f'{m:03}') for x in keep):
            raise SystemExit(f'Missing source map terrain: {m}')
        if source/'vmaps'/f'{m:03}.vmtree' not in keep:
            raise SystemExit(f'Missing source collision tree: {m}')
    for s in profile['staging']:
        gx, gy = (math.floor(32-s[k]/(1600/3)) for k in ('x', 'y'))
        if source/'maps'/f'{s["map"]:03}{gx:02}{gy:02}.map' not in keep:
            raise SystemExit(f'Missing staging tile: {s["map"]} {gx} {gy}')
    dest.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': 1, 'profile': profile, 'source_bytes': sum(p.stat().st_size for p in files),
              'packed_bytes': 0, 'collision_models': len(dependencies), 'files': []}
    for path in sorted(keep):
        relative = path.relative_to(source)
        target = dest/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        original = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != original:
            raise RuntimeError(f'Copy verification failed: {relative}')
        size = target.stat().st_size
        report['packed_bytes'] += size
        report['files'].append({'path': str(relative), 'bytes': size, 'sha256': original})
    # Completion marker written only after dependencies and every copy were verified.
    (dest/'pvp-profile.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('files','profile')}, indent=2))


if __name__ == '__main__':
    main()
