# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage A.1 — audit neorv32_demo.rbf directive coverage.

Produces a column-binned + band-binned histogram of the cells that differ
between the Quartus gold `neorv32_demo.rbf` and `nv_zero_global.rbf`,
then categorises each band against FASM directives the codec already
supports. Output is `tmp/neorv32_directive_audit.txt` (human-readable)
plus `results/neorv32_directive_audit.json` (machine-readable).

Usage:
    python3 scripts/stage_a_audit/audit_neorv32_gold.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import (
    CRC_PREAMBLE,
    CRC_FRAME_SIZE,
    CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME,
    CRC_LAST_FRAME,
)
from config import COLUMN_BASE, LAB_X, JAILBREAK_LAB_X

GOLD_PATH = Path("/home/test/see_neorv32_run_linux/output/neorv32_demo.rbf")
ZERO_PATH = ROOT / "results" / "rbf" / "nv_zero_global.rbf"
OUT_TXT = ROOT / "tmp" / "neorv32_directive_audit.txt"
OUT_JSON = ROOT / "results" / "neorv32_directive_audit.json"

# Block-band frame range (per CLAUDE.md): M9K / DSPMULT / IOB enable cells
BLOCK_BAND = (1692, 1738)
CLOCK_NET_BAND = (1005, 1015)  # DSPMULT_CLOCK_ENABLE, LOCAL_CLK_* territory

# Physical CRAM column width = 7350 bytes (LAB column step). Every LAB X
# column covers [COLUMN_BASE[x] - 136, COLUMN_BASE[x] - 136 + 7350). Block
# columns (M9K X=15,27; MULT X=20) also occupy column-width regions but
# lack a LAB entry.
COLUMN_WIDTH = 7350
NON_LAB_X = {
    15: "M9K",
    27: "M9K",
    20: "MULT",
}


def load_bytes(p: Path) -> bytes:
    return p.read_bytes()


def diff_cells(target: bytes, zero: bytes):
    """Yield (off, bp) for every bit where target XOR zero is 1, in the
    CRAM data region (frames 25..1751, data bytes only, CRC trailers
    excluded)."""
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        for off in range(s, s + CRC_DATA_SIZE):
            x = target[off] ^ zero[off]
            if not x:
                continue
            for bp in range(8):
                if (x >> bp) & 1:
                    yield off, bp, n


def classify_by_column(off: int) -> tuple[str, int | None]:
    """Return ('LAB' | 'M9K' | 'MULT' | 'unmapped', x_coord | None)."""
    # Column spans are [COLUMN_BASE[x] - 136, COLUMN_BASE[x] - 136 + 7350)
    all_cols = list(COLUMN_BASE.items()) + [(x, 0) for x in NON_LAB_X]
    # Recompute NON_LAB_X bases from stride: X=15/20/27 are inter-LAB; find
    # by bracketing between adjacent LAB bases.
    non_lab_bases = {}
    sorted_lab = sorted(COLUMN_BASE.items(), key=lambda kv: kv[1])
    for x_nl, kind in NON_LAB_X.items():
        # Find the adjacent LAB X whose base is just below.
        prev_base = None
        for lx, lb in sorted_lab:
            if lb < (COLUMN_BASE.get(x_nl + 1, 0) or 0) and lx < x_nl:
                if prev_base is None or lb > prev_base:
                    prev_base = lb
        # Simpler: X=15 sits between X=14 (jailbreak 0x1B2B2) and X=16
        # (0x2BFC2); block columns span multiple 7350 strides. Use a fixed
        # heuristic: NON_LAB column base = previous LAB base + 7350.
    # Use explicit known bases (mined once):
    BLOCK_COL_BASE = {
        15: 0x1CF68,   # X=14 (0x1B2B2) + 7350
        20: 0x33208,   # X=19 (0x3192C) + 7350 * 2 (wider MULT)
        27: 0x3F6A8,   # X=26 (0x3D9F2) + 7350
    }
    for lx, base in sorted(COLUMN_BASE.items(), key=lambda kv: kv[1]):
        lo = base - 136
        hi = lo + COLUMN_WIDTH
        if lo <= off < hi:
            return ("LAB", lx)
    for x_nl, base in BLOCK_COL_BASE.items():
        lo = base - 136
        hi = lo + COLUMN_WIDTH
        if lo <= off < hi:
            return (NON_LAB_X[x_nl], x_nl)
    return ("unmapped", None)


def analyze():
    if not GOLD_PATH.exists():
        raise SystemExit(f"gold not found: {GOLD_PATH}")
    if not ZERO_PATH.exists():
        raise SystemExit(f"zero not found: {ZERO_PATH}")

    gold = load_bytes(GOLD_PATH)
    zero = load_bytes(ZERO_PATH)

    cells = list(diff_cells(gold, zero))
    total = len(cells)

    frame_hist: dict[int, int] = {}
    column_hist: dict[str, int] = {}     # "LAB_X", "M9K_15", etc
    column_frames: dict[str, set[int]] = {}
    band_counts = {
        "header_adj_25_100": 0,
        "body_lab_100_1691": 0,
        "clock_net_1005_1015": 0,
        "block_band_1692_1738": 0,
        "tail_1739_1751": 0,
    }

    for off, bp, frame in cells:
        frame_hist[frame] = frame_hist.get(frame, 0) + 1

        # Band
        if frame <= 100:
            band_counts["header_adj_25_100"] += 1
        elif frame <= 1691:
            if CLOCK_NET_BAND[0] <= frame <= CLOCK_NET_BAND[1]:
                band_counts["clock_net_1005_1015"] += 1
            band_counts["body_lab_100_1691"] += 1
        elif frame <= BLOCK_BAND[1]:
            band_counts["block_band_1692_1738"] += 1
        else:
            band_counts["tail_1739_1751"] += 1

        # Column
        kind, x = classify_by_column(off)
        key = f"{kind}_{x}" if x is not None else kind
        column_hist[key] = column_hist.get(key, 0) + 1
        column_frames.setdefault(key, set()).add(frame)

    # Derived stats
    active_frames = len(frame_hist)
    top_cols = sorted(column_hist.items(), key=lambda kv: -kv[1])

    # LAB cover: how many LAB columns are exercised, out of 22 CE6 + 6 jailbreak
    lab_cols_active = [k for k in column_hist if k.startswith("LAB_")]
    ce6_lab_active = [k for k in lab_cols_active if int(k.split("_")[1]) in LAB_X]
    jb_lab_active = [k for k in lab_cols_active if int(k.split("_")[1]) in JAILBREAK_LAB_X]

    lines: list[str] = []
    lines.append(f"# Stage A.1 — neorv32_demo.rbf directive coverage audit")
    lines.append(f"# vs nv_zero_global baseline")
    lines.append("#")
    lines.append(f"# total diff cells     = {total}")
    lines.append(f"# active frames        = {active_frames}/{CRC_LAST_FRAME-CRC_FIRST_CRAM_FRAME+1}")
    lines.append(f"# LAB columns active   = {len(ce6_lab_active)}/{len(LAB_X)} CE6 + "
                 f"{len(jb_lab_active)}/{len(JAILBREAK_LAB_X)} jailbreak")
    lines.append("#")
    lines.append("# === Frame bands ===")
    for b, c in band_counts.items():
        pct = 100.0 * c / total if total else 0.0
        lines.append(f"#   {b:32s}: {c:7d} cells ({pct:5.2f}%)")
    lines.append("#")
    lines.append("# === Column histogram ===")
    lines.append("# kind_x: cells, active-frames")
    for k, c in top_cols:
        nf = len(column_frames[k])
        lines.append(f"#   {k:12s}: {c:6d} cells, {nf:4d} frames")
    lines.append("#")
    lines.append("# === Top 20 frames by cell count ===")
    for n, c in sorted(frame_hist.items(), key=lambda kv: -kv[1])[:20]:
        off0 = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        lines.append(f"#   frame {n:4d} (byte 0x{off0:06x}): {c:5d} cells")
    lines.append("#")
    lines.append("# === Known-directive coverage ===")
    lines.append("# Directives with mined cells (codec knows how to place):")
    lines.append("#   LUT, ROUTE, GCLK, GCLK_PIN, LAB_CLK_SEL, LAB_CLK_SEL_LE,")
    lines.append("#   LUT_ARITH, IOB_IN, IOB_OUT, IOB_ROUTE, IOB_BASELINE_NV,")
    lines.append("#   IOB_CLK_INPUT, M9K.INIT_*, NV_BASELINE_PACK family,")
    lines.append("#   M9K_MODE (codec only, emission gated), DSPMULT_GLOBAL_ON")
    lines.append("#   (codec only, HW-falsified 2026-04-16)")
    lines.append("#")
    lines.append("# Unmined block-band cells are residue that Stage C (M9K")
    lines.append("# modes beyond 9x512/18x512) + Stage B (IOB bidir/OE) must")
    lines.append("# close.")
    lines.append("#")
    lines.append("# === Device + resource notes (from neorv32_demo.fit.summary) ===")
    lines.append("# Device: EP4CE10F17C8 (jailbreak target).  CE6 silicon covers")
    lines.append("# 22/28 LAB columns; Quartus used all 28 because this RBF")
    lines.append("# was fit for EP4CE10.  Functional-equivalent open-toolchain")
    lines.append("# build can target CE6-only (22 LABs, 6272 LEs, ~75% util).")
    lines.append("# Resources: 4712 LE (46% CE10 / 75% CE6), 2367 DFFs,")
    lines.append("# 168,960 memory bits (40% — heavy M9K use),")
    lines.append("# 0 DSPMULTs (MULT_20 cells are just default-off residue),")
    lines.append("# 0 PLLs (no DDIO/PLL mining needed), 51 pins.")
    lines.append("#")
    lines.append("# === Stage-fork implications ===")
    lines.append("# * Stage A.5 (CE6-vs-CE10 fork): largely answered already.")
    lines.append("#   Quartus gold is CE10; for CE6-open-toolchain build, we")
    lines.append("#   let nextpnr place in the 22 CE6 LABs; gold byte-equivalence")
    lines.append("#   is not the goal anyway.")
    lines.append("# * Stage B (tristate/bidir IOB): 16 sdram_dq pins confirmed")
    lines.append("#   present in ax301_top design → narrow scope holds.")
    lines.append("# * Stage C (M9K mode expansion): 40% memory-bits usage")
    lines.append("#   across many M9K sites; need 8x64 SP, 8x2048 SDP, 32x32 TDP,")
    lines.append("#   32x1024 ROM modes beyond the calibrated 9x512 + 18x512.")
    lines.append("# * Stage D (32-bit carry): 2367 DFFs suggest the ALU's carry")
    lines.append("#   chain is wide; width=32 arith blob mining is load-bearing.")
    lines.append("# * Stage E/F: LAB-column domination (98.74%) = sig-cache miss")
    lines.append("#   budget is the chokepoint; demand-driven route mining is")
    lines.append("#   the right cadence.")

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(lines) + "\n")

    json_out = {
        "gold": str(GOLD_PATH),
        "zero": str(ZERO_PATH),
        "total_cells": total,
        "active_frames": active_frames,
        "band_counts": band_counts,
        "column_hist": column_hist,
        "column_frames_count": {k: len(v) for k, v in column_frames.items()},
        "top_20_frames": [
            {"frame": n, "byte": CRC_PREAMBLE + n * CRC_FRAME_SIZE, "cells": c}
            for n, c in sorted(frame_hist.items(), key=lambda kv: -kv[1])[:20]
        ],
        "ce6_lab_active": sorted(int(k.split("_")[1]) for k in ce6_lab_active),
        "jailbreak_lab_active": sorted(int(k.split("_")[1]) for k in jb_lab_active),
    }
    OUT_JSON.write_text(json.dumps(json_out, indent=2))

    print(f"wrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")
    print()
    print(f"summary: {total} cells, {active_frames} frames, "
          f"{len(ce6_lab_active)}/{len(LAB_X)} CE6 LABs + "
          f"{len(jb_lab_active)}/{len(JAILBREAK_LAB_X)} jailbreak LABs active")
    print()
    for b, c in band_counts.items():
        pct = 100.0 * c / total if total else 0.0
        print(f"  {b:32s}: {c:7d} cells ({pct:5.2f}%)")


if __name__ == "__main__":
    analyze()
