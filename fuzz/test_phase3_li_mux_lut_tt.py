# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression for Phase 3 LI MUX restoration vs std_lut LUT TT.

CLAUDE.md Known Pitfall #13 (memory note phase3_li_mux_lut_tt_collision_2026_05_04.md):
fasm2rbf's Phase 3 LI MUX snapshot-restore loop walks 18 cells per LAB
at a (group, slot)-derived bp.  Without the std_lut TT exclusion landed
2026-05-05, that bp coincides with the LE LUT TT bp at the same byte
offsets for roughly half of CE6 LAB_Y values (Y∈{2,4,5,7,10,14,17})
and clobbers Phase 1+2's LUT TT writes.

Symptom: LutCodec.read_tt(rbf, nv) returns the post-apply_routing
snapshot encoding (often pass-datac) instead of the FASM directive
mask.  This regression decodes a small std_lut + ROUTE design at every
CE6 LAB_Y and asserts the directive round-trips through the codec.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from bitstream import LutCodec  # noqa: E402
from fasm2rbf import bitgen  # noqa: E402

# Y values where Phase 3 bp coincides with N=0 LUT TT bp (collision).
COLLIDING_Y = (2, 4, 5, 7, 10, 14, 17)
# Y values where the bps differ — sanity-check that the fix doesn't
# regress already-working placements.
SAFE_Y = (3, 6, 18, 21)


def decode(y: int, mask: int = 0xAAAA) -> int:
    nv_path = os.path.join(ROOT, "results", "rbf", "nv_zero_global.rbf")
    nv = open(nv_path, "rb").read()
    fasm = (
        "NV_BASELINE_PACK\n"
        f"X10Y{y}N0.LUT = 0x{mask:04x}\n"
        f"ROUTE X10Y10N0 -> X10Y{y}N0.dataa\n"
    )
    rbf = bitgen(fasm, nv)
    return LutCodec.from_cram_model(10, y, 0).read_tt(rbf, nv)


def main():
    failures = []
    for y in COLLIDING_Y + SAFE_Y:
        got = decode(y)
        tag = "collision" if y in COLLIDING_Y else "safe"
        status = "OK" if got == 0xAAAA else f"FAIL (got 0x{got:04x})"
        print(f"  Y={y:2d}  ({tag:9s})  {status}")
        if got != 0xAAAA:
            failures.append((y, got))
    if failures:
        print(f"\nFAIL: {len(failures)} of {len(COLLIDING_Y) + len(SAFE_Y)} Y values")
        for y, got in failures:
            print(f"  Y={y}: decoded 0x{got:04x}, expected 0xaaaa")
        sys.exit(1)
    print(f"\nPASS: {len(COLLIDING_Y) + len(SAFE_Y)} Y values round-trip 0xaaaa")


if __name__ == "__main__":
    main()
