# SPDX-License-Identifier: GPL-3.0-or-later
"""Sweep codec emission probe across all 26 SDP sites.

For each site, applies M9K_INIT ∩ target, M9K_MODE D3, M9K_COLUMN_INFRA,
and IOB_PIN_BANK_INFRA (HEADER ∪ BLOCK_BAND_POST) to nv_zero_global,
CRC-patches, diffs vs Quartus v0 gold, and reports the remaining gap
broken down by region.

Sanity check: gap structure should be stable across sites.
Outlier sites flag a mining problem.
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

PRE, FRAME, DPF = 32, 210, 208
REGIONS = [
    (0, 24, "header"), (25, 1006, "lab_low"), (1007, 1013, "clk_net"),
    (1014, 1691, "lab_high"), (1692, 1738, "block_band"),
    (1739, 1751, "block_band_post"),
]


def region_of(frame: int) -> str:
    for lo, hi, name in REGIONS:
        if lo <= frame <= hi:
            return name
    return "?"


def diff_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    cells = set()
    for off in range(PRE, len(a)):
        if (off - PRE) % FRAME >= DPF:
            continue
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                cells.add((off, bp))
    return cells


def main():
    from m9k_init_basis import M9K_INIT_ANCHORS, init_cell
    from bitstream import patch_rbf_crc

    nv = (ROOT / "results/rbf/nv_zero_global.rbf").read_bytes()
    d3_data = json.loads((ROOT / "results/m9k_mode_d3.json").read_text())
    infra_data = json.loads((ROOT / "results/m9k_column_infra.json").read_text())
    iob_data = json.loads((ROOT / "results/iob_pin_bank_infra.json").read_text())

    base = ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp"
    sites = sorted(p.name for p in base.iterdir()
                   if p.is_dir() and p.name.startswith("X")
                   and "_Y" in p.name and "_N" in p.name)

    print(f"{'site':<14} {'target':>6} {'union':>6} {'gap':>6}  "
          f"{'hdr':>4} {'lab_lo':>6} {'lab_hi':>6} {'bb':>4} {'bb_p':>4}")
    print("-" * 76)
    rows = []
    for site in sites:
        site_dir = base / site
        v0 = (site_dir / "m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()
        target = diff_cells(v0, nv)

        # M9K_INIT footprint ∩ target
        anchor_info = M9K_INIT_ANCHORS.get((site, 4, 2048))
        init_cells = set()
        if anchor_info:
            anchor = anchor_info[0]
            init_bp = anchor_info[1] if len(anchor_info) > 1 else 6
            footprint = set()
            for w in range(2048):
                for b in range(4):
                    try:
                        footprint.add(init_cell(anchor, w, b, init_bp))
                    except Exception:
                        pass
            init_cells = target & footprint

        # M9K_MODE D3 (re-mined vs nv_zero_global)
        mode_cells = set(tuple(c) for c in
                         d3_data.get(site, {}).get("mode_d3_cells", []))

        # M9K_COLUMN_INFRA
        infra_cells = set(tuple(c) for c in
                          infra_data.get(site, {}).get("infra_cells", []))

        # IOB_PIN_BANK_INFRA (per-site, HEADER ∪ BLOCK_BAND_POST —
        # absorbs the legacy M9K_BLOCK_TAIL bucket)
        iob_cells = set(tuple(c) for c in
                        iob_data.get("per_site", {}).get(site, []))

        union = init_cells | mode_cells | infra_cells | iob_cells
        rebuilt = bytearray(nv)
        for off, bp in union:
            rebuilt[off] ^= 1 << bp
        final = patch_rbf_crc(bytes(rebuilt))

        remaining = diff_cells(final, v0)
        by_region = Counter()
        for off, bp in remaining:
            by_region[region_of((off - PRE) // FRAME)] += 1

        row = {
            "site": site,
            "target": len(target),
            "union": len(union),
            "gap": len(remaining),
            "header": by_region["header"],
            "lab_low": by_region["lab_low"],
            "lab_high": by_region["lab_high"],
            "block_band": by_region["block_band"],
            "block_band_post": by_region["block_band_post"],
        }
        rows.append(row)
        print(f"{site:<14} {row['target']:>6} {row['union']:>6} {row['gap']:>6}  "
              f"{row['header']:>4} {row['lab_low']:>6} {row['lab_high']:>6} "
              f"{row['block_band']:>4} {row['block_band_post']:>4}")

    # Aggregate
    print("-" * 76)
    print(f"\nGap statistics across {len(rows)} sites:")
    for key in ("gap", "header", "lab_low", "lab_high", "block_band",
                "block_band_post"):
        vals = [r[key] for r in rows]
        print(f"  {key:18} min={min(vals):4} max={max(vals):4} "
              f"mean={sum(vals)/len(vals):6.1f} stdev_pp={max(vals)-min(vals):4}")

    # Outlier detection
    gaps = [r["gap"] for r in rows]
    mean = sum(gaps) / len(gaps)
    print(f"\nOutliers (|gap - mean| > 200, mean={mean:.0f}):")
    for r in rows:
        if abs(r["gap"] - mean) > 200:
            print(f"  {r['site']:<14} gap={r['gap']}  Δ={r['gap'] - mean:+.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
