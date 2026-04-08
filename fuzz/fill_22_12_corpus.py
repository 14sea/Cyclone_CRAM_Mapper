# SPDX-License-Identifier: GPL-3.0-or-later
"""δ step 1 — fill the (22,12) right-side interior corpus.

Fourth green-zone candidate. (22,12) is deep on the right half of the chip,
opposite the existing α (10,10) island. Hypothesis: fingerprint should look
similar to α (interior, no edges) — if so, that supports the conjecture that
all interior LABs share a small per-source fingerprint and we only need a
sparse set of islands to cover the chip. If it diverges, we learn the
fingerprint also depends on something other than chip-edge adjacency.
"""
import sys, os
import os as _os
REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input, compile_route_baseline_abcd

SX, SY = 22, 12

DSTS = [
    # short hops in all 4 directions
    (24, 12), (26, 12), (28, 12),
    (19, 12), (17, 12), (16, 12),
    (22, 14), (22, 16), (22, 18),
    (22, 10), (22,  8), (22,  6),
    # diagonals
    (24, 14), (26, 16), (28, 18),
    (19, 14), (17, 16), (16, 18),
    (24, 10), (26,  8), (28,  6),
    (19, 10), (17,  8), (16,  6),
    # far reaches (R24/C16 territory)
    (10, 12), ( 4, 12), (31, 12),
    (22,  2), (22, 21),
    (10,  2), (31, 21),
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
