# SPDX-License-Identifier: GPL-3.0-or-later
"""Inspect overlap between M9K_INIT footprint, M9K_MODE bucket, and
M9K_COLUMN_INFRA bucket at one (X,Y) site, plus their relation to the
target (v0 ⊕ nv_zero_global).
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
PRE, FRAME, DPF = 32, 210, 208


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


def main():
    site = "X15_Y16_N0"
    w, d = 4, 2048
    nv = (ROOT / "results/rbf/nv_zero_global.rbf").read_bytes()
    v0 = (ROOT / f"tmp/m9k_mode_quartus_gold/4x2048/sdp/{site}/m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()
    target = diff_cells(v0, nv)

    from m9k_init_basis import M9K_INIT_ANCHORS, init_cell
    anchor_info = M9K_INIT_ANCHORS[(site, w, d)]
    anchor = anchor_info[0]
    init_bp = anchor_info[1] if len(anchor_info) > 1 else 6
    init_footprint = set()
    for word_idx in range(d):
        for bit_idx in range(w):
            try:
                off, bp = init_cell(anchor, word_idx, bit_idx, init_bp)
                init_footprint.add((off, bp))
            except Exception:
                pass

    mode_bits = json.loads((ROOT / "results/m9k_mode_bits.json").read_text())
    mode_set = set(tuple(c) for c in mode_bits[f"{site}_4x2048"]["cells_by_template"]["quartus_gold_sdp"])

    infra_path = ROOT / "results/m9k_column_infra.json"
    if not infra_path.exists():
        infra_path = ROOT / "tmp/m9k_column_infra_mine.json"
    infra = json.loads(infra_path.read_text())
    infra_set = set(tuple(c) for c in infra[site]["infra_cells"])

    init_in_target = target & init_footprint

    print(f"Target cells: {len(target)}")
    print(f"M9K_INIT footprint: {len(init_footprint)} (bp={init_bp})")
    print(f"  ∩ target: {len(init_in_target)}")
    print(f"  ∩ infra : {len(init_footprint & infra_set)}  ← double-XOR if non-zero")
    print(f"  ∩ mode  : {len(init_footprint & mode_set)}")
    print(f"M9K_MODE quartus_gold_sdp: {len(mode_set)}")
    print(f"  ∩ target: {len(mode_set & target)}")
    print(f"  ∩ infra : {len(mode_set & infra_set)}")
    print(f"M9K_COLUMN_INFRA: {len(infra_set)}")
    print(f"  ∩ target: {len(infra_set & target)}")

    # The applied union (XOR-applied) cells: cells in odd number of buckets
    init_used = init_in_target  # only those that are in target
    applied_xor = set()
    for c in init_used | mode_set | infra_set:
        flips = (c in init_used) + (c in mode_set) + (c in infra_set)
        if flips % 2 == 1:
            applied_xor.add(c)
    expected = target
    missed = expected - applied_xor  # cells we should flip but don't
    spurious = applied_xor - expected  # cells we flip but shouldn't
    print(f"\nApplied XOR (odd-count): {len(applied_xor)}")
    print(f"Missed (target not applied): {len(missed)}")
    print(f"Spurious (applied but not target): {len(spurious)}")

    # Where are spurious?
    REGIONS = [
        (0, 24, "header"), (25, 1006, "lab_low"), (1007, 1013, "clk_net"),
        (1014, 1691, "lab_high"), (1692, 1738, "block_band"),
        (1739, 1751, "block_band_post"),
    ]
    def region_of(frame):
        for lo, hi, name in REGIONS:
            if lo <= frame <= hi:
                return name
        return "?"

    print("\nSpurious by (region, bp):")
    sc = Counter((region_of((off-PRE)//FRAME), bp) for off, bp in spurious)
    for (r, bp), n in sorted(sc.items()):
        print(f"  {r:18} bp={bp}: {n}")

    print("\nMissed by (region, bp):")
    mc = Counter((region_of((off-PRE)//FRAME), bp) for off, bp in missed)
    for (r, bp), n in sorted(mc.items()):
        print(f"  {r:18} bp={bp}: {n}")


if __name__ == "__main__":
    main()
