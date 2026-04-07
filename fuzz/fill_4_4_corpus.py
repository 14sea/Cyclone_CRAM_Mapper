"""γ step 1 — fill the (4,4) corner corpus.

(4,4) is the double-edge case: one column from left IO (X3 is leftmost
LAB), two rows from top IO (Y2 is topmost LAB). Hypothesis: fingerprint
will exceed 20 bits and contain edge_even_b0 LI signatures absent from
both interior islands.

Note: corner LABs are notoriously fitter-hostile. Expect ~30-40% of
targets to fail with 'illegal location assignment'. Pick wide spread
to maximize survivors.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input, compile_route_baseline_abcd

DSTS = [
    # short corridor
    ( 6,  4), ( 8,  4), (10,  4), (13,  4),
    ( 4,  6), ( 4,  8), ( 4, 10), ( 4, 13),
    # diagonals into the chip
    ( 6,  6), ( 8,  8), (10, 10), (13, 13),
    # far reaches (R24/C16 territory)
    (16,  4), (28,  4), ( 4, 16), ( 4, 21),
    # opposite corner
    (28, 21), (31, 21),
]

def main():
    ztag = "lits_zero_4_4"
    if not os.path.exists(f"/home/test/EP4CE6/results/rbf/{ztag}.rbf"):
        print(f"compiling {ztag}...", flush=True)
        rbf, t, err = compile_route_baseline_abcd(ztag, 4, 4, 0)
        print(f"  {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")
        if not rbf:
            print("baseline failed — aborting")
            return

    ok = fail = 0
    for dx, dy in DSTS:
        tag = f"lits_pair_X4Y4_to_X{dx}Y{dy}N0_datab"
        path = f"/home/test/EP4CE6/results/rbf/{tag}.rbf"
        if os.path.exists(path):
            print(f"  exists: {tag}")
            ok += 1
            continue
        print(f"compiling {tag}...", flush=True)
        rbf, t, err = compile_route_pair_single_input(
            tag, 4, 4, 0, dx, dy, 0, connect_port="datab")
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
