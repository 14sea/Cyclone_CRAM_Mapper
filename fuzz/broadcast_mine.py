# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine the 'broadcast fanout' pattern: R24/C4 cells that span many Y at
the same (wx, I) for a single point-to-point route.

Hypothesis: Quartus emits a column-broadcast tail (same I-index across
the full Y range of the column) for clock/anti-glitch alignment, not
just the strict src->dst path. If universal, route_synth can emit it
unconditionally.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import defaultdict, Counter
from pathlib import Path

from bitstream import RouteCodec

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / "results" / "rbf"
ZERO = RBF / "lits_zero_10_10.rbf"
NAME = re.compile(r"lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf")
WIRE = re.compile(r"(R24|R4|C4)_X(\d+)_Y(\d+)_N\d+_I(\d+)")


def main():
    codec = RouteCodec()
    zero = ZERO.read_bytes()

    # For each route, group cells by (type, wx, I) -> set of Y values
    # Look for groups with |Y|>=3 (a "broadcast")
    broadcast_per_route = {}  # route_key -> list of (type, wx, I, sorted_Y_tuple)

    for path in sorted(RBF.glob("lits_pair_*.rbf")):
        m = NAME.match(path.name)
        if not m:
            continue
        sx, sy, dx, dy, dn = (int(m.group(i)) for i in range(1, 6))
        port = m.group(6)
        try:
            data = path.read_bytes()
            sw = codec.read_switches(data, zero)
        except Exception:
            continue

        groups = defaultdict(set)
        for t in ("c4", "r4", "r24"):
            for entry in sw.get(t, []):
                mm = WIRE.match(entry[0])
                if not mm:
                    continue
                wt, wx, wy, ii = mm.group(1), int(mm.group(2)), int(mm.group(3)), int(mm.group(4))
                groups[(wt, wx, ii)].add(wy)

        bcasts = [(wt, wx, ii, tuple(sorted(ys))) for (wt, wx, ii), ys in groups.items() if len(ys) >= 3]
        broadcast_per_route[(sx, sy, dx, dy, port)] = bcasts

    # Aggregate: which (rel_wx, I) broadcasts appear in many routes?
    by_geom = defaultdict(Counter)  # (type, ddx, ddy_sign) -> Counter[(rel_wx, I, len_Y)]
    universal = Counter()  # (type, rel_wx, I) regardless of geom
    for (sx, sy, dx, dy, port), bcasts in broadcast_per_route.items():
        ddx = dx - sx
        ddy = dy - sy
        for wt, wx, ii, ys in bcasts:
            key = (wt, wx - sx, ii)
            universal[key] += 1
            by_geom[(wt, ddx, ddy)][(wx - sx, ii, len(ys))] += 1

    n_routes = len(broadcast_per_route)
    print(f"=== broadcast cells across {n_routes} routes ===\n")
    print("universal (type, rel_wx, I) — appears in N routes:")
    for k, n in universal.most_common(20):
        pct = 100 * n / n_routes
        print(f"  {k}: {n}/{n_routes} ({pct:.0f}%)")

    print(f"\n=== sample broadcasts per route (first 6) ===")
    for k in sorted(broadcast_per_route)[:6]:
        bs = broadcast_per_route[k]
        print(f"  {k}: {len(bs)} broadcasts")
        for wt, wx, ii, ys in bs[:5]:
            print(f"     {wt}_X{wx}_I{ii}  Y={ys}")

    # Y-pattern analysis: do broadcasts always cover the SAME Y set?
    print(f"\n=== Y-set frequency for top universal broadcast ===")
    top_key = universal.most_common(1)[0][0]
    wt, rel_wx, ii = top_key
    yset_ctr = Counter()
    for (sx, sy, dx, dy, port), bcasts in broadcast_per_route.items():
        for w, wx, i, ys in bcasts:
            if (w, wx - sx, i) == top_key:
                # normalize Y by sy
                yset_ctr[tuple(y - sy for y in ys)] += 1
    for ys, n in yset_ctr.most_common(8):
        print(f"  rel_Y={ys}: {n}")


if __name__ == "__main__":
    main()
