#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""σ⁻¹ coverage diagnostic scan.

For every CE6 whitelist LE position (x, y, n), compute (foff, fb8) and report:
  - fb8 distribution across the 6272 LEs
  - Exact match rate vs nearest-neighbor fallback vs identity fallback
  - Which positions use identity fallback (fb8 ∈ missing groups)
  - Sample Symptom A/B diagnosis where Quartus gold is available
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

from config import COLUMN_BASE, LAB_X, LAB_Y, SLOT_BASE, cram_n_delta, cram_ctrl_bit
from bitstream import (
    LutCodec,
    _SIGMA_INV_CACHE,
    _SIGMA_INV_BY_FB8,
    _SIGMA_INV_SORTED,
    _sigma_inv_lookup,
)


def compute_foff_fb8(x, y, n):
    """Replicate from_cram_model's (foff, fb8) calculation."""
    slot = (y - 2) % 3
    group = (y - 2) // 3
    nd = cram_n_delta(n)
    wrapped = slot == 1 and (24 + group * 3 + nd < 0)
    if wrapped:
        addr_adj = 207
    else:
        addr_adj = 0
    offset = SLOT_BASE[slot] + group * 3 + (1 if slot == 0 and group > 0 else 0)
    val = COLUMN_BASE[x] - 168 + offset + nd + addr_adj
    foff = val % 210
    fb8 = (val // 210) % 8
    return foff, fb8


def classify_lookup(foff, fb8):
    """Return 'exact', 'nearest', or 'identity'."""
    if (foff, fb8) in _SIGMA_INV_CACHE:
        return "exact"
    if fb8 in _SIGMA_INV_SORTED:
        return "nearest"
    return "identity"


def main():
    print("=" * 70)
    print("σ⁻¹ COVERAGE DIAGNOSTIC SCAN")
    print("=" * 70)

    fb8_counter = Counter()
    class_counter = Counter()
    fb8_class = defaultdict(Counter)
    identity_positions = []
    nearest_positions = defaultdict(list)

    all_n = list(range(0, 32, 2))

    for x in LAB_X:
        for y in LAB_Y:
            for n in all_n:
                foff, fb8 = compute_foff_fb8(x, y, n)
                cls = classify_lookup(foff, fb8)
                fb8_counter[fb8] += 1
                class_counter[cls] += 1
                fb8_class[fb8][cls] += 1
                if cls == "identity":
                    identity_positions.append((x, y, n, foff, fb8))
                elif cls == "nearest":
                    entries = _SIGMA_INV_SORTED[fb8]
                    best_dist = min(abs(ef - foff) for ef, _ in entries)
                    nearest_positions[best_dist].append((x, y, n, foff, fb8))

    total = sum(fb8_counter.values())
    print(f"\nTotal CE6 LE positions scanned: {total}")
    print(f"  (LAB_X={len(LAB_X)} × LAB_Y={len(LAB_Y)} × N=16 = {len(LAB_X)*len(LAB_Y)*16})")

    print(f"\n--- fb8 Distribution ---")
    for fb8 in sorted(fb8_counter.keys()):
        n = fb8_counter[fb8]
        pct = 100.0 * n / total
        has_table = "✓" if fb8 in _SIGMA_INV_BY_FB8 else "✗ IDENTITY"
        print(f"  fb8={fb8}: {n:5d} positions ({pct:5.1f}%)  σ⁻¹ table: {has_table}")

    print(f"\n--- Lookup Classification ---")
    for cls in ["exact", "nearest", "identity"]:
        n = class_counter[cls]
        pct = 100.0 * n / total
        print(f"  {cls:10s}: {n:5d} positions ({pct:5.1f}%)")

    print(f"\n--- Per-fb8 Breakdown ---")
    for fb8 in sorted(fb8_class.keys()):
        counts = fb8_class[fb8]
        parts = []
        for cls in ["exact", "nearest", "identity"]:
            if counts[cls] > 0:
                parts.append(f"{cls}={counts[cls]}")
        entries_in_table = len(_SIGMA_INV_BY_FB8.get(fb8, []))
        print(f"  fb8={fb8}: {', '.join(parts)}  (table has {entries_in_table} foff entries)")

    print(f"\n--- Nearest-Neighbor Distance Distribution ---")
    for dist in sorted(nearest_positions.keys())[:15]:
        n = len(nearest_positions[dist])
        print(f"  dist={dist:3d}: {n:5d} positions")

    if identity_positions:
        print(f"\n--- Identity Fallback Positions ({len(identity_positions)} total) ---")
        fb8_groups = defaultdict(list)
        for x, y, n, foff, fb8 in identity_positions:
            fb8_groups[fb8].append((x, y, n, foff))
        for fb8 in sorted(fb8_groups.keys()):
            positions = fb8_groups[fb8]
            foffs = sorted(set(f for _, _, _, f in positions))
            print(f"  fb8={fb8}: {len(positions)} positions, {len(foffs)} distinct foffs")
            print(f"    foffs: {foffs[:20]}{'...' if len(foffs) > 20 else ''}")
            print(f"    sample: {positions[:5]}")

    # --- Permutation diversity per fb8 ---
    print(f"\n--- σ⁻¹ Permutation Diversity ---")
    for fb8 in sorted(_SIGMA_INV_BY_FB8.keys()):
        perms = set()
        for entry in _SIGMA_INV_BY_FB8[fb8]:
            perms.add(entry[1:])
        print(f"  fb8={fb8}: {len(perms)} distinct permutations: {sorted(perms)}")

    # --- Check which σ⁻¹ permutations would apply at identity positions ---
    print(f"\n--- What σ⁻¹ SHOULD be at identity-fallback positions? ---")
    print("  (Requires Quartus gold to diagnose; listing candidate fb8 groups to mine)")
    missing_fb8 = sorted(set(fb8 for _, _, _, _, fb8 in identity_positions))
    for fb8 in missing_fb8:
        covered_fb8s = sorted(_SIGMA_INV_BY_FB8.keys())
        print(f"  fb8={fb8}: NOT COVERED — nearest covered fb8s: {covered_fb8s}")

    # --- Save diagnostic report ---
    report = {
        "total_positions": total,
        "fb8_distribution": {str(k): v for k, v in sorted(fb8_counter.items())},
        "lookup_classification": dict(class_counter),
        "identity_fallback_count": len(identity_positions),
        "identity_fb8_groups": missing_fb8,
        "covered_fb8_groups": sorted(_SIGMA_INV_BY_FB8.keys()),
        "identity_positions_sample": [
            {"x": x, "y": y, "n": n, "foff": foff, "fb8": fb8}
            for x, y, n, foff, fb8 in identity_positions[:50]
        ],
    }
    out = REPO / "tmp" / "sigma_inv_diagnostic.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\nDiagnostic saved to {out}")


if __name__ == "__main__":
    main()
