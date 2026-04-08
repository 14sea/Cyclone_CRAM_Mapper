# SPDX-License-Identifier: GPL-3.0-or-later
"""R24 I≠0 address miner via route-cells intersection.

Uses only existing data (route_cells.json + routing_paths STA table) — no
Quartus compiles. For each mined route, we know both:
  - its full CRAM cell set (route_cells.json)
  - its full STA wire list (routing_paths.path_json)

For a target I-index (e.g. I=21), we bucket routes by the specific
R24_X{wx}_Y{wy}_N*_I21 wire they traverse. Cells shared by every route
using the same (wx,wy) are candidates for that wire's R24 bits.

Output: prints per-(wx,wy) candidate cells + per-I global candidate set.
"""
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DB = Path(REPO) / "results" / "ep4ce6_bitdb.sqlite"
CELLS = Path(REPO) / "results" / "route_cells.json"

R24_RE = re.compile(r"R24_X(\d+)_Y(\d+)_N(\d+)_I(\d+)")


def load_route_wires():
    """Map (sx,sy,dx,dy,dn,port) -> set of R24 wires (all I)."""
    db = sqlite3.connect(DB)
    out = defaultdict(list)  # key -> [(wx,wy,wn,wi), ...]
    for sx, sy, dx, dy, pj in db.execute(
        "SELECT src_x, src_y, dst_x, dst_y, path_json FROM routing_paths"):
        try:
            path = json.loads(pj)
        except Exception:
            continue
        wires = []
        port = None
        for h in path:
            loc = h.get("location", "")
            m = R24_RE.match(loc)
            if m:
                wires.append(tuple(int(x) for x in m.groups()))
            # destination N + port from the final LUT input element
            el = h.get("element", "")
            if el in ("data[0]", "data[1]", "data[2]", "data[3]"):
                # map data[i] -> dataa/b/c/d via position? Actually we use the loc
                pass
        # port: path doesn't always have port literal; skip grouping by port
        # (we bucket by wire only)
        if wires:
            out[(sx, sy, dx, dy)].append(wires)
    return out


def main(target_i=21):
    cells = json.loads(CELLS.read_text())  # {"sx,sy->dx,dy,dn,port": [[off,bp],...]}
    wires = load_route_wires()

    # For each route in cells, find its R24 wires at target_i
    # route_cells key format: "sx,sy->dx,dy,dn,port"
    by_wire = defaultdict(list)  # (wx,wy) -> list of cell-sets
    total = 0
    for rk, clist in cells.items():
        lhs, rhs = rk.split("->")
        sx, sy = map(int, lhs.split(","))
        dx, dy, dn, port = rhs.split(",")
        dx, dy = int(dx), int(dy)
        wl = wires.get((sx, sy, dx, dy))
        if not wl:
            continue
        # flatten all R24 wires in all STA paths for this (src,dst)
        flat = []
        for w in wl:
            flat.extend(w)
        r24_ti = [(wx, wy, wn) for (wx, wy, wn, wi) in flat if wi == target_i]
        if not r24_ti:
            continue
        total += 1
        cset = set(tuple(c) for c in clist)
        for wxy in set(r24_ti):
            by_wire[wxy].append(cset)

    print(f"I={target_i}: {total} routes touching this I, "
          f"{len(by_wire)} distinct (wx,wy) buckets")

    # For each (wx,wy) with ≥2 routes, intersect cell sets
    buckets = [(wxy, sets) for wxy, sets in by_wire.items() if len(sets) >= 2]
    buckets.sort(key=lambda x: -len(x[1]))
    print(f"{len(buckets)} buckets with ≥2 routes")
    print()

    # Global intersection across ALL route cells that use ANY R24 I=target
    # (weak — picks up R24 shared overhead)
    all_sets = [s for sets in by_wire.values() for s in sets]
    if all_sets:
        global_inter = set(all_sets[0])
        for s in all_sets[1:]:
            global_inter &= s
        print(f"GLOBAL intersection across {len(all_sets)} (wx,wy,route) pairs: "
              f"{len(global_inter)} cells")
        if global_inter:
            for c in sorted(global_inter)[:10]:
                print(f"  0x{c[0]:05x}.{c[1]}")

    print()
    print("per-(wx,wy) intersections (top 10 by bucket size):")
    for (wxy, sets) in buckets[:10]:
        inter = set(sets[0])
        for s in sets[1:]:
            inter &= s
        # subtract global so we see wire-specific cells
        specific = inter - global_inter if all_sets else inter
        print(f"  {wxy}  n={len(sets):3d}  inter={len(inter):3d}  "
              f"wire-specific={len(specific):3d}")
        for c in sorted(specific)[:5]:
            print(f"    0x{c[0]:05x}.{c[1]}")


if __name__ == "__main__":
    t = int(sys.argv[1]) if len(sys.argv) > 1 else 21
    main(t)
