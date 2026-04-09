# SPDX-License-Identifier: GPL-3.0-or-later
"""Task A — streaming per-source fingerprint miner.

Watches results/rbf/nv_pair_*.rbf, groups by (sx,sy,sn). When a source
has ≥ MIN_ROUTES completed routes, computes the cell-set intersection
(XOR-diff vs a neutral baseline, CRC-filtered) and writes
results/nv_fingerprint_{sx}_{sy}_{sn}.json. Re-mines when new routes
arrive at already-fingerprinted sources. Runs continuously; exits when
the factory finishes AND no backlog remains.
"""
import os, re, sys, time, json, subprocess
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / 'results' / 'rbf'
OUT = ROOT / 'results' / 'nv_fingerprints'
OUT.mkdir(parents=True, exist_ok=True)
BASE_RBF = RBF / 'nv_zero_global.rbf'

MIN_ROUTES = 3
POLL_SEC = 120
HDR_END = 32 + 25 * 210

NAME_RE = re.compile(
    r'nv_pair_X(\d+)Y(\d+)N(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf$'
)


def diff_cells(target, zero):
    cells = set()
    for n in range(25, 1752):
        s = 32 + n * 210
        for off in range(s, s + 208):
            x = target[off] ^ zero[off]
            if x:
                for bp in range(8):
                    if (x >> bp) & 1:
                        cells.add((off, bp))
    return cells


def group_by_source():
    buckets = defaultdict(list)
    for p in RBF.glob('nv_pair_*.rbf'):
        m = NAME_RE.match(p.name)
        if not m:
            continue
        sx, sy, sn = int(m[1]), int(m[2]), int(m[3])
        dx, dy, dn, port = int(m[4]), int(m[5]), int(m[6]), m[7]
        buckets[(sx, sy, sn)].append((dx, dy, dn, port, p))
    return buckets


def factory_alive():
    try:
        subprocess.check_output(['pgrep', '-f', 'plan_d_prime_factory'])
        return True
    except subprocess.CalledProcessError:
        return False


def mine_source(src, routes, zero):
    sx, sy, sn = src
    all_sets = []
    per = {}
    for dx, dy, dn, port, p in sorted(routes):
        cs = diff_cells(p.read_bytes(), zero)
        all_sets.append(cs)
        per[f'{dx},{dy},{dn},{port}'] = sorted([list(c) for c in cs])
    fp = set(all_sets[0])
    for s in all_sets[1:]:
        fp &= s
    return {
        'src': [sx, sy, sn],
        'n_routes': len(all_sets),
        'fp_size': len(fp),
        'fingerprint': sorted([list(c) for c in fp]),
        'per_route_delta': {k: sorted([list(c) for c in (set(map(tuple, v)) - fp)])
                            for k, v in per.items()},
    }


def main():
    if not BASE_RBF.exists():
        print(f'baseline missing: {BASE_RBF}')
        sys.exit(1)
    zero = BASE_RBF.read_bytes()
    last_mined_n = {}  # src -> n_routes at last mine
    print(f'[fp-stream] start; baseline={BASE_RBF.name} min_routes={MIN_ROUTES}',
          flush=True)

    backlog_empty_rounds = 0
    while True:
        buckets = group_by_source()
        ready = [(src, r) for src, r in buckets.items() if len(r) >= MIN_ROUTES]
        new_or_grown = [(src, r) for src, r in ready
                        if len(r) != last_mined_n.get(src, 0)]
        if new_or_grown:
            ts = time.strftime('%H:%M:%S')
            print(f'[fp-stream {ts}] mining {len(new_or_grown)} sources '
                  f'(total ready: {len(ready)})', flush=True)
            for src, routes in new_or_grown:
                try:
                    result = mine_source(src, routes, zero)
                    out_path = OUT / f'nv_fp_{src[0]}_{src[1]}_{src[2]}.json'
                    tmp = out_path.with_suffix('.tmp')
                    tmp.write_text(json.dumps(result))
                    os.replace(tmp, out_path)
                    last_mined_n[src] = len(routes)
                    print(f'  ({src[0]:2},{src[1]:2},{src[2]:2}): '
                          f'{len(routes)} routes fp={result["fp_size"]}',
                          flush=True)
                except Exception as e:
                    print(f'  ERR ({src}): {e}', flush=True)
            backlog_empty_rounds = 0
        else:
            backlog_empty_rounds += 1

        alive = factory_alive()
        if not alive and backlog_empty_rounds >= 2:
            print(f'[fp-stream] factory done + backlog empty — exit. '
                  f'Mined {len(last_mined_n)} sources.', flush=True)
            break
        time.sleep(POLL_SEC)


if __name__ == '__main__':
    main()
