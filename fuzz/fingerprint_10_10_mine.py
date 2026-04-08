# SPDX-License-Identifier: GPL-3.0-or-later
"""Step 2 — extract the (10,10) source fingerprint by intersecting all
lits_pair_X10Y10_to_*.rbf cell sets, then break down the per-route delta.

Source fingerprint = bits present in EVERY (10,10)-source route. These
are the unconditional source-side activations (LE driver MUX, R24
broadcast hold, R4 launch pair, possibly some C4/LI).

Per-route delta = remaining bits after subtracting the fingerprint.
Categorized by type for the snapshot table.
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import defaultdict, Counter
from pathlib import Path
from bitstream import RouteCodec

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / 'results' / 'rbf'
ZERO = RBF / 'lits_zero_10_10.rbf'
NAME = re.compile(r'lits_pair_X10Y10_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf')


def cells_with_type(codec, rbf, zero):
    """Return set of (type, off, bp) — physical bits with their type label."""
    sw = codec.read_switches(rbf, zero)
    out = set()
    for t, lst in sw.items():
        for e in lst:
            out.add((t, e[1], e[2]))
    return out


def main():
    codec = RouteCodec()
    zero = ZERO.read_bytes()

    routes = {}  # (dx,dy,port) -> set((t,off,bp))
    for path in sorted(RBF.glob('lits_pair_X10Y10_to_*.rbf')):
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

    print(f"=== mined {len(routes)} (10,10)-source routes ===\n")

    # Intersect all
    all_sets = list(routes.values())
    fingerprint = set(all_sets[0])
    for s in all_sets[1:]:
        fingerprint &= s

    print(f"=== source fingerprint: {len(fingerprint)} bits (in 100% of routes) ===")
    by_type = Counter(t for t, _, _ in fingerprint)
    print(f"  by type: {dict(by_type)}\n")
    for t, off, bp in sorted(fingerprint):
        print(f"  {t:6s} off={off:#08x} bp={bp}")

    # Per-route delta sizes
    print(f"\n=== per-route delta (cells beyond fingerprint) ===")
    delta_sizes = []
    for k, cells in sorted(routes.items()):
        delta = cells - fingerprint
        delta_sizes.append(len(delta))
        bt = Counter(t for t, _, _ in delta)
        print(f"  {k}: total={len(cells):3d} delta={len(delta):3d}  {dict(bt)}")

    # Cells that appear in ≥80% but <100% of routes — "near-universal" candidates
    print(f"\n=== near-universal cells (≥80%, <100%) ===")
    cell_freq = Counter()
    for cells in all_sets:
        for c in cells:
            cell_freq[c] += 1
    n = len(all_sets)
    near = [(c, ct) for c, ct in cell_freq.items() if ct >= 0.8 * n and ct < n]
    near.sort(key=lambda x: -x[1])
    print(f"  {len(near)} cells qualify")
    bt = Counter(c[0] for c, _ in near)
    print(f"  by type: {dict(bt)}")
    for c, ct in near[:20]:
        print(f"  {ct}/{n}  {c[0]:6s} off={c[1]:#08x} bp={c[2]}")

    # Save fingerprint as JSON
    out = {
        "n_routes": len(routes),
        "fingerprint": sorted([list(c) for c in fingerprint]),
        "per_route_delta": {
            f"{k[0]},{k[1]},{k[2]}": sorted([list(c) for c in (cells - fingerprint)])
            for k, cells in routes.items()
        },
    }
    p = ROOT / 'results' / 'fingerprint_10_10.json'
    p.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
