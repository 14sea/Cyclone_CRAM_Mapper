# SPDX-License-Identifier: GPL-3.0-or-later
"""ε step 1 — fill the (28,18) far-right-bottom corpus.

Fifth green-zone candidate. (28,18) is the geometric opposite of γ (4,4):
deep into the bottom-right quadrant, two columns from right edge, three
rows from bottom edge. Tests whether opposite-corner sources behave
symmetrically (and whether the corner→1bit fingerprint pattern from γ
generalizes).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input, compile_route_baseline_abcd

SX, SY = 28, 18

DSTS = [
    # short corridor toward chip interior
    (26, 18), (24, 18), (22, 18), (19, 18),
    (28, 16), (28, 14), (28, 12), (28, 10),
    # diagonals into the chip
    (26, 16), (24, 14), (22, 12), (19, 10),
    # far reaches (R24/C16 territory)
    (16, 18), (10, 18), ( 4, 18),
    (28,  6), (28,  2),
    (16, 10), (10, 10), ( 4,  4),
    # opposite corner
    ( 3,  2), ( 4,  2),
    # right edge / bottom edge probes
    (31, 18), (31, 21), (28, 21), (26, 21),
]


def main():
    ztag = f"lits_zero_{SX}_{SY}"
    if not os.path.exists(f"/home/test/EP4CE6/results/rbf/{ztag}.rbf"):
        print(f"compiling {ztag}...", flush=True)
        rbf, t, err = compile_route_baseline_abcd(ztag, SX, SY, 0)
        print(f"  {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")
        if not rbf:
            print("baseline failed — aborting")
            return

    ok = fail = 0
    for dx, dy in DSTS:
        tag = f"lits_pair_X{SX}Y{SY}_to_X{dx}Y{dy}N0_datab"
        path = f"/home/test/EP4CE6/results/rbf/{tag}.rbf"
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
