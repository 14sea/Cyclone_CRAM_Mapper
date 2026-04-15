# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 2 of nv_zero_global retirement — mine NV_BASELINE_PACK cells.

Given nv_zero_global.rbf and PURE_ZERO (programmatic baseline from
fuzz.pure_zero_rbf), compute the XOR cell set and bucket it into
named sub-packs that Phase 3 will expose as FASM directives.

Buckets:
  iob_bank_default_pack   — hdr band (off < 5282); per-pin LVTTL +
                            bank-config defaults.  Single opaque pack
                            for now; a per-pin sub-decomposition is
                            a future refinement.
  local_clk_e1_baseline   — known universal cells at (7312, 4) and
                            (7519, 4) per memory lab_clk_sel_decomposes_.
                            Plus (7520, 4) = GCLK-enable mux bit — in
                            NV this is 0 (auto mode), so NOT expected
                            in the delta; absence is a sanity check.
  local_clk_path_a        — 16-cell spine from memory gclk_16cell_spine_
                            9_of_13_labs (frames 55,57,62,63,64,72,75,
                            85,86,89,93,95 + 1178,1181 + 1728,1730,1732
                            at bp∈{2,4}).  9-LAB shared local-clk wire.
  low_frame_infra         — other cells in frames 25..COLUMN_BASE_MIN
                            (chip-global infra outside LAB columns).
  lab_col[X]              — cells inside LAB column X's 7350-byte span
                            (bucketed by X, not further resolved to Y/N
                            — that is a per-LAB sub-decomposition step).
  high_frame_band         — cells in frames past the last LAB column
                            (block-band / M9K / DSPMULT / trailer infra).
  residue                 — anything unplaced (for inspection).

Output: results/nv_baseline_pack.json with the bucket map and metadata.
Also prints a summary for go/no-go: residue must be < 20% of total.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

from bitstream import (                                         # noqa: E402
    CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME,
    CRC_FRAME_SIZE,
    CRC_LAST_FRAME,
    CRC_PREAMBLE,
)
from config import COLUMN_BASE                                  # noqa: E402
from pure_zero_rbf import make_pure_zero_rbf                    # noqa: E402

NV_ZERO = REPO / "results" / "rbf" / "nv_zero_global.rbf"
OUT = REPO / "results" / "nv_baseline_pack.json"

CRAM_START = CRC_PREAMBLE + CRC_FIRST_CRAM_FRAME * CRC_FRAME_SIZE   # 5282
COLUMN_STRIDE = 7350
COLUMN_SPAN_BYTES = COLUMN_STRIDE   # each column occupies exactly one stride
COLUMN_ACTIVE_LOW = 136             # period_start = COLUMN_BASE[x] - 136

# Memory-known anchor cells
LOCAL_CLK_E1_BASELINE_KNOWN = [
    (7312, 4),
    (7519, 4),
]
# 16-cell spine — frame/bp pattern from memory
LOCAL_CLK_PATH_A_FRAMES_BP2 = [55, 57, 62, 63, 64, 72, 75, 85, 86, 89, 93, 95]
LOCAL_CLK_PATH_A_FRAMES_BP4 = [1178, 1181, 1728, 1730, 1732]


def frame_of(off: int) -> int:
    return (off - CRC_PREAMBLE) // CRC_FRAME_SIZE


def is_crc_byte(off: int) -> bool:
    """Is this offset a CRC slot (last 2 bytes of a CRAM frame)?"""
    if off < CRAM_START:
        return False
    f = frame_of(off)
    if f > CRC_LAST_FRAME:
        return False
    start = CRC_PREAMBLE + f * CRC_FRAME_SIZE
    return off in (start + CRC_DATA_SIZE, start + CRC_DATA_SIZE + 1)


def column_of(off: int) -> int | None:
    """Return LAB X whose 7350-byte column contains off, else None."""
    for x, base in COLUMN_BASE.items():
        lo = base - COLUMN_ACTIVE_LOW
        hi = lo + COLUMN_SPAN_BYTES
        if lo <= off < hi:
            return x
    return None


def extract_cells(delta: bytes) -> list[tuple[int, int]]:
    """Return all (offset, bp) positions where delta bit is set, skipping CRC bytes."""
    cells = []
    for off, v in enumerate(delta):
        if v == 0:
            continue
        if is_crc_byte(off):
            continue
        for bp in range(8):
            if (v >> bp) & 1:
                cells.append((off, bp))
    return cells


def main():
    nv = NV_ZERO.read_bytes()
    pz = make_pure_zero_rbf()
    assert len(nv) == len(pz) == 368011
    delta = bytes(a ^ b for a, b in zip(nv, pz))
    cells = extract_cells(delta)
    total = len(cells)
    print(f"NV ^ PURE_ZERO: {total} bit-cells (CRC bytes excluded)")

    # --- Build buckets ---
    spine_a_set = set()
    for f in LOCAL_CLK_PATH_A_FRAMES_BP2:
        base = CRC_PREAMBLE + f * CRC_FRAME_SIZE
        for b in range(CRC_DATA_SIZE):
            spine_a_set.add((base + b, 2))
    for f in LOCAL_CLK_PATH_A_FRAMES_BP4:
        base = CRC_PREAMBLE + f * CRC_FRAME_SIZE
        for b in range(CRC_DATA_SIZE):
            spine_a_set.add((base + b, 4))
    # (the memory listed frame/bp combos but didn't pin specific offsets —
    # so we accept any bit at those frame+bp positions as candidates; the
    # final spine bucket is the intersection with the actual delta)
    e1_baseline_set = set(LOCAL_CLK_E1_BASELINE_KNOWN)

    # Boundary of low-frame-infra vs first LAB column
    col_min_base = min(COLUMN_BASE.values()) - COLUMN_ACTIVE_LOW    # X=3 base
    col_max_base = max(COLUMN_BASE.values()) - COLUMN_ACTIVE_LOW + COLUMN_SPAN_BYTES

    hdr = []
    e1_base = []
    spine_a = []
    low_frame = []
    lab_col: dict[int, list] = {x: [] for x in COLUMN_BASE}
    high_frame = []
    residue = []

    for off, bp in cells:
        if off < CRAM_START:
            hdr.append([off, bp])
            continue
        cell = (off, bp)
        if cell in e1_baseline_set:
            e1_base.append([off, bp])
            continue
        if cell in spine_a_set:
            spine_a.append([off, bp])
            continue
        x = column_of(off)
        if x is not None:
            lab_col[x].append([off, bp])
            continue
        if off < col_min_base:
            low_frame.append([off, bp])
            continue
        if off >= col_max_base:
            high_frame.append([off, bp])
            continue
        residue.append([off, bp])

    # --- Summary ---
    def pct(n):
        return f"{100.0 * n / total:5.1f}%"

    print()
    print(f"  hdr-band (off < {CRAM_START}):     {len(hdr):6d}  {pct(len(hdr))}  → iob_bank_default_pack")
    print(f"  local_clk_e1_baseline (2 known): {len(e1_base):6d}  {pct(len(e1_base))}")
    print(f"  local_clk_path_a candidates:     {len(spine_a):6d}  {pct(len(spine_a))}")
    print(f"  low-frame chip-infra:            {len(low_frame):6d}  {pct(len(low_frame))}")
    lab_total = sum(len(v) for v in lab_col.values())
    print(f"  LAB column buckets (total):      {lab_total:6d}  {pct(lab_total)}")
    live = sum(1 for v in lab_col.values() if v)
    print(f"    columns with ≥1 cell: {live}/{len(lab_col)}")
    for x in sorted(lab_col):
        if lab_col[x]:
            print(f"      X={x:2d}: {len(lab_col[x]):5d} cells")
    print(f"  high-frame infra:                {len(high_frame):6d}  {pct(len(high_frame))}")
    print(f"  residue (unplaced):              {len(residue):6d}  {pct(len(residue))}")

    residue_pct = 100.0 * len(residue) / total
    print()
    if residue_pct >= 20.0:
        print(f"  !! residue {residue_pct:.1f}% >= 20%  — DECOMPOSITION GATE FAILED")
    else:
        print(f"  residue {residue_pct:.1f}% < 20%  — DECOMPOSITION GATE PASSED")

    # --- Write output ---
    out = {
        "meta": {
            "source": "nv_zero_global.rbf ^ pure_zero_rbf (generated)",
            "total_cells": total,
            "crc_bytes_skipped": True,
            "buckets": {
                "iob_bank_default_pack": len(hdr),
                "local_clk_e1_baseline": len(e1_base),
                "local_clk_path_a": len(spine_a),
                "low_frame_infra": len(low_frame),
                "lab_columns": {str(x): len(v) for x, v in lab_col.items() if v},
                "high_frame_infra": len(high_frame),
                "residue": len(residue),
            },
            "residue_pct": round(residue_pct, 2),
        },
        "iob_bank_default_pack": hdr,
        "local_clk_e1_baseline": e1_base,
        "local_clk_path_a": spine_a,
        "low_frame_infra": low_frame,
        "lab_columns": {str(x): v for x, v in lab_col.items() if v},
        "high_frame_infra": high_frame,
        "residue": residue,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}")
    return 0 if residue_pct < 20.0 else 1


if __name__ == "__main__":
    sys.exit(main())
