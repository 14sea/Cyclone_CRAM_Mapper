# SPDX-License-Identifier: GPL-3.0-or-later
"""Companion-infra audit for M9K_MODE codec emission.

Per `m9k_mode_d2_falsified_2026_04_26.md`, D2 silicon-tests
revealed the codec emission gap is broader than the M9K mode bucket
itself. v0 (a Quartus SDP build at X15_Y16_N0) has 5222 cells
differing from `nv_zero_global`; only 35 are in block-band. The
other 5187 are companion infrastructure Quartus emits implicitly.

This script classifies every cell in (v0 ⊕ nv_zero_global) by:

  1. **Region** (header / lab_low / clk_net / lab_high / block_band /
     block_band_post).
  2. **Static directive coverage** — which existing static-bucket
     FASM directives (`NV_BASELINE_PACK`, `IOB_PAD_NV`,
     `M9K_MODE_*_quartus_gold_sdp`, `M9K_INIT_*`,
     `OUTROUTE_G15`, `IOB_ROUTE`) declare ownership of that cell.
  3. **Dynamic-emission plausibility** — for cells in LAB columns
     (X-coordinate derivable from CRAM byte → column), tag as
     LAB-resident (potential `LUT`/`ROUTE`/`SRC` coverage by
     np2fasm at emit time, design-dependent).

Output:
  * Per-region histogram of covered vs uncovered cells.
  * Top 20 frames with uncovered cells.
  * Summary of which directives provide the most coverage.
  * The "true gap" = cells not covered by any static directive AND
    not in a LAB column → probably need new directives.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

PRE, FRAME, DPF = 32, 210, 208
LAB_COL_STEP = 7350  # bytes per LAB column

# From fuzz/c16_mapper.py — END byte of each LAB column.  Each column
# spans roughly [END - 7350, END].
_LAB_CRAM_END = {
    3: 0x07ccf, 4: 0x09985, 6: 0x0d2f1, 7: 0x0efa7, 8: 0x10c5d,
    10: 0x145c9, 11: 0x1627f, 12: 0x17f35, 13: 0x19beb,
    16: 0x2c5b1, 17: 0x2e267, 18: 0x30265, 19: 0x31f1b,
    21: 0x35053, 22: 0x36d09, 23: 0x389bf, 24: 0x3a675,
    25: 0x3c32b, 26: 0x3dfe1, 28: 0x4ecf1, 29: 0x509a7, 31: 0x54313,
}
# M9K columns and Mult column — per CLAUDE.md NON_LAB_X = {15,27} (M9K), {20} (mult).
# Their CRAM bases interpolate the LAB grid; estimate from neighbours.
_NONLAB_X_BASE: dict[int, int] = {
    15: 0x1d8a3 - 7350,   # X=15 sits between X=13 (0x19beb) and X=16 (0x2c5b1)
    20: 0x33301 - 7350,   # X=20 between X=19 (0x31f1b) and X=21 (0x35053)
    27: 0x4717b - 7350,   # X=27 between X=26 (0x3dfe1) and X=28 (0x4ecf1)
}
LAB_X_LIST = sorted(_LAB_CRAM_END) + sorted(_NONLAB_X_BASE)

REGIONS = [
    (0, 24, "header"),
    (25, 1006, "lab_low"),
    (1007, 1013, "clk_net"),
    (1014, 1691, "lab_high"),
    (1692, 1738, "block_band"),
    (1739, 1751, "block_band_post"),
]


def region_of(frame: int) -> str:
    for lo, hi, name in REGIONS:
        if lo <= frame <= hi:
            return name
    return "?"


def all_v0_cells() -> set[tuple[int, int]]:
    zero = (ROOT / "results/rbf/nv_zero_global.rbf").read_bytes()
    v0 = (ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp/X15_Y16_N0/"
          "m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()
    cells: set[tuple[int, int]] = set()
    for off in range(PRE, len(zero)):
        if (off - PRE) % FRAME >= DPF:
            continue
        x = v0[off] ^ zero[off]
        for bp in range(8):
            if x & (1 << bp):
                cells.add((off, bp))
    return cells


def load_nv_baseline() -> set[tuple[int, int]]:
    nv = json.loads((ROOT / "results/nv_baseline_pack.json").read_text())
    out: set[tuple[int, int]] = set()
    def walk(o):
        if isinstance(o, list):
            if (len(o) == 2 and all(isinstance(x, int) for x in o)
                    and 0 <= o[1] <= 7):
                out.add((o[0], o[1]))
            else:
                for x in o:
                    walk(x)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
    walk(nv)
    return out


def load_iob_pad_nv() -> set[tuple[int, int]]:
    j = json.loads((ROOT / "results/output_route_nv_mining.json").read_text())
    cells = j.get("iob_pad_cells", [])
    return set(tuple(c) for c in cells)


def load_m9k_mode_sdp_x15_y16() -> set[tuple[int, int]]:
    j = json.loads((ROOT / "results/m9k_mode_bits.json").read_text())
    bucket = (j.get("X15_Y16_N0_4x2048", {})
              .get("cells_by_template", {})
              .get("quartus_gold_sdp", []))
    return set(tuple(c) for c in bucket)


def load_outroute_sigcache() -> set[tuple[int, int]]:
    j = json.loads((ROOT / "results/output_route_sigcache.json").read_text())
    out: set[tuple[int, int]] = set()
    def walk(o):
        if isinstance(o, list):
            if (len(o) == 2 and all(isinstance(x, int) for x in o)
                    and 0 <= o[1] <= 7):
                out.add((o[0], o[1]))
            else:
                for x in o:
                    walk(x)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
    walk(j)
    return out


def load_route_sigcache() -> set[tuple[int, int]]:
    """Union of every cell ANY ROUTE directive could write."""
    p = ROOT / "results/route_cells_full.json"
    if not p.exists():
        p = ROOT / "results/route_cells.json"
    j = json.loads(p.read_text())
    out: set[tuple[int, int]] = set()
    for v in j.values():
        if isinstance(v, list):
            for cell in v:
                if (isinstance(cell, list) and len(cell) == 2
                        and 0 <= cell[1] <= 7):
                    out.add((cell[0], cell[1]))
    return out


def load_clk_lab_sel_per_le() -> set[tuple[int, int]]:
    p = ROOT / "results/clk_lab_sel_per_le.json"
    if not p.exists():
        return set()
    j = json.loads(p.read_text())
    out: set[tuple[int, int]] = set()
    def walk(o):
        if isinstance(o, list):
            if (len(o) == 2 and all(isinstance(x, int) for x in o)
                    and 0 <= o[1] <= 7):
                out.add((o[0], o[1]))
            else:
                for x in o:
                    walk(x)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
    walk(j)
    return out


def m9k_init_anchor_cells_x15_y16(width=4, depth=2048) -> set[tuple[int, int]]:
    """For SDP (4, 2048) at X15_Y16_N0: enumerate all (word, bit) → (off, bp)."""
    try:
        from m9k_init_basis import M9K_INIT_ANCHORS, init_cell
    except Exception as e:
        print(f"  (m9k_init_basis import failed: {e})")
        return set()
    key = ("X15_Y16_N0", width, depth)
    info = M9K_INIT_ANCHORS.get(key)
    if info is None:
        return set()
    anchor = info[0] if isinstance(info, tuple) else info
    bp_default = info[1] if isinstance(info, tuple) and len(info) > 1 else 6
    out = set()
    for w in range(depth):
        for b in range(width):
            try:
                off, bp = init_cell(anchor, w, b, bp_default)
                out.add((off, bp))
            except Exception:
                pass
    return out


def lab_x_for_byte(off: int) -> int | None:
    """Map a CRAM byte offset to its column's X coordinate.

    LAB columns: search _LAB_CRAM_END (END marks last byte of column).
    Non-LAB columns (X=15, 20, 27): use _NONLAB_X_BASE.
    """
    for x, end in _LAB_CRAM_END.items():
        if end - LAB_COL_STEP < off <= end:
            return x
    for x, base in _NONLAB_X_BASE.items():
        if base <= off < base + LAB_COL_STEP:
            return x
    return None


def main() -> int:
    print("Loading v0 ⊕ nv_zero_global cells (X15_Y16_N0 SDP 4x2048)...")
    v0_cells = all_v0_cells()
    print(f"  total: {len(v0_cells)} cells")

    print("\nLoading static directive buckets:")
    bucket_loaders = [
        ("NV_BASELINE_PACK", load_nv_baseline),
        ("IOB_PAD_NV", load_iob_pad_nv),
        ("M9K_MODE_4x2048_quartus_gold_sdp (X15_Y16_N0)",
         load_m9k_mode_sdp_x15_y16),
        ("OUTROUTE_G15 sigcache (all positions, union)",
         load_outroute_sigcache),
        ("LAB_CLK_SEL_LE per_le (all 14 LABs, union)",
         load_clk_lab_sel_per_le),
        ("M9K_INIT 4x2048 anchor (X15_Y16_N0)",
         lambda: m9k_init_anchor_cells_x15_y16(4, 2048)),
        ("ROUTE sig-cache (1725 entries, all directive-writable)",
         load_route_sigcache),
    ]
    buckets: dict[str, set[tuple[int, int]]] = {}
    for name, loader in bucket_loaders:
        try:
            b = loader()
        except Exception as e:
            print(f"  {name}: ERROR {e}")
            b = set()
        buckets[name] = b
        print(f"  {name}: {len(b)} cells, {len(b & v0_cells)} ∩ v0_cells")

    # Per-cell coverage classification
    print("\nPer-cell coverage classification:")
    coverage = defaultdict(set)  # bucket_name → cells covered
    uncovered: set[tuple[int, int]] = set(v0_cells)
    for name, b in buckets.items():
        hit = b & v0_cells
        coverage[name] = hit
        uncovered -= hit
    print(f"  Cells covered by ≥1 static directive: {len(v0_cells) - len(uncovered)}")
    print(f"  Cells NOT covered by any static directive: {len(uncovered)}")

    # Region-level breakdown
    print("\nRegion breakdown (covered / uncovered):")
    print(f"  {'region':18} {'total':>7} {'covered':>9} {'uncov':>7} "
          f"{'cov%':>7}")
    for lo, hi, name in REGIONS:
        in_region = {(o, bp) for (o, bp) in v0_cells
                     if lo <= (o - PRE) // FRAME <= hi}
        u_in_region = in_region & uncovered
        cov = len(in_region) - len(u_in_region)
        pct = 100.0 * cov / len(in_region) if in_region else 0.0
        print(f"  {name:18} {len(in_region):>7} {cov:>9} "
              f"{len(u_in_region):>7} {pct:>6.1f}%")

    # Top frames with uncovered cells
    print("\nTop 20 frames with uncovered cells:")
    fc: Counter[int] = Counter()
    for off, bp in uncovered:
        frame = (off - PRE) // FRAME
        fc[frame] += 1
    for frame, count in fc.most_common(20):
        print(f"  frame {frame:5} ({region_of(frame):16}): {count:4} cells")

    # LAB-column ownership for uncovered cells (potential LUT/ROUTE coverage)
    print("\nUncovered cells by LAB column (X coord):")
    xc: Counter[int | None] = Counter()
    for off, bp in uncovered:
        x = lab_x_for_byte(off)
        xc[x] += 1
    for x, count in sorted(xc.items(),
                           key=lambda t: -t[1])[:15]:
        tag = f"X={x}" if x is not None else "<unknown>"
        is_lab = (x in _LAB_CRAM_END) if x is not None else False
        is_m9k = x in (15, 27)
        is_mult = x == 20
        kind = ("M9K" if is_m9k else "MULT" if is_mult
                else "LAB" if is_lab else "?")
        print(f"  {tag:8} ({kind:4}): {count:4} cells")

    # Per-bucket coverage detail
    print("\nPer-bucket coverage (cells in v0 covered by each):")
    for name, hit in coverage.items():
        print(f"  {name:55} {len(hit):>5}")

    # Suggested next-step buckets — frames with high uncovered but not yet
    # ascribed to an existing directive
    print("\nGap summary (uncovered cells per region with frame examples):")
    region_gaps: dict[str, list[int]] = defaultdict(list)
    for frame, count in fc.most_common():
        region_gaps[region_of(frame)].append((frame, count))
    for region in [r[2] for r in REGIONS]:
        items = region_gaps.get(region, [])
        if not items:
            continue
        total = sum(c for _, c in items)
        print(f"  {region:18} total={total:4}  "
              f"top frames: {items[:5]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
