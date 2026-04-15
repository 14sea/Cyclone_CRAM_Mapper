# SPDX-License-Identifier: GPL-3.0-or-later
"""L1 round-trip test for synth_route on a real zero baseline RBF."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from route_synth import synth_route

ROOT = Path(__file__).resolve().parent.parent
ZERO = ROOT / "results" / "rbf" / "lits_zero_10_10.rbf"


CASES = [
    ("(10,10)→(11,10) 1×R4 east",   (10, 10), (11, 10)),
    ("(10,10)→(12,10) 1×R4 east",   (10, 10), (12, 10)),
    ("(10,10)→(10,11) 1×C4 down",   (10, 10), (10, 11)),
    ("(10,10)→(16, 8) C4↑+R4→",     (10, 10), (16,  8)),
    ("(10,10)→(28,21) 7-hop",       (10, 10), (28, 21)),
]


def main():
    base = ZERO.read_bytes()
    print(f"baseline: {ZERO.name}  ({len(base)} bytes)\n")

    for label, src, dst in CASES:
        print(f"=== {label} ===")
        try:
            out, dbg = synth_route(base, src, dst)
        except Exception as e:
            print(f"  ✗ FAIL: {type(e).__name__}: {e}")
            print()
            continue
        if dbg.get("source") == "snapshot":
            # Green-zone LABs now short-circuit through the
            # fingerprint snapshot before the formula path; debug info
            # reports raw ops instead of plan/li_mode.
            print(f"  source: snapshot  ({len(dbg.get('ops', []))} raw ops)")
        else:
            plan = dbg["plan"]
            print(f"  plan ({len(plan)} hops): {[repr(h) for h in plan]}")
            print(f"  li_mode: {dbg['li_mode']}")
        sw = dbg["read_back"]
        c4 = sw.get("c4", [])
        r4 = sw.get("r4", [])
        li = sw.get("li", [])
        print(f"  read-back: C4={len(c4)} R4={len(r4)} LI={len(li)}")

        # Show LI cells at dst LAB
        from bitstream import RouteCodec
        cd = RouteCodec()
        dst_li = []
        for e in li:
            lx, ly, p, b = cd._parse_li_name(e[0])
            if (lx, ly) == dst:
                dst_li.append((p, b))
        print(f"  LI@{dst}: {sorted(dst_li)}")

        # First few C4/R4 wire names
        if c4:
            print(f"  C4 wires: {[w[0] for w in c4[:6]]}")
        if r4:
            print(f"  R4 wires: {[w[0] for w in r4[:6]]}")
        print()


if __name__ == "__main__":
    main()
