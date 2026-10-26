#!/usr/bin/env python3
"""Run a fixed-settings, side-balanced headless arena benchmark.

Run after pausing the tuner. Existing matches drain before settings change.
Raw results, live snapshots and a manifest are retained for independent analysis.
The caller's saved team settings, auto rotation and paused tuner are restored on exit.
"""
import argparse
from collections import Counter
import itertools
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import time

from arena_ctl import ROOT, soap


def status():
    return json.loads(soap('.botarena json'))


def results():
    r = subprocess.run(['docker', 'compose', 'exec', '-T', 'worldserver', 'cat',
                        '/logs/botarena_matches.jsonl'], cwd=ROOT, check=True,
                       capture_output=True, text=True)
    lines = r.stdout.splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def plan(quick=False):
    comps = ['rmp', 'tsg', 'lsd', 'beastcleave']
    jobs = []
    for a, h in itertools.combinations(comps, 2):
        for repeat in range(2 if quick else 3):
            for x, y in [(a, h), (h, a)]:
                jobs.append(dict(arena='na', compA=x, compH=y, repeat=repeat,
                                 phase='composition'))
    for comp in comps:
        for repeat in range(1 if quick else 3):
            jobs.append(dict(arena='na', compA=comp, compH=comp, repeat=repeat,
                             phase='mirror'))
    for arena in ['be', 'rl']:
        for a, h in ([('rmp', 'tsg')] if quick else [('rmp', 'tsg'), ('lsd', 'beastcleave')]):
            for repeat in range(1 if quick else 2):
                for x, y in [(a, h), (h, a)]:
                    jobs.append(dict(arena=arena, compA=x, compH=y, repeat=repeat,
                                     phase='map'))
    random.Random(20261025).shuffle(jobs)
    return jobs


def fits_pool(job, state):
    classes = {'rmp': ['rogue', 'mage', 'priest'], 'tsg': ['warrior', 'dk', 'paladin'],
               'lsd': ['warlock', 'shaman', 'druid'], 'beastcleave': ['hunter', 'shaman', 'shaman']}
    occupied = Counter((b['team'], b['class']) for m in state['matches'] for b in m['bots'])
    needed = Counter((team, cls) for team in ['A', 'H'] for cls in classes[job['comp' + team]])
    if 'capacity' in state:
        return all(n <= state['capacity'].get(f"{team}:{cls}", 0)
                   for (team, cls), n in needed.items())
    # The installed NPCBot template pool has only three Alliance shamans. Other classes
    # have at least seven templates per faction; reserve one to avoid boundary races.
    return all(occupied[k] + n <= (3 if k == ('A', 'shaman') else 6) for k, n in needed.items())


def server_boot():
    return subprocess.check_output(['docker', 'inspect', subprocess.check_output(['docker','compose','ps','-q','worldserver'], cwd=ROOT, text=True).strip(),
                                   '--format', '{{.State.StartedAt}}'], text=True).strip()


def restore(saved):
    # Restore overrides before allowing the paused tuner to continue its batch evaluation.
    for line in saved['brains'].splitlines():
        if not line.startswith('ArenaBrain '):
            continue
        label, values = line.split(':', 1)
        team = label[-1]
        for pair in values.split():
            key, value = pair.split('=', 1)
            soap(f'.botarena brain set{team} {key} {value}')
    soap('.botarena auto ' + ('on 20' if saved['state']['auto'] else 'off'))
    if saved.get('tuner_pid'):
        os.kill(saved['tuner_pid'], signal.SIGCONT)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--concurrency', type=int, default=12)
    ap.add_argument('--interval', type=float, default=2)
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--quick', action='store_true', help='32 matches: 24 paired, four mirrors, four map checks')
    ap.add_argument('--smoke', action='store_true', help='Four side-balanced matches for lifecycle smoke testing')
    args = ap.parse_args()
    if args.concurrency < 1 or args.interval <= 0:
        ap.error('Concurrency and polling interval must be positive')
    args.out.mkdir(parents=True, exist_ok=True)
    saved = json.loads((args.out / 'restore.json').read_text())
    jobs = plan(args.quick)
    if args.smoke:
        jobs = [dict(arena='na', compA=a, compH=h, repeat=0, phase='composition')
                for a, h in [('rmp', 'tsg'), ('tsg', 'rmp'),
                             ('lsd', 'beastcleave'), ('beastcleave', 'lsd')]]
    manifest = dict(planned=list(jobs), concurrency=args.concurrency,
                    poll_seconds=args.interval, seed=20261025,
                    started=time.time(), source_revision=subprocess.check_output(
                        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    parameters=Path(ROOT, 'docker/conf/arenabrain.params').read_text(),
                    jobs=[], start_errors=[])
    def save():
        (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    active = {}
    completed = set()
    if args.resume:
        manifest = json.loads((args.out / 'manifest.json').read_text())
        if manifest.get('server_started_at') != server_boot():
            raise RuntimeError('Cannot resume across a server restart; use a new output directory')
        existing = [json.loads(l) for l in (args.out / 'results.jsonl').read_text().splitlines()]
        completed = {r['match'] for r in existing}
        active = {j['match']: j for j in manifest['jobs'] if j['match'] not in completed}
        def key(j):
            return tuple(j[k] for k in ['arena', 'compA', 'compH', 'repeat', 'phase'])
        launched = {key(j) for j in manifest['jobs']}
        jobs = [j for j in manifest['planned'] if key(j) not in launched]
    save()
    try:
        if not args.resume:
            soap('.botarena auto off')
            print('Draining the existing tuner batch before changing settings.', flush=True)
            while True:
                s = status()
                if not s['batch']['active'] and not s['running']:
                    break
                if time.time() - manifest['started'] > 1200:
                    raise RuntimeError('Existing batch failed to drain within 20 minutes')
                time.sleep(5)
            print(soap('.botarena brain reload'), flush=True)
            manifest['brains'] = soap('.botarena brain show')
        a, h = [line.split(':', 1)[1].strip() for line in manifest['brains'].splitlines()
                if line.startswith('ArenaBrain ')]
        if a != h:
            raise RuntimeError('Team parameters differ after reload')
        cursor = manifest['log_start_row'] if args.resume else len(results())
        if not args.resume:
            manifest['log_start_row'] = cursor
            manifest['benchmark_started'] = time.time()
        save()
        boot = server_boot()
        manifest['server_started_at'] = boot
        save()
        mode = 'a' if args.resume else 'w'
        with (args.out / 'snapshots.jsonl').open(mode) as snapshots, \
             (args.out / 'results.jsonl').open(mode) as output:
            while jobs or active:
                if server_boot() != boot:
                    raise RuntimeError('Server restarted; stop rather than merging recycled match IDs')
                t0 = time.monotonic()
                s = status()
                latency = time.monotonic() - t0
                # Other producers invalidate the controlled run.
                known = {j['match'] for j in manifest['jobs']}
                if s['batch']['active'] or s['auto']:
                    raise RuntimeError('Another producer enabled batch/auto during benchmark')
                snapshots.write(json.dumps(dict(time=time.time(), soap_seconds=latency,
                    matches=[m for m in s['matches'] if m['id'] in known])) + '\n')
                snapshots.flush()
                rows = results()
                if len(rows) < cursor:
                    raise RuntimeError('Results log shrank during benchmark')
                for row in rows[cursor:]:
                    mid = row['match']
                    if mid in active:
                        job = active.pop(mid)
                        if row.get('schema', 0) >= 2 and not row.get('valid', False):
                            raise RuntimeError('Invalid arena setup/result; benchmark aborted')
                        row['benchmark'] = job
                        if row['brainA'] != a or row['brainH'] != h:
                            raise RuntimeError('Parameters changed during a benchmark match')
                        output.write(json.dumps(row) + '\n')
                        output.flush()
                        completed.add(mid)
                        print(f"{len(completed)}/{len(manifest['planned'])}: {row['compA']} vs {row['compH']} "
                              f"on {row['arena']}: {row['winner']} in {row['duration']}s", flush=True)
                cursor = len(rows)
                attempts = 0
                while jobs and len(active) < args.concurrency and s['running'] < args.concurrency and attempts < min(8, len(jobs)):
                    attempts += 1
                    job = jobs[0]
                    if not fits_pool(job, s):
                        jobs.append(jobs.pop(0))
                        continue
                    before = {m['id'] for m in s['matches']}
                    reply = soap(f".botarena start 3 {job['arena']} {job['compA']} {job['compH']}")
                    s = status()
                    if 'match started' not in reply:
                        manifest['start_errors'].append(dict(time=time.time(), job=job, reply=reply))
                        save()
                        jobs.append(jobs.pop(0))  # another composition may have enough free bots
                        continue
                    added = [m for m in s['matches'] if m['id'] not in before]
                    if len(added) != 1 or len(added[0]['bots']) != 6:
                        raise RuntimeError('Could not identify one complete newly-started match')
                    job = dict(jobs.pop(0), match=added[0]['id'], launched=time.time())
                    active[job['match']] = job
                    manifest['jobs'].append(job)
                    save()
                if time.time() - manifest['benchmark_started'] > 3600:
                    raise RuntimeError('Benchmark exceeded one hour')
                time.sleep(args.interval)
        manifest['finished'] = time.time()
        manifest['completed'] = len(completed)
        save()
    finally:
        # Never resume changing parameters while benchmark matches are still running.
        for attempt in range(12):
            try:
                # IDs are reused after restart; never stop matches from a new process.
                if server_boot() == manifest.get('server_started_at'):
                    for mid in active:
                        soap(f'.botarena stop {mid}')
                restore(saved)
                print('Original team parameters, auto rotation and tuner restored.', flush=True)
                break
            except (SystemExit, OSError, subprocess.CalledProcessError) as exc:
                if attempt == 11:
                    raise RuntimeError('Could not restore settings; use restore.json') from exc
                time.sleep(5)


if __name__ == '__main__':
    main()
