# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-mine fingerprint snapshots for jailbreak/edge islands from existing
pair RBFs.

The Y=15 (seven islands) and Y=5 (two islands) edge-island snapshots in
`results/fingerprint_{sx}_{sy}.json` were produced by an older mining
pass whose extraction logic disagrees with the current `RouteCodec.read_switches`
classifier — the per_route_delta entries miss ~14 classifiable switch
cells per route, so `synth_route` under-emits and the green-zone harness
scores 4/5 per edge island.

The pair RBFs on disk already cover the 5 snapshot dsts × 9 sources = 45
routes (plus a handful of N=2 variants). This script re-derives each
snapshot via the same formula as `fingerprint_10_14_mine.py`:

    routes[(dx,dy,dn,port)] = read_switches(pair_rbf, zero)
    fingerprint = intersection of all routes' cell sets
    per_route_delta[(dx,dy,port)] = (cells - fingerprint) unioned across N variants

Multi-N collision (e.g. (10,10,0,datab) and (10,10,2,datab) both land on
key '10,10,datab') is resolved by union — `synth_route`'s raw-ops path
then over-emits safely; the N=0 variant's cells are a subset of the union.
Writing cells common to both N variants is a no-op on subsequent N=0
reads.

Runs in parallel across islands via multiprocessing.
"""
import sys, os, re, json, multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import defaultdict
from pathlib import Path


EDGE_ISLANDS = [
    (10, 15), (11, 15), (12, 15), (13, 15), (14, 15), (17, 15), (18, 15),
    (18, 5), (19, 5),
]

ROOT = Path(__file__).resolve().parent.parent
RBF_DIR = ROOT / 'results' / 'rbf'


def mine_one(sxsy):
    sx, sy = sxsy
    # Imports inside worker so each process gets its own codec.
    import sys
    sys.path.insert(0, str(ROOT / 'fuzz'))
    from bitstream import RouteCodec

    codec = RouteCodec()
    zero_path = RBF_DIR / f'lits_zero_{sx}_{sy}.rbf'
    if not zero_path.exists():
        return sx, sy, f'missing zero baseline {zero_path.name}'
    zero = zero_path.read_bytes()

    name_re = re.compile(rf'lits_pair_X{sx}Y{sy}_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf')
    routes = {}
    for path in sorted(RBF_DIR.glob(f'lits_pair_X{sx}Y{sy}_to_*.rbf')):
        m = name_re.match(path.name)
        if not m:
            continue
        dx, dy, dn, port = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        try:
            sw = codec.read_switches(path.read_bytes(), zero)
        except Exception as e:
            continue
        cells = {(t, e[1], e[2]) for t, lst in sw.items() for e in lst}
        routes[(dx, dy, dn, port)] = cells

    if not routes:
        return sx, sy, 'no routes found on disk'

    all_sets = list(routes.values())
    fp = set(all_sets[0])
    for s in all_sets[1:]:
        fp &= s

    # Collapse N variants onto (dx,dy,port) keys by unioning deltas.
    per = defaultdict(set)
    for (dx, dy, dn, port), cells in routes.items():
        per[(dx, dy, port)] |= (cells - fp)

    snap = {
        "n_routes": len(routes),
        "fingerprint": sorted([list(c) for c in fp]),
        "per_route_delta": {
            f"{dx},{dy},{port}": sorted([list(c) for c in cells])
            for (dx, dy, port), cells in per.items()
        },
    }

    out = ROOT / 'results' / f'fingerprint_{sx}_{sy}.json'
    # Backup the old snapshot once, for audit trail.
    bak = out.with_suffix('.json.preremine_bak')
    if out.exists() and not bak.exists():
        bak.write_bytes(out.read_bytes())
    out.write_text(json.dumps(snap, indent=1))

    fp_n = len(fp)
    dst_n = len(per)
    return sx, sy, f'OK  routes={len(routes)}  fp={fp_n}  dsts={dst_n}'


def main():
    with mp.Pool(processes=min(len(EDGE_ISLANDS), mp.cpu_count())) as pool:
        for sx, sy, msg in pool.imap_unordered(mine_one, EDGE_ISLANDS):
            print(f'({sx},{sy}): {msg}')


if __name__ == '__main__':
    main()
