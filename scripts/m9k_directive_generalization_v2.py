# SPDX-License-Identifier: GPL-3.0-or-later
"""Same-pinout cross-design generalization test.

Compare two SDP 4x2048 designs at X15_Y16_N0, BOTH using the AX301
4-pin pinout:
  * blink:        outdata_reg_b="UNREGISTERED", byteena_a=1, simple
                  counter, RDW="OLD_DATA", LED0=dout_r[0]
  * passive_ax301: outdata_reg_b="CLOCK0",   byteena_a=1, expanded
                  counter, RDW="DONT_CARE",  LED0=^dout_r

The pinout axis is now controlled.  Cross-design Jaccard at HEADER
should jump from 0.024 (the original 45-pin vs 4-pin) to ~0.9+.
BLOCK_BAND_POST is the genuine feature-usage axis: if 0 vs nonzero
again, feature usage is the cause; if both ~0 or both nonzero in
similar proportion, generalization is mostly viable per-pinout.
"""
from __future__ import annotations
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
PRE, FRAME, DPF = 32, 210, 208
LAB_LOW = (25, 1006)
HEADER = (0, 24)
BLOCK_BAND = (1692, 1738)
BLOCK_BAND_POST = (1739, 1751)


def diff_cells(a, b):
    cells = set()
    for off in range(PRE, len(a)):
        if (off - PRE) % FRAME >= DPF:
            continue
        x = a[off] ^ b[off]
        if x:
            for bp in range(8):
                if x & (1 << bp):
                    cells.add((off, bp))
    return cells


def filter_region(cells, region, bp_set=None):
    lo, hi = region
    return {(o, bp) for o, bp in cells
            if lo <= (o - PRE) // FRAME <= hi
            and (bp_set is None or bp in bp_set)}


def main():
    nv = (ROOT / "results/rbf/nv_zero_global.rbf").read_bytes()
    blink = (ROOT / "tmp/m9k_sdp_blink_4x2048_X15_Y16_N0/m9k_sdp_blink_4x2048_X15_Y16_N0.rbf").read_bytes()
    passive = (ROOT / "tmp/m9k_sdp_passive_ax301_X15_Y16_N0/m9k_sdp_passive_ax301_X15_Y16_N0.rbf").read_bytes()
    passive_45pin = (ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp/X15_Y16_N0/m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()

    b_diff = diff_cells(blink, nv)
    p_diff = diff_cells(passive, nv)
    p45_diff = diff_cells(passive_45pin, nv)

    print(f"Total v0⊕nv:")
    print(f"  blink (AX301):           {len(b_diff)}")
    print(f"  passive_ax301 (AX301):   {len(p_diff)}")
    print(f"  passive_45pin (passive): {len(p45_diff)}")

    bp_y = 2  # Y=16 → bp=2

    print(f"\n--- BLINK vs PASSIVE_AX301 (same pinout, different features) ---")
    print(f"{'directive':<22}  blink  passive  ∩    Jaccard")
    for name, region, bp_set in [
        ("HEADER", HEADER, None),
        ("BLOCK_BAND", BLOCK_BAND, None),
        ("BLOCK_BAND_POST", BLOCK_BAND_POST, None),
        ("COLUMN_INFRA bp=2", LAB_LOW, {bp_y}),
        ("LAB_LOW total", LAB_LOW, None),
    ]:
        b = filter_region(b_diff, region, bp_set)
        p = filter_region(p_diff, region, bp_set)
        inter = b & p
        union = b | p
        j = len(inter) / len(union) if union else 0.0
        print(f"{name:<22}  {len(b):>5}  {len(p):>5}  {len(inter):>5}    {j:.3f}")

    print(f"\n--- BLINK vs PASSIVE_45PIN (different pinout, different features) [reference] ---")
    print(f"{'directive':<22}  blink  passv45  ∩    Jaccard")
    for name, region, bp_set in [
        ("HEADER", HEADER, None),
        ("BLOCK_BAND", BLOCK_BAND, None),
        ("BLOCK_BAND_POST", BLOCK_BAND_POST, None),
        ("COLUMN_INFRA bp=2", LAB_LOW, {bp_y}),
    ]:
        b = filter_region(b_diff, region, bp_set)
        p45 = filter_region(p45_diff, region, bp_set)
        inter = b & p45
        union = b | p45
        j = len(inter) / len(union) if union else 0.0
        print(f"{name:<22}  {len(b):>5}  {len(p45):>5}  {len(inter):>5}    {j:.3f}")

    print(f"\n--- PASSIVE_AX301 vs PASSIVE_45PIN (different pinout, similar features) ---")
    print(f"{'directive':<22}  ax301  45pin    ∩    Jaccard")
    for name, region, bp_set in [
        ("HEADER", HEADER, None),
        ("BLOCK_BAND", BLOCK_BAND, None),
        ("BLOCK_BAND_POST", BLOCK_BAND_POST, None),
        ("COLUMN_INFRA bp=2", LAB_LOW, {bp_y}),
    ]:
        p = filter_region(p_diff, region, bp_set)
        p45 = filter_region(p45_diff, region, bp_set)
        inter = p & p45
        union = p | p45
        j = len(inter) / len(union) if union else 0.0
        print(f"{name:<22}  {len(p):>5}  {len(p45):>5}  {len(inter):>5}    {j:.3f}")


if __name__ == "__main__":
    main()
