# SPDX-License-Identifier: GPL-3.0-or-later
"""β expansion — push (10,14) corpus to ~30+ routes to kill small-N inflation."""
import sys, os
import os as _os
REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input, compile_route_baseline_abcd

SX, SY = 10, 14

# New DSTs (avoid duplicating fill_10_14_corpus.py)
DSTS = [
    # column hops
    (10,  2), (10,  6), (10, 18),
    # row hops east/west
    (17, 14), (19, 14), (22, 14), (25, 14), (28, 14), (31, 14),
    ( 6, 14), ( 3, 14),
    # diagonals
    (13, 17), (16, 17), (19, 11), (22,  8),
    ( 7, 17), ( 4, 11), ( 7,  8),
    # far reaches
    ( 3,  2), (31,  2), ( 3, 21), (31, 21),
    (16,  4), (22, 18), (28,  4),
]


def main():
    ztag = f"lits_zero_{SX}_{SY}"
    if not os.path.exists(f"{REPO}/results/rbf/{ztag}.rbf"):
        rbf, t, err = compile_route_baseline_abcd(ztag, SX, SY, 0)
        print(f"baseline: {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")

    ok = fail = 0
    for dx, dy in DSTS:
        tag = f"lits_pair_X{SX}Y{SY}_to_X{dx}Y{dy}N0_datab"
        path = f"{REPO}/results/rbf/{tag}.rbf"
        if os.path.exists(path):
            ok += 1
            continue
        print(f"compiling {tag}...", flush=True)
        rbf, t, err = compile_route_pair_single_input(
            tag, SX, SY, 0, dx, dy, 0, connect_port="datab")
        if rbf:
            ok += 1
            print(f"  OK ({t:.1f}s)")
        else:
            fail += 1
            print(f"  FAIL ({t:.1f}s) {(err or '').split(';')[0][:80]}")
    print(f"\nsummary: {ok} OK, {fail} fail")


if __name__ == "__main__":
    main()
