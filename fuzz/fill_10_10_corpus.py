# SPDX-License-Identifier: GPL-3.0-or-later
"""Step 1 — fill the (10,10) Manhattan corridor with strategic dst samples."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input

DSTS = [
    (10,  2), (10, 21),
    ( 3, 10), (31, 10),
    (13, 13), ( 7,  7),
    (13,  7), ( 7, 13),
    (16,  8),
    (19, 10), (10, 16),
]

def main():
    for dx, dy in DSTS:
        tag = f"lits_pair_X10Y10_to_X{dx}Y{dy}N0_datab"
        path = f"/home/test/EP4CE6/results/rbf/{tag}.rbf"
        if os.path.exists(path):
            print(f"  exists: {tag}")
            continue
        print(f"compiling {tag}...", flush=True)
        rbf, t, err = compile_route_pair_single_input(
            tag, 10, 10, 0, dx, dy, 0, connect_port="datab")
        print(f"  {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")

if __name__ == "__main__":
    main()
