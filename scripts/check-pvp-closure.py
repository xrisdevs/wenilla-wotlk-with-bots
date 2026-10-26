#!/usr/bin/env python3
"""Audit a dependency-pruned candidate against the byte-verified conservative pack.

This checks retained-map/dynamic-asset coverage, not full battleground gameplay.
"""
import argparse
import json
from pathlib import Path


def normalize(name):
    return name.replace('\\', '/').lower()


def audit(previous, candidate, plan, reports):
    old = {normalize(e['name']): e for e in previous['files']}
    new = {normalize(e['name']): e for e in candidate['files']}
    errors = []
    if set(previous['maps']) != set(candidate['maps']):
        errors.append('Supported map set changed')
    if set(new) != set(plan['kept']):
        errors.append('Candidate asset set differs from dependency closure')
    # These runtime-selected families must not depend on a sampled play session.
    protected = ('world/maps/', 'character/', 'item/', 'creature/', 'spells/',
                 'spell/', 'dbfilesclient/', 'interface/', 'tileset/', 'textures/')
    required = {n for n in old if n.startswith(protected)}
    errors.extend('Required family asset removed: '+n for n in sorted(required-new.keys()))
    for name, entry in new.items():
        if name in old and (entry['size'], entry['sha256']) != (old[name]['size'], old[name]['sha256']):
            errors.append('Asset bytes changed: '+name)
    for report in reports:
        for name, status in report.items():
            if 200 <= status < 300 and name != '__index' and normalize(name) not in new:
                errors.append('Observed successful asset removed: '+name)
            if status == 404 and normalize(name) in old and normalize(name) not in new:
                errors.append('Pruned asset requested by client: '+name)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('plan', type=Path)
    parser.add_argument('reports', type=Path, nargs='*')
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text())
    previous, candidate, plan = map(read, (args.previous, args.candidate, args.plan))
    errors = audit(previous, candidate, plan, list(map(read, args.reports)))
    for error in errors:
        print(error)
    print(f"{len(candidate['maps'])} map roots; {len(candidate['files'])} files; {len(errors)} coverage errors")
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
