#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dump the 21-LAB LI mode classification to a JSON snapshot.

The underlying lits_pair_* RBFs are gitignored (results/rbf/), so without
this snapshot a fresh checkout has to recompile ~22 designs (~2 min) just to
recover the 'paired vs alternating' label per LAB.

Source: src=(X10,Y10,N0), dst sweep over 24 LABs, single-input lut2,
        connect_port=datab.

Output: results/li_lab_classification.json
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitstream import RouteCodec
from li_topology_validate import (TARGETS, ZERO_TAG, TAG_PREFIX, CONNECT_PORT,
                                   RBF_DIR, load, read_pair_base_set_at,
                                   classify_mode)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "results", "li_lab_classification.json")

def main():
    codec = RouteCodec()
    zero = load(os.path.join(RBF_DIR, ZERO_TAG + ".rbf"))

    samples = []
    for dx, dy in TARGETS:
        tag = f"{TAG_PREFIX}_X10Y10_to_X{dx}Y{dy}N0_{CONNECT_PORT}"
        path = os.path.join(RBF_DIR, tag + ".rbf")
        if not os.path.exists(path):
            samples.append({"dst_x": dx, "dst_y": dy, "status": "missing_rbf"})
            continue
        cells = read_pair_base_set_at(codec, load(path), zero, dx, dy)
        mode = classify_mode(cells)
        samples.append({
            "dst_x": dx, "dst_y": dy,
            "mode": mode,
            "n_cells": len(cells),
            "cells": sorted([list(c) for c in cells]),
        })

    snapshot = {
        "generated_by": "fuzz/dump_li_classification.py",
        "source": {"x": 10, "y": 10, "n": 0},
        "connect_port": CONNECT_PORT,
        "verilog_template": "gen_two_luts_single_input (lut2 unused inputs tied to 1'b0)",
        "cell_format": "[pair_index_0_to_8, base_idx_0_or_1] where base_idx 0=offset70 1=offset71",
        "modes": {
            "paired": "P0 paired (B0+B1) + 4 middle pairs paired + P8 single tail = 9 cells",
            "alternating": "P0..P7 single base alternating B1,B0,B1,...,B0 + P8 single tail = 9 cells",
        },
        "samples": samples,
    }
    with open(OUT, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"wrote {OUT}")
    print(f"  {sum(1 for s in samples if s.get('mode')=='paired')} paired")
    print(f"  {sum(1 for s in samples if s.get('mode')=='alternating')} alternating")
    print(f"  {sum(1 for s in samples if s.get('status')=='missing_rbf')} missing")


if __name__ == "__main__":
    main()
