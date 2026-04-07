# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine which R4 (wx, i_idx) Quartus picks per (src, dst, port).

Walks lits_pair_*.rbf, reads R4 switches via RouteCodec, and tabulates
the wire identities Quartus chose. Output: per-(src,dst,port) lookup
table for route_synth so adjacent horizontal hops use the right I-index.
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import Counter, defaultdict
from pathlib import Path

from bitstream import RouteCodec

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / "results" / "rbf"
ZERO = RBF / "lits_zero_10_10.rbf"
NAME = re.compile(r"lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf")
WIRE = re.compile(r"R4_X(\d+)_Y(\d+)_N\d+_I(\d+)")


def main():
    codec = RouteCodec()
    zero = ZERO.read_bytes()

    by_route = defaultdict(list)  # (sx,sy,dx,dy,port) -> list of (wx,wy,i)
    by_geom = defaultdict(Counter)  # (ddx,ddy,port) -> Counter[(rel_wx,i)]

    for path in sorted(RBF.glob("lits_pair_*.rbf")):
        m = NAME.match(path.name)
        if not m:
            continue
        sx, sy, dx, dy, dn = (int(m.group(i)) for i in range(1, 6))
        port = m.group(6)
        try:
            data = path.read_bytes()
            r4 = codec.read_r4(data, zero)
        except Exception:
            continue

        seen = set()
        for name, _, _ in r4:
            mm = WIRE.match(name)
            if not mm:
                continue
            wx, wy, ii = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
            # corridor filter
            xlo, xhi = min(sx, dx) - 1, max(sx, dx) + 1
            ylo, yhi = min(sy, dy) - 1, max(sy, dy) + 1
            if not (xlo <= wx <= xhi and ylo <= wy <= yhi):
                continue
            key = (wx, wy, ii)
            if key in seen:
                continue
            seen.add(key)
            by_route[(sx, sy, dx, dy, port)].append(key)
            by_geom[(dx - sx, dy - sy, port)][(wx - sx, ii)] += 1

    print(f"=== R4 by-geometry histogram ({sum(len(v) for v in by_route.values())} cells) ===")
    for geom in sorted(by_geom):
        ctr = by_geom[geom]
        ddx, ddy, port = geom
        top = ctr.most_common(5)
        print(f"  ddx={ddx:+d} ddy={ddy:+d} {port}: {top}")

    print(f"\n=== per-route entries: {len(by_route)} ===")
    for k in sorted(by_route)[:6]:
        print(f"  {k}: {by_route[k]}")

    out = ROOT / "results" / "r4_iindex_table.json"
    table = {f"{sx},{sy},{dx},{dy},{port}": [list(c) for c in cells]
             for (sx, sy, dx, dy, port), cells in by_route.items()}
    out.write_text(json.dumps(table, indent=2))
    print(f"\nwrote {out} ({len(table)} entries)")


if __name__ == "__main__":
    main()
