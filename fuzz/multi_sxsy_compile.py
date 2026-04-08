# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile lits_pair RBFs at varied (sx, sy) to test whether the R24
broadcast hold is relative to (sx, sy) or absolute.

Sources: (10, 4), (10, 14), (6, 10), (17, 10) — orthogonal moves from
the existing (10, 10) anchor.
For each src, compile a zero baseline and 2 pair targets.
"""
import sys, os
import os as _os
REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runner import compile_route_pair_single_input, compile_route_baseline_abcd

# (sx, sy, [(dx, dy), ...])
SOURCES = [
    (10,  4, [(11,  4), (10,  6)]),
    (10, 14, [(11, 14), (10, 16)]),
    ( 6, 10, [( 7, 10), ( 6, 12)]),
    (17, 10, [(18, 10), (17, 12)]),
]


def main():
    for sx, sy, dsts in SOURCES:
        ztag = f"lits_zero_{sx}_{sy}"
        zpath = f"{REPO}/results/rbf/{ztag}.rbf"
        if not os.path.exists(zpath):
            print(f"compiling {ztag}...", flush=True)
            rbf, t, err = compile_route_baseline_abcd(ztag, sx, sy, 0)
            print(f"  {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")
        for dx, dy in dsts:
            tag = f"lits_pair_X{sx}Y{sy}_to_X{dx}Y{dy}N0_datab"
            rpath = f"{REPO}/results/rbf/{tag}.rbf"
            if os.path.exists(rpath):
                print(f"  exists: {tag}")
                continue
            print(f"compiling {tag}...", flush=True)
            rbf, t, err = compile_route_pair_single_input(
                tag, sx, sy, 0, dx, dy, 0, connect_port="datab")
            print(f"  {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")


if __name__ == "__main__":
    main()
