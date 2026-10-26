#!/usr/bin/env python3
"""Tune on fixed side-swapped matchups, then require a fresh holdout before promotion.

Minimum 48 games per stage. A paired sign test and minimum score improvement must
both pass; alpha is Bonferroni-adjusted across the requested generations. Aborted
or unverified matches invalidate evaluation rather than entering the win rate.
"""
import argparse
import itertools
import math
import json
import os
import random
import subprocess
import tempfile
import sys
import time

from benchmark import status, results, server_boot, fits_pool, soap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTL = [sys.executable, os.path.join(ROOT, "controller", "arena_ctl.py")]
PARAMS_FILE = os.path.join(ROOT, "docker", "conf", "arenabrain.params")

# name: (min, max, sigma as fraction of range, integer?)
SPACE = {
    "healerBias":      (0.0, 60.0, 0.20, False),
    "ccBonus":         (0.0, 40.0, 0.20, False),
    "distWeight":      (0.0, 2.0, 0.20, False),
    "swapMargin":      (0.0, 40.0, 0.20, False),
    "minTargetHoldMs": (1000, 12000, 0.20, True),
    "kiteTrigger":     (3.0, 15.0, 0.20, False),
    "kiteDist":        (6.0, 25.0, 0.20, False),
    "kiteStayMs":      (1000, 6000, 0.20, True),
    "kiteCooldownMs":  (2000, 15000, 0.20, True),
}


def ctl(*args, retries=30):
    """Run arena_ctl; retry while the worldserver is restarting (SOAP connection errors)."""
    for attempt in range(retries):
        r = subprocess.run(CTL + list(args), capture_output=True, text=True)
        out = r.stdout.strip()
        if r.returncode == 0 and "SOAP request failed" not in out:
            return out
        time.sleep(10)
    raise SystemExit(f"arena_ctl failed after {retries} tries: {' '.join(args)}\n{r.stderr}\n{out}")


def read_params():
    p = {}
    for line in open(PARAMS_FILE):
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = [s.strip() for s in line.split("=", 1)]
            p[k] = v
    return p


def write_params(p):
    # Promotion is atomic; an interrupted write must not truncate the baseline.
    path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(PARAMS_FILE), delete=False) as f:
            path = f.name
            f.write("# ArenaBrain tunables (key = value). Written by controller/tune.py; reload with `.botarena brain reload`.\n")
            for k, v in p.items():
                f.write(f"{k} = {v}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(path, PARAMS_FILE)
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def fmt(k, v):
    return str(int(round(v))) if SPACE[k][3] else f"{v:.3f}"


def apply(team, p):
    for k, v in p.items():
        ctl("brain", f"set{team}", k, str(v))


def all_results():
    r = subprocess.run(["docker", "compose", "exec", "-T", "worldserver", "cat", "/logs/botarena_matches.jsonl"],
                       cwd=ROOT, capture_output=True, text=True)
    return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]


def results_since(row_count):
    """Rows appended after the first `row_count` lines (match ids restart when the server restarts)."""
    return all_results()[row_count:]


def paired_plan(n, arena="na", seed=1):
    """Same composition and arena for each candidate/baseline side swap."""
    comps = ["rmp", "tsg", "lsd", "beastcleave"]
    matchups = list(itertools.permutations(comps, 2))
    rng = random.Random(seed)
    rng.shuffle(matchups)
    return [dict(pair=i, compA=matchups[i % len(matchups)][0],
                 compH=matchups[i % len(matchups)][1],
                 arena=rng.choice(["na", "be"]) if arena == "random" else arena)
            for i in range(n)]


def run_fixed(jobs, conc, bracket, timeout=3600):
    """Run explicit matches, requiring every expected result from one server process."""
    boot = server_boot()
    cursor = len(results())
    pending, active, completed = list(jobs), {}, []
    deadline = time.monotonic() + timeout
    expected_brains = [line.split(":", 1)[1].strip() for line in soap(".botarena brain show").splitlines()
                       if line.startswith("ArenaBrain ")]
    try:
        while pending or active:
            if server_boot() != boot:
                raise RuntimeError("Server restarted during evaluation; candidate invalid")
            if time.monotonic() > deadline:
                raise RuntimeError("Evaluation timeout; candidate invalid")
            st = status()
            if st['auto'] or st['batch']['active']:
                raise RuntimeError("Another producer started during evaluation")
            rows = results()
            if len(rows) < cursor:
                raise RuntimeError("Result log was truncated")
            for row in rows[cursor:]:
                if row['match'] not in active:
                    raise RuntimeError("Unexpected match result during evaluation")
                job = active.pop(row['match'])
                if [row['brainA'], row['brainH']] != expected_brains:
                    raise RuntimeError("Parameters changed during evaluation")
                if row.get('schema', 0) < 2 or not row.get('valid') or not all(b.get('setupVerified') for b in row['bots']):
                    raise RuntimeError("Unverified bot setup; candidate invalid")
                if (row['compA'], row['compH']) != (job['compA'], job['compH']):
                    raise RuntimeError("Result lineup mismatch")
                completed.append(dict(row, pair=job['pair']))
            cursor = len(rows)
            for _ in range(len(pending)):
                if not pending or len(active) >= conc:
                    break
                job = pending.pop(0)
                if not fits_pool(job, st):
                    pending.append(job)
                    continue
                before = {m['id'] for m in st['matches']}
                reply = soap(f".botarena start {bracket} {job['arena']} {job['compA']} {job['compH']}")
                if 'match started' not in reply:
                    raise RuntimeError(f"Match admission failed: {reply}")
                st = status()
                added = [m for m in st['matches'] if m['id'] not in before]
                if len(added) != 1:
                    raise RuntimeError("Cannot identify new match")
                active[added[0]['id']] = job
            time.sleep(2)
        return completed
    finally:
        if active and server_boot() == boot:
            for mid in active:
                soap(f".botarena stop {mid}")


def wait_idle(timeout=1200):
    deadline = time.monotonic() + timeout
    while status()['matches']:
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out draining arenas before changing parameters")
        time.sleep(2)


def evidence(pair_scores, margin=0.08, alpha=0.05):
    """Exact one-sided paired sign test; neutral pairs supply no evidence.

    Each pair scores 0..2 points (draws count half). Testing pair outcomes avoids
    pretending the two sides of a matchup are independent observations.
    """
    n = len(pair_scores)
    positive = sum(x > 1 for x in pair_scores)
    negative = sum(x < 1 for x in pair_scores)
    decisive = positive + negative
    p = (sum(math.comb(decisive, k) for k in range(positive, decisive + 1)) / 2**decisive
         if decisive else 1.0)
    score = sum(pair_scores) / (2*n) if n else 0.5
    return dict(score=score, matches=2*n, positive_pairs=positive, negative_pairs=negative,
                neutral_pairs=n-decisive, p_value=p, alpha=alpha,
                passed=2*n >= 48 and score >= 0.5 + margin and p <= alpha)


def evaluate(candidate, baseline, jobs, conc, bracket):
    wait_idle()
    apply("A", candidate); apply("H", baseline)
    first = run_fixed(jobs, conc, bracket)
    wait_idle()
    apply("A", baseline); apply("H", candidate)
    swapped = [dict(j, compA=j['compH'], compH=j['compA']) for j in jobs]
    second = run_fixed(swapped, conc, bracket)
    if len(first) != len(jobs) or len(second) != len(jobs):
        raise RuntimeError("Incomplete paired evaluation")
    totals = {j['pair']: 0.0 for j in jobs}
    for side, rows in [("A", first), ("H", second)]:
        for row in rows:
            totals[row['pair']] += 1 if row['winner'] == side else (0.5 if row['winner'] == 'none' else 0)
    return list(totals.values()), first + second


def mutate(p, scale):
    q = dict(p)
    for k, (lo, hi, sig, is_int) in SPACE.items():
        v = float(q.get(k, (lo + hi) / 2))
        v += random.gauss(0, sig * (hi - lo) * scale)
        v = max(lo, min(hi, v))
        q[k] = fmt(k, v)
    return q


def main():
    ap = argparse.ArgumentParser(description="Paired arena tuning with independent holdout promotion")
    ap.add_argument("--matches", type=int, default=24, help="pairs per stage; minimum 24 (48 games)")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--generations", type=int, default=12)
    ap.add_argument("--bracket", choices=["3"], default="3")
    ap.add_argument("--arena", choices=["na", "be", "rl", "random"], default="na")
    ap.add_argument("--holdout-arena", choices=["na", "be", "rl", "random"], default="random")
    ap.add_argument("--margin", type=float, default=0.08)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=20261026)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--log", default=os.path.join(ROOT, "controller", "tune.log"))
    a = ap.parse_args()
    if a.matches < 24 or a.concurrency < 1 or a.generations < 1:
        ap.error("Use at least 24 pairs, one arena and one generation")
    if not 0 < a.alpha < 1 or not 0 <= a.margin <= 0.5:
        ap.error("alpha must be in (0,1); margin in [0,0.5]")
    random.seed(a.seed)
    original = status()
    if original['batch']['active']:
        raise SystemExit("An existing batch is active; finish or stop it before tuning")
    soap(".botarena auto off")
    baseline = read_params()  # Preserve and apply every parameter, including boolean controls.
    for k in SPACE:
        baseline.setdefault(k, fmt(k, (SPACE[k][0] + SPACE[k][1]) / 2))
    train = paired_plan(a.matches, a.arena, a.seed)
    try:
        with open(a.log, "a") as log:
            def record(value):
                print(json.dumps(value), flush=True)
                log.write(json.dumps(value) + "\n"); log.flush()
            record(dict(event="paired_start", baseline=baseline, plan=train, config=vars(a), time=time.time()))
            for g in range(1, a.generations + 1):
                cand = mutate(baseline, a.scale)
                t0 = time.time()
                scores, rows = evaluate(cand, baseline, train, a.concurrency, a.bracket)
                training = evidence(scores, a.margin, a.alpha/a.generations)
                holdout = None
                if training['passed']:
                    holdout_plan = paired_plan(a.matches, a.holdout_arena, a.seed + 10000 + g)
                    hscores, hrows = evaluate(cand, baseline, holdout_plan, a.concurrency, a.bracket)
                    holdout = evidence(hscores, a.margin, a.alpha/a.generations)
                    record(dict(event="holdout", gen=g, plan=holdout_plan, evidence=holdout, results=hrows))
                accepted = bool(holdout and holdout['passed'])
                record(dict(event="gen", gen=g, candidate=cand, training=training,
                            accepted=accepted, results=rows, secs=int(time.time()-t0)))
                if accepted:
                    baseline = cand
                    write_params(baseline)
            record(dict(event="end", baseline=baseline, time=time.time()))
    finally:
        # Restore persisted settings even after invalid/incomplete evaluations.
        wait_idle()
        apply("A", baseline); apply("H", baseline)
        soap(".botarena auto " + ("on 20" if original['auto'] else "off"))


if __name__ == "__main__":
    main()
