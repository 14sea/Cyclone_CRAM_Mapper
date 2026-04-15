# SPDX-License-Identifier: GPL-3.0-or-later
"""Build simple_led (KEY=E16 → LUT@X10Y4N0 → DFF → LED=G15) from FASM
and diff against the Quartus gold RBF.

End-to-end baseline-integration check: exercises IOB_BASELINE_NV +
IOB_IN + IOB_OUT + IOB_ROUTE + LUT + GCLK_PIN + LAB_CLK_SEL +
LAB_CLK_SEL_LE on top of nv_zero_global.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f


PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_START = PRE + FIRST * FRAME
CRAM_END = PRE + (LAST + 1) * FRAME


FASM = """\
IOB_BASELINE_NV
IOB_IN  PIN_E16
IOB_OUT PIN_G15
IOB_CLK_INPUT PIN_E1
IOB_ROUTE PIN_E16 -> X10Y4N0.dataa
GCLK_PIN PIN_E1
LAB_CLK_SEL X10Y4
LAB_CLK_SEL_LE X10Y4N0
"""
# NOTE: no explicit LUT directive — the IOB_ROUTE pair-delta was mined
# from iob_pair_E16_10_4_0_dataa.rbf (Quartus-canonicalized single-input
# LUT with mask=0xAAAA at dataa) vs the zero variant.  Its 196 cells
# already include the LUT TT state that makes lut_prim pass dataa
# through to combout.  Adding X10Y4N0.LUT=0xAAAA on top would XOR with
# the baked-in LUT state and produce a different truth table.


def main() -> int:
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    gold_path = (HERE / "work" / "simple_led_E16_to_G15"
                 / "output_files" / "simple_led_E16_to_G15.rbf")
    gold = gold_path.read_bytes()
    assert len(nv) == len(gold)

    # Clear all caches for a clean run
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None

    out = f.bitgen(FASM, nv, patch_crc=True)

    diffs = [i for i in range(len(out)) if out[i] != gold[i]]
    hdr = [i for i in diffs if i < CRAM_START]
    cram = [i for i in diffs if CRAM_START <= i < CRAM_END]
    trl = [i for i in diffs if i >= CRAM_END]
    print(f"FASM vs Quartus gold: total {len(diffs)} byte diffs")
    print(f"  hdr   : {len(hdr):4d}")
    print(f"  CRAM  : {len(cram):4d}")
    print(f"  trl   : {len(trl):4d}")

    if hdr:
        print(f"  hdr offsets[:30]: {hdr[:30]}")
    if cram:
        fc = Counter((i - PRE) // FRAME for i in cram)
        print(f"  CRAM frame histogram (top 12): {fc.most_common(12)}")
        print(f"  CRAM frames touched: {len(fc)} range "
              f"{min(fc)}..{max(fc)}")

    # Also bucket: how many of the diffs are in CRC bytes (last 2 of each
    # frame)?  CRC is deterministic-reconstructed, so a CRC-only diff
    # would be a CRC bug, not a codec bug.
    crc_diffs = 0
    data_cram_diffs = 0
    for i in cram:
        rel = i - PRE
        frame = rel // FRAME
        within = rel % FRAME
        if within >= 208:  # bytes 208,209 = CRC LE bytes
            crc_diffs += 1
        else:
            data_cram_diffs += 1
    print(f"  CRAM breakdown: data={data_cram_diffs}  CRC={crc_diffs}")

    # Save the FASM output for inspection
    out_path = HERE / "work" / "simple_led_E16_to_G15" / "fasm.rbf"
    out_path.write_bytes(out)
    print(f"\n[wrote] {out_path}")

    if not diffs:
        print("\n[PERFECT] FASM output is byte-identical to Quartus gold.")
        return 0
    return 0  # informational script, don't fail


if __name__ == "__main__":
    sys.exit(main())
