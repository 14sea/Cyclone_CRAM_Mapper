# SPDX-License-Identifier: GPL-3.0-or-later
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
    designs = [
        ("lits_l3_base", 0x8888, 0xAA),   # working logic
        ("lits_l3_zero", 0x0000, 0x00),   # same skeleton, no signal route
    ]
    rc = 0
    for tag, m1, m2 in designs:
        rbf, t, err = compile_route_pair_single_input(
            tag, 10, 10, 0, 12, 10, 0,
            connect_port="datab", mask1=m1, mask2=m2,
        )
        if rbf is None:
            print(f"FAIL {tag} ({t:.1f}s): {err}")
            rc = 1
        else:
            print(f"OK   {tag} ({t:.1f}s) -> {rbf}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
