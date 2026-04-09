# SPDX-License-Identifier: GPL-3.0-or-later
"""Raw-diff fingerprint mine — codec-blind, captures cells the routing
codec can't decode (unmapped R4 I-indices, etc).

For each (sx,sy) source LAB with a baseline + ≥1 lits_pair RBF, intersect
the byte-level XOR diffs to find cells active in 100% of routes. Replaces
the codec-based fingerprint mine for the SOURCE_OVERHEAD_TIES table.
"""
import os, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / 'results' / 'rbf'

SOURCES = [(10,10),(10,14),(4,4),(22,12),(28,18),(16,8),(16,14),(22,16),(16,4),(28,10),
           (4,12),(10,4),(13,10),(19,14),(25,6),(31,12)]


def mine(sx, sy):
    zpath = RBF / f'lits_zero_{sx}_{sy}.rbf'
    if not zpath.exists():
        return None
    zero = zpath.read_bytes()
    name = re.compile(rf'lits_pair_X{sx}Y{sy}_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf')
    routes = {}
    for p in sorted(RBF.glob(f'lits_pair_X{sx}Y{sy}_to_*.rbf')):
        m = name.match(p.name)
        if not m:
            continue
        dx, dy, dn, port = int(m[1]), int(m[2]), int(m[3]), m[4]
        r = p.read_bytes()
        cells = set()
        # Skip the 25-frame bitstream header (frames 0..24 = bytes 32..5281).
        # Header byte deltas are not CRAM and confuse intersection mining.
        HEADER_END = 32 + 25 * 210
        for i in range(HEADER_END, len(zero)):
            # Skip CRC bytes at frame positions 208/209 — without this filter
            # small-corpus mining produces spurious CRC-ghost intersection hits
            # (2026-04-09).
            if (i - 32) % 210 >= 208:
                continue
            x = zero[i] ^ r[i]
            if x:
                for bp in range(8):
                    if x >> bp & 1:
                        cells.add(('raw', i, bp))
        routes[(dx, dy, port)] = cells
    if not routes:
        return None
    all_sets = list(routes.values())
    fp = set(all_sets[0])
    for s in all_sets[1:]:
        fp &= s
    return routes, fp


def main():
    only = set()
    if len(sys.argv) > 1:
        only = {tuple(map(int, a.split(','))) for a in sys.argv[1:]}
    for sx, sy in SOURCES:
        if only and (sx, sy) not in only:
            continue
        result = mine(sx, sy)
        if result is None:
            print(f'({sx},{sy}): no corpus')
            continue
        routes, fp = result
        print(f'({sx:2},{sy:2}): {len(routes):3} routes  fp={len(fp)}')
        for c in sorted(fp):
            print(f'    {c[0]} off={hex(c[1])} bp={c[2]}')
        out = {
            "n_routes": len(routes),
            "fingerprint": sorted([list(c) for c in fp]),
            "per_route_delta": {
                f"{k[0]},{k[1]},{k[2]}": sorted([list(c) for c in (cells - fp)])
                for k, cells in routes.items()
            },
        }
        (ROOT / 'results' / f'fingerprint_{sx}_{sy}.json').write_text(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
