#!/usr/bin/env python3
"""Analyze benchmark results plus live samples; never trust post-match resurrection state."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

HEALERS = {('priest', 'disc'), ('paladin', 'holy'), ('druid', 'resto'), ('shaman', 'resto')}


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    x = (len(values) - 1) * p
    lo = int(x)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (x - lo)


def distribution(values):
    return dict(n=len(values), median=statistics.median(values) if values else None,
                p90=percentile(values, .9), min=min(values) if values else None,
                max=max(values) if values else None)


def wilson(wins, n):
    if not n:
        return [None, None]
    z = 1.96
    p = wins / n
    d = 1 + z*z/n
    center = (p + z*z/(2*n))/d
    half = z*((p*(1-p)/n + z*z/(4*n*n))**.5)/d
    return [center-half, center+half]


def analyze(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    rows = [json.loads(l) for l in (folder / 'results.jsonl').read_text().splitlines()]
    invalid_rows = [r for r in rows if r.get('schema', 0) >= 2 and not r.get('valid', False)]
    rows = [r for r in rows if r not in invalid_rows]
    verified = bool(rows) and all(r.get('schema', 0) >= 2 and r.get('valid') for r in rows)
    samples = defaultdict(list)
    latencies = []
    for line in (folder / 'snapshots.jsonl').read_text().splitlines():
        snap = json.loads(line)
        latencies.append(snap['soap_seconds'] * 1000)
        for match in snap['matches']:
            if match['state'] == 'running' and match['bgStatus'] == 3:
                samples[match['id']].append(match)
    comps = defaultdict(lambda: dict(games=0, wins=0, draws=0, combat_seconds=[],
                                    focus=0, focus_samples=0, no_victim=0, dps_samples=0,
                                    healer_target=0, enemy_target=0))
    specs = defaultdict(lambda: dict(appearances=0, damage=0, healing=0, seconds=0,
                                    no_victim=0, alive_samples=0, first_deaths=0,
                                    observed_deaths=0, killing_blows=0, logged_deaths=0))
    pairs = defaultdict(lambda: dict(games=0, wins=Counter(), draws=0, durations=[]))
    metrics = []
    for row in rows:
        combat = max(0, row['duration'] - 60)
        phase = row['benchmark']['phase']
        pair = pairs[f"{row['arena']}: {' vs '.join(sorted([row['compA'], row['compH']]))}"]
        pair['games'] += 1
        pair['durations'].append(combat)
        if row['winner'] in ['A', 'H']:
            pair['wins'][row['comp' + row['winner']]] += 1
        else:
            pair['draws'] += 1
        for team in ['A', 'H']:
            if phase == 'composition':
                c = comps[row['comp' + team]]
                c['games'] += 1
                c['wins'] += row['winner'] == team
                c['draws'] += row['winner'] == 'none'
                c['combat_seconds'].append(combat)
        for bot in row['bots']:
            if phase == 'composition':
                spec = specs[f"{bot['class']}/{bot['spec']}"]
                spec['appearances'] += 1
                spec['damage'] += bot['damage']
                spec['healing'] += bot['healing']
                spec['seconds'] += combat
                if row.get('schema', 0) >= 2 and row.get('valid'):
                    spec['killing_blows'] += bot['killingBlows']
                    spec['logged_deaths'] += bot['deaths']
        first_death = None
        dead = set()
        contact = None
        focus = Counter()
        focus_n = Counter()
        for m in samples[row['match']]:
            if contact is None and any(b['hp'] < b['maxhp']*.95 for b in m['bots']):
                contact = max(0, m['elapsed'] - 60)
            newly_dead = [b for b in m['bots'] if not b['alive'] and b['idx'] not in dead]
            if first_death is None and newly_dead:
                first_death = dict(seconds=max(0, m['elapsed']-60),
                                   bots=[f"{b['team']}:{b['class']}/{b['spec']}" for b in newly_dead])
                if phase == 'composition':
                    for b in newly_dead:
                        specs[f"{b['class']}/{b['spec']}"]['first_deaths'] += 1
            for b in newly_dead:
                dead.add(b['idx'])
                if phase == 'composition':
                    specs[f"{b['class']}/{b['spec']}"]['observed_deaths'] += 1
            for team in ['A', 'H']:
                enemies = {b['name']: b for b in m['bots'] if b['team'] != team and b['alive']}
                dps = [b for b in m['bots'] if b['team'] == team and b['alive']
                       and (b['class'], b['spec']) not in HEALERS]
                targets = [b['target'] for b in dps if b['target'] in enemies]
                if len(dps) >= 2 and len(targets) == len(dps):
                    focus_n[team] += 1
                    focus[team] += len(set(targets)) == 1
                if phase != 'composition':
                    continue
                c = comps[row['comp' + team]]
                if len(dps) >= 2 and len(targets) == len(dps):
                    c['focus_samples'] += 1
                    c['focus'] += len(set(targets)) == 1
                for b in dps:
                    c['dps_samples'] += 1
                    c['no_victim'] += not b['target']
                    spec = specs[f"{b['class']}/{b['spec']}"]
                    spec['alive_samples'] += 1
                    spec['no_victim'] += not b['target']
                    if b['target'] in enemies:
                        c['enemy_target'] += 1
                        enemy = enemies[b['target']]
                        c['healer_target'] += (enemy['class'], enemy['spec']) in HEALERS
        metrics.append(dict(match=row['match'], arena=row['arena'], compA=row['compA'],
                            compH=row['compH'], phase=phase, winner=row['winner'],
                            combat_seconds=combat, contact_seconds=contact,
                            first_death=first_death, observed_deaths=len(dead),
                            focus=dict(focus), focus_samples=dict(focus_n)))
    for c in comps.values():
        c['win_rate'] = c['wins']/c['games'] if c['games'] else None
        c['win_ci95'] = wilson(c['wins'], c['games'])
        c['combat_duration'] = distribution(c.pop('combat_seconds'))
        c['focus_rate'] = c['focus']/c['focus_samples'] if c['focus_samples'] else None
        c['no_victim_rate'] = c['no_victim']/c['dps_samples'] if c['dps_samples'] else None
        c['healer_target_rate'] = c['healer_target']/c['enemy_target'] if c['enemy_target'] else None
    for s in specs.values():
        s['damage_per_combat_second'] = s['damage']/s['seconds'] if s['seconds'] else None
        s['healing_per_combat_second'] = s['healing']/s['seconds'] if s['seconds'] else None
        s['no_victim_rate'] = s['no_victim']/s['alive_samples'] if s['alive_samples'] else None
    for p in pairs.values():
        p['combat_duration'] = distribution(p.pop('durations'))
    outcome = Counter(r['winner'] for r in rows)
    return dict(matches=len(rows), excluded_invalid=len(invalid_rows), verified_telemetry=verified, planned=len(manifest['planned']), outcomes=dict(outcome),
                interrupted=manifest.get('interrupted'),
                interrupted_matches=len(manifest.get('interrupted_matches', [])),
                combat_duration=distribution([m['combat_seconds'] for m in metrics]),
                first_contact=distribution([m['contact_seconds'] for m in metrics if m['contact_seconds'] is not None]),
                first_death=distribution([m['first_death']['seconds'] for m in metrics if m['first_death']]),
                first_death_coverage=sum(m['first_death'] is not None for m in metrics),
                soap_latency_ms=distribution(latencies), compositions=dict(comps),
                specs=dict(specs), pairs=dict(pairs), match_metrics=metrics,
                start_retries=len(manifest['start_errors']),
                caveats=[
                    'Combat duration subtracts the 60-second arena preparation timer; small spawn delays remain.',
                    'DPS/HPS are total logged output divided by whole-match combat time, not time alive.',
                    ('Schema 2 kills/deaths and terminal alive/HP are recorded before cleanup.' if verified else
                     'Legacy kill/death counters and post-match alive/HP values are invalid and excluded.'),
                    'First deaths and focus use roughly 2-second live samples; deaths at match end can be missed.',
                    'No attack victim is not proof of inactivity: CC, casting, movement and stealth can contribute.',
                    'Composition statistics use non-mirror Nagrand matches; interrupted runs may not complete the planned side balance.',
                    ('Actual spec, roles and faction-specific equipment are verified before combat.' if verified else
                     'Legacy spec labels come from the requested lineup; duplicate-class lineups can be misassociated.'),
                    'Small samples and composition/spec coupling preclude claims about player PvP class balance.'
                ])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    summary = analyze(args.folder)
    (args.folder / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k not in ['match_metrics','specs','pairs']}, indent=2))
