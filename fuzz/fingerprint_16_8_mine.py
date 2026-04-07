# SPDX-License-Identifier: GPL-3.0-or-later
"""ε — extract the (16,8) source fingerprint, the 6th green-zone candidate.

Geometric opposite of γ (4,4): far-right, near-bottom interior. Tests
whether the corner→tiny-fingerprint pattern (γ=1 bit) generalizes to the
opposite corner, and adds a 6th data point for the per-source fingerprint
size mystery (α=6, β=11, γ=1, δ=1, ε=?).
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import Counter
from pathlib import Path
from bitstream import RouteCodec

SX, SY = 16, 8
ROOT = Path('/home/test/EP4CE6')
RBF = ROOT / 'results' / 'rbf'
ZERO = RBF / f'lits_zero_{SX}_{SY}.rbf'
NAME = re.compile(rf'lits_pair_X{SX}Y{SY}_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf')


def cells_with_type(codec, rbf, zero):
    sw = codec.read_switches(rbf, zero)
    out = set()
    for t, lst in sw.items():
        for e in lst:
            out.add((t, e[1], e[2]))
    return out


def main():
    codec = RouteCodec()
    zero = ZERO.read_bytes()

    routes = {}
    for path in sorted(RBF.glob(f'lits_pair_X{SX}Y{SY}_to_*.rbf')):
        m = NAME.match(path.name)
        if not m:
            continue
        dx, dy, dn, port = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        try:
            cells = cells_with_type(codec, path.read_bytes(), zero)
        except Exception as e:
            print(f"  skip {path.name}: {e}")
            continue
        routes[(dx, dy, port)] = cells

    print(f"=== mined {len(routes)} ({SX},{SY})-source routes ===\n")

    all_sets = list(routes.values())
    fingerprint = set(all_sets[0])
    for s in all_sets[1:]:
        fingerprint &= s

    print(f"=== source fingerprint: {len(fingerprint)} bits (in 100% of routes) ===")
    by_type = Counter(t for t, _, _ in fingerprint)
    print(f"  by type: {dict(by_type)}\n")
    for t, off, bp in sorted(fingerprint):
        print(f"  {t:6s} off={off:#08x} bp={bp}")

    print(f"\n=== per-route delta (cells beyond fingerprint) ===")
    for k, cells in sorted(routes.items()):
        delta = cells - fingerprint
        bt = Counter(t for t, _, _ in delta)
        print(f"  {k}: total={len(cells):3d} delta={len(delta):3d}  {dict(bt)}")

    out = {
        "n_routes": len(routes),
        "fingerprint": sorted([list(c) for c in fingerprint]),
        "per_route_delta": {
            f"{k[0]},{k[1]},{k[2]}": sorted([list(c) for c in (cells - fingerprint)])
            for k, cells in routes.items()
        },
    }
    p = ROOT / 'results' / f'fingerprint_{SX}_{SY}.json'
    p.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
