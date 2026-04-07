"""Targeted compiles to fill sparse cells in the R24 (Y_block, prev_x) matrix.

Forces Quartus to route long horizontal paths through the under-sampled
(Y_block, prev_x) pairs:

  - Block F (Y=16/17/18) × prev_x=13   ← flips to SEC at low confidence
  - Block D (Y=10/11/12) × prev_x=8    ← Y=10 ties at 4/4 samples
  - Block C (Y=7/8/9)    × prev_x=4    ← totally absent
  - Block A (Y=2/3)      × prev_x=4    ← only 0/2 samples in earlier scan

Each compile is a single-input lut2 design (lut1 → datab), filename
prefix 'lits_r24fill_' so the cardinality miner's existing zero-baseline
heuristic (lits_zero_10_10.rbf) picks them up automatically.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time

from runner import compile_route_pair_single_input

# Each entry: (label, src, dst). Long horizontal hops force R24 usage.
TARGETS = [
    # Block F prev_x=13: wx ∈ {14,15,16} → src/dst spanning across X=16
    ("F13a", (3,  16), (24, 16)),
    ("F13b", (4,  17), (28, 17)),
    ("F13c", (6,  18), (29, 18)),
    # Block D prev_x=8: wx ∈ {9,10} → src/dst spanning across X=10
    ("D08a", (3,  10), (28, 12)),
    ("D08b", (4,  11), (31, 11)),
    ("D08c", (6,  12), (29, 10)),
    # Block C prev_x=4: wx ∈ {5,6} → src/dst spanning across X=6
    ("C04a", (3,   7), (28,  9)),
    ("C04b", (4,   8), (31,  7)),
    # Block A prev_x=4: wx ∈ {5,6}
    ("A04a", (3,   2), (28,  3)),
    ("A04b", (4,   3), (29,  2)),
]


def main():
    print(f"compiling {len(TARGETS)} targeted R24-fill designs\n")
    t_start = time.time()
    n_ok = n_fail = 0
    for label, src, dst in TARGETS:
        tag = f"lits_r24fill_{label}_{src[0]}_{src[1]}_to_{dst[0]}_{dst[1]}"
        rbf, t, err = compile_route_pair_single_input(
            tag, src[0], src[1], 0, dst[0], dst[1], 0,
            connect_port="datab", mask1=0x8888, mask2=0xAA,
        )
        if rbf:
            print(f"  ✓ {label} {src}→{dst}  ({t:.1f}s)")
            n_ok += 1
        else:
            print(f"  ✗ {label} {src}→{dst}  ({t:.1f}s) {err[:80]}")
            n_fail += 1

    print(f"\ndone in {time.time()-t_start:.1f}s  ok={n_ok} fail={n_fail}")
    print("now re-run: python3 r24_cardinality_mine.py")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
