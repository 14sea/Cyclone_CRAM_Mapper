# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 6 — nextpnr chipdb skeleton exporter for EP4CE6.

Dumps what we currently know about the CE6 fabric into a JSON file that a
future nextpnr-generic backend can ingest. This is a *skeleton*: BELs and
wires are authoritative (from silicon-verified geometry), but pips are
limited to the (src,dst,port) routes we've actually mined into
route_cells.json.

Output: results/ep4ce6_chipdb.json
  {
    "device": "EP4CE6F17C8",
    "grid": {"lab_x": [...], "lab_y": [...], "n": [...]},
    "bels": [{"name": "LCCOMB_X3_Y2_N0", "type": "LCCOMB",
              "x": 3, "y": 2, "n": 0}, ...],
    "wires": [{"name": "LOCAL_INTERCONNECT_X3_Y2_N0_I0", "type": "LI"}, ...],
    "pips": [{"src_bel": "LCCOMB_X4_Y4_N0",
              "dst_bel": "LCCOMB_X10_Y10_N0",
              "dst_port": "datab",
              "cells": [[offset, bit], ...]}, ...]
  }

The "cells" field is the raw CRAM bit-flip set — nextpnr doesn't need it
for pathfinding, but keeping it inline lets the bitgen half of any future
backend skip a second lookup.
"""
import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import config  # noqa: E402


def build_bels():
    bels = []
    # CE6 whitelist. Jailbreak columns/rows can be added via --jailbreak.
    for x in config.LAB_X:
        for y in config.LAB_Y:
            for n in config.LE_N:
                bels.append({
                    "name": f"LCCOMB_X{x}_Y{y}_N{n}",
                    "type": "LCCOMB",
                    "x": x, "y": y, "n": n,
                })
    return bels


def build_pips():
    """One pip per entry in route_cells.json."""
    path = Path(REPO) / "results" / "route_cells.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    pips = []
    for key, cells in data.items():
        lhs, rhs = key.split("->")
        sx, sy = map(int, lhs.split(","))
        dx, dy, dn, port = rhs.split(",")
        pips.append({
            "src_bel": f"LCCOMB_X{sx}_Y{sy}_N0",
            "dst_bel": f"LCCOMB_X{dx}_Y{dy}_N{dn}",
            "dst_port": port,
            "cells": cells,
        })
    return pips


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(REPO) / "results" / "ep4ce6_chipdb.json"))
    ap.add_argument("--jailbreak", action="store_true",
                    help="Include X=5,9,14,30,32,33 and Y=15 jailbreak bels")
    args = ap.parse_args()

    if args.jailbreak:
        config.LAB_X = sorted(set(config.LAB_X) | {5, 9, 14, 30, 32, 33})
        config.LAB_Y = sorted(set(config.LAB_Y) | {15})

    bels = build_bels()
    pips = build_pips()

    # Unique wires = union of pip endpoints + all BEL input ports seen.
    wires = set()
    for p in pips:
        wires.add((p["dst_bel"], p["dst_port"]))
    wire_list = [{"name": f"{bel}.{port}", "type": "BEL_INPUT"}
                 for bel, port in sorted(wires)]

    chipdb = {
        "device": config.DEVICE,
        "family": config.FAMILY,
        "grid": {
            "lab_x": config.LAB_X,
            "lab_y": config.LAB_Y,
            "n": config.LE_N,
        },
        "bels": bels,
        "wires": wire_list,
        "pips": pips,
        "stats": {
            "num_bels": len(bels),
            "num_wires": len(wire_list),
            "num_pips": len(pips),
        },
    }
    Path(args.out).write_text(json.dumps(chipdb, indent=1))
    print(f"wrote {args.out}")
    print(f"  bels={len(bels)} wires={len(wire_list)} pips={len(pips)}")
    ports = {}
    for p in pips:
        ports[p["dst_port"]] = ports.get(p["dst_port"], 0) + 1
    print(f"  pip ports: {ports}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
