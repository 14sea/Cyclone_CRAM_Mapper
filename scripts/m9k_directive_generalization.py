# SPDX-License-Identifier: GPL-3.0-or-later
"""Test if directive buckets generalize across designs at the same site.

Mine the 4 buckets from BOTH the passive v0 (X15_Y16_N0 SDP 4x2048,
no LED logic) AND the blink v0 (X15_Y16_N0 m9k_sdp_blink_4x2048,
HW-validated to blink LED0).  Compare bucket overlap.

If buckets are M9K-instance-only and design-independent, the
overlap should be near 100%.  If lower, the directives include
design-specific cells (clk-net adjacency, etc.) that won't
generalize."""
from __future__ import annotations
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
    site = "X15_Y16_N0"
    y = 16
    bp_y = (6 - (y - 2) // 3) if (y - 2) % 3 == 2 else (7 - (y - 2) // 3)

    passive_v0 = (ROOT / f"tmp/m9k_mode_quartus_gold/4x2048/sdp/{site}/m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()
    blink_v0 = (ROOT / f"tmp/m9k_sdp_blink_4x2048_{site}/m9k_sdp_blink_4x2048_{site}.rbf").read_bytes()

    p_diff = diff_cells(passive_v0, nv)
    b_diff = diff_cells(blink_v0, nv)
    print(f"Total v0⊕nv: passive={len(p_diff)}  blink={len(b_diff)}")

    print(f"\n{'directive':<22}  passive   blink     ∩       jaccard")
    print("-" * 65)
    for name, region, bp_set in [
        ("HEADER (IOB_PIN)", HEADER, None),
        ("BLOCK_BAND (D3)", BLOCK_BAND, None),
        ("BLOCK_BAND_POST", BLOCK_BAND_POST, None),
        ("COLUMN_INFRA bp=2", LAB_LOW, {bp_y}),
    ]:
        p = filter_region(p_diff, region, bp_set)
        b = filter_region(b_diff, region, bp_set)
        inter = p & b
        union = p | b
        jacc = len(inter) / len(union) if union else 0.0
        print(f"{name:<22}  {len(p):>5}     {len(b):>5}     {len(inter):>5}    {jacc:.3f}")

    # Total bucket union vs target (gap if codec applies passive bucket onto nv to recreate blink)
    p_buckets = set()
    for region, bp_set in [(HEADER, None), (BLOCK_BAND, None),
                           (BLOCK_BAND_POST, None), (LAB_LOW, {bp_y})]:
        p_buckets |= filter_region(p_diff, region, bp_set)
    print(f"\nPassive-mined union of 4 directives: {len(p_buckets)}")
    print(f"Blink target: {len(b_diff)}")
    print(f"Passive bucket ∩ blink target: {len(p_buckets & b_diff)}")
    print(f"Passive bucket ∖ blink (would apply spurious cells): {len(p_buckets - b_diff)}")
    print(f"Blink ∖ passive bucket (cells passive misses): {len(b_diff - p_buckets)}")


if __name__ == "__main__":
    main()
