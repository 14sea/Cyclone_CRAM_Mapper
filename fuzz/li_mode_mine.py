#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine mode-selection rule from the 21 already-classified LABs.

Source LE is fixed at (X=10, Y=10, N=0) for the entire single-input lut2 sweep.
For each destination LAB we have a mode: "paired" or "alternating".

Hypothesis space:
  - axis (column move dy != 0 vs row move dx != 0)
  - dst_x adjacency to non-LAB columns (5,9,14,15,20,27,30)
  - dst_x parity / dst_y parity
  - distance buckets
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitstream import RouteCodec
from li_topology_validate import (TARGETS, ZERO_TAG, TAG_PREFIX, CONNECT_PORT,
                                   RBF_DIR, load, read_pair_base_set_at,
                                   classify_mode)

NON_LAB_X = {5, 9, 14, 15, 20, 27, 30}

def main():
    codec = RouteCodec()
    zero = load(os.path.join(RBF_DIR, ZERO_TAG + ".rbf"))
    src_x, src_y = 10, 10

    rows = []
    for dx, dy in TARGETS:
        tag = f"{TAG_PREFIX}_X10Y10_to_X{dx}Y{dy}N0_{CONNECT_PORT}"
        path = os.path.join(RBF_DIR, tag + ".rbf")
        if not os.path.exists(path): continue
        cells = read_pair_base_set_at(codec, load(path), zero, dx, dy)
        mode = classify_mode(cells)
        if mode in ("empty", "mixed"): continue
        # Adjacency: dst_x within 1 of any non-LAB column?
        adj_nonlab = min(abs(dx - n) for n in NON_LAB_X)
        axis = "col" if dx == src_x else ("row" if dy == src_y else "diag")
        rows.append((dx, dy, axis, dx - src_x, dy - src_y, adj_nonlab, mode))

    # Print
    print(f"{'dx':>3} {'dy':>3}  {'axis':5} {'Δx':>3} {'Δy':>3} {'nlAdj':>5}  mode")
    for r in rows:
        print(f"{r[0]:3d} {r[1]:3d}  {r[2]:5} {r[3]:+3d} {r[4]:+3d} {r[5]:5d}  {r[6]}")

    # Cross-tabs
    from collections import Counter
    print("\n--- mode by axis ---")
    by_axis = Counter()
    for r in rows:
        by_axis[(r[2], r[6])] += 1
    for k, v in sorted(by_axis.items()): print(f"  {k}: {v}")

    print("\n--- mode by non-LAB adjacency (min dist to {5,9,14,15,20,27,30}) ---")
    by_adj = Counter()
    for r in rows:
        by_adj[(r[5], r[6])] += 1
    for k, v in sorted(by_adj.items()): print(f"  dist={k[0]} {k[1]}: {v}")

    print("\n--- mode by dst_x parity ---")
    by_par = Counter()
    for r in rows:
        by_par[(r[0] % 2, r[6])] += 1
    for k, v in sorted(by_par.items()): print(f"  x%2={k[0]} {k[1]}: {v}")


if __name__ == "__main__":
    main()
