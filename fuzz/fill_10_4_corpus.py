# SPDX-License-Identifier: GPL-3.0-or-later
"""ζ step 1 — fill the (16,8) left-center upper corpus.

Sixth green-zone candidate. (16,8) is left-center upper, complementing the
existing islands which cluster on the right (α 10,10; β 10,14; δ 22,12;
ε 28,18) or in corners (γ 4,4). Provides a midpoint data point for the
"fingerprint size depends on physical anomalies near source" hypothesis —
(16,8) is a clean interior LAB with no M9K boundary, no corner.
"""
import sys, os
import os as _os
REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input, compile_route_baseline_abcd

SX, SY = 10, 4

DSTS = [
    # near hops in 4 directions
    (18,  8), (21,  8), (23,  8),
    (13,  8), (11,  8), ( 8,  8),
    (16, 10), (16, 12), (16, 14),
    (16,  6), (16,  4), (16,  2),
    # diagonals
    (18, 10), (21, 12), (23, 14),
    (13, 10), (11, 12), ( 8, 14),
    (18,  6), (21,  4), (23,  2),
    (13,  6), (11,  4), ( 8,  2),
    # far reaches
    ( 4,  8), (28,  8), (31,  8),
    (16, 18), (16, 21),
    ( 4, 21), (31, 21),
]


def main():
    ztag = f"lits_zero_{SX}_{SY}"
    if not os.path.exists(f"{REPO}/results/rbf/{ztag}.rbf"):
        print(f"compiling {ztag}...", flush=True)
        rbf, t, err = compile_route_baseline_abcd(ztag, SX, SY, 0)
        print(f"  {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")
        if not rbf:
            print("baseline failed — aborting")
            return

    ok = fail = 0
    for dx, dy in DSTS:
        tag = f"lits_pair_X{SX}Y{SY}_to_X{dx}Y{dy}N0_datab"
        path = f"{REPO}/results/rbf/{tag}.rbf"
        if os.path.exists(path):
            print(f"  exists: {tag}")
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
            short = (err or "").split(";")[0][:80]
            print(f"  FAIL ({t:.1f}s) {short}")
    print(f"\nsummary: {ok} OK, {fail} fail")


if __name__ == "__main__":
    main()
