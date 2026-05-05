# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3 LI MUX std_lut TT collision regression.

CLAUDE.md Known Pitfall #13:
fasm2rbf's Phase 3 LI MUX snapshot-restore loop walks 18 cells per
(lx, ly) at a (group, slot)-derived bp.  At colliding Y values
(Y∈{2,4,5,7,10,14,17}) that bp coincides with the LE LUT TT bp at
the same byte offsets — pre-fix, Phase 3 unconditionally restored
those bytes from the apply_routing snapshot, corrupting Phase 1+2's
LUT TT writes.

Mining via `scripts/sigma_inv_real_tt_mining/mine_real_tt.py`
(2026-05-05) proved σ⁻¹'s 16 claimed TT cells per LE ARE all real
TT cells (correctly_identified=16, misclassified=0 across 8 mined
LEs at colliding + safe Y values).  The fix in `fuzz/fasm2rbf.py`
Phase 3 skips σ⁻¹'s `tt_cells_cache` entries → Phase 1+2 owns LUT
TT, Phase 3 restores only the 2 true LI MUX cells per LAB at the
overlapping bp.

This regression decodes a small std_lut + ROUTE design at every
CE6 LAB_Y and asserts the directive round-trips through the codec.
Pre-fix all 7 colliding Y values failed (decoded as snapshot value);
post-fix all 11 (7 colliding + 4 safe) round-trip correctly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from bitstream import LutCodec  # noqa: E402
from fasm2rbf import bitgen  # noqa: E402

# Y values where Phase 3 bp == N=0 LUT TT bp (collision).
COLLIDING_Y = (2, 4, 5, 7, 10, 14, 17)
# Y values where the bps differ — sanity-check that the fix doesn't
# regress already-working safe placements.
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
