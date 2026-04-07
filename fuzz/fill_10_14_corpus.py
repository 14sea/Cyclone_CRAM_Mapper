"""β step 1 — fill the (10,14) Manhattan corridor."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input, compile_route_baseline_abcd

DSTS = [
    (10, 16), (10, 21), (10, 11), (10,  8), (10,  4),
    (11, 14), (12, 14), (13, 14), ( 7, 14), ( 4, 14),
    (13, 16), ( 7, 12), (13, 11), (16, 14),
]

def main():
    ztag = "lits_zero_10_14"
    if not os.path.exists(f"/home/test/EP4CE6/results/rbf/{ztag}.rbf"):
        print(f"compiling {ztag}...", flush=True)
        rbf, t, err = compile_route_baseline_abcd(ztag, 10, 14, 0)
        print(f"  {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")

    for dx, dy in DSTS:
        tag = f"lits_pair_X10Y14_to_X{dx}Y{dy}N0_datab"
        path = f"/home/test/EP4CE6/results/rbf/{tag}.rbf"
        if os.path.exists(path):
            print(f"  exists: {tag}")
            continue
        print(f"compiling {tag}...", flush=True)
        rbf, t, err = compile_route_pair_single_input(
            tag, 10, 14, 0, dx, dy, 0, connect_port="datab")
        print(f"  {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")

if __name__ == "__main__":
    main()
