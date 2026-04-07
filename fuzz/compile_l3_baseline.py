"""L3 step 1 — compile a Quartus 'golden' baseline with proper LUT masks.

Design: lut1@(10,10,0) mask=0x8888 (A AND B) feeds lut2@(12,10,0) mask=0xAA
(pass datab) → Q. Produces results/rbf/lits_l3_base.rbf containing both
working logic AND Quartus's own routing — used as the donor for the
routing-transplant experiment in synth_route_l3.py.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runner import compile_route_pair_single_input


def main():
    tag = "lits_l3_base"
    rbf, t, err = compile_route_pair_single_input(
        tag, 10, 10, 0, 12, 10, 0,
        connect_port="datab",
        mask1=0x8888,   # A AND B at lut1
        mask2=0xAA,     # pass datab at lut2
    )
    if rbf is None:
        print(f"FAIL ({t:.1f}s): {err}")
        return 1
    print(f"OK  ({t:.1f}s) -> {rbf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
