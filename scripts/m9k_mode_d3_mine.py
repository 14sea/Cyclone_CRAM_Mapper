# SPDX-License-Identifier: GPL-3.0-or-later
"""M9K_MODE D3 re-mine — vs nv_zero_global instead of matched_baseline.

Per `m9k_mode_codec_silicon_broken_2026_04_25.md`, the production
`quartus_gold_*` bucket = (v0 ⊕ matched_baseline) ∩ block_band, with
3-variant intersection.  Applied to nv_zero_global via XOR, ~100 cells
of `matched_baseline ⊕ nv_zero_global ∩ block_band` are spurious and
22 cells of v0-state are missing (D2 falsified — see
`m9k_mode_d2_falsified_2026_04_26.md`).

D3 fix (this script): mine bucket = (v0 ⊕ nv_zero_global) ∩ block_band
directly — single variant, no 3-way intersection.  This drops the
matched_baseline pollution AND the 3-variant over-filter in one move.

The resulting bucket is v0-specific (won't work as a generic INIT-
invariant template), but for codec emission what matters is that
`np2fasm --base nv` reproduces v0 byte-identically.  INIT-invariance
is a separate problem belonging to the np2fasm template selection
layer, not the codec apply layer.

Output: results/m9k_mode_d3.json with per-site buckets.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRE, FRAME, DPF = 32, 210, 208
BLOCK_BAND = (1692, 1738)


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


def block_band(cells: set[tuple[int, int]]) -> set[tuple[int, int]]:
    lo, hi = BLOCK_BAND
    return {(off, bp) for off, bp in cells
            if lo <= (off - PRE) // FRAME <= hi}


def parse_site(name: str) -> tuple[int, int, int]:
    p = name.split("_")
    return int(p[0][1:]), int(p[1][1:]), int(p[2][1:])


def main() -> int:
    base = ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp"
    nv = (ROOT / "results/rbf/nv_zero_global.rbf").read_bytes()
    sites = sorted(p.name for p in base.iterdir()
                   if p.is_dir() and p.name.startswith("X")
                   and "_Y" in p.name and "_N" in p.name)
    results = {}
    for site in sites:
        x, y, n = parse_site(site)
        v0 = (base / site / "m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()
        bucket = block_band(diff_cells(v0, nv))
        results[site] = {
            "site": site, "x": x, "y": y, "n": n,
            "mode_d3_count": len(bucket),
            "mode_d3_cells": sorted(bucket),
        }
        print(f"  {site:14}  d3={len(bucket):3}")

    # Site-invariance summary
    sets = {s: set(map(tuple, results[s]["mode_d3_cells"])) for s in sites}
    x15 = [s for s in sites if s.startswith("X15_")]
    x27 = [s for s in sites if s.startswith("X27_")]
    if x15:
        i15 = set.intersection(*[sets[s] for s in x15])
        u15 = set.union(*[sets[s] for s in x15])
        print(f"\nX15 ({len(x15)}): intersection={len(i15)}  union={len(u15)}")
    if x27:
        i27 = set.intersection(*[sets[s] for s in x27])
        u27 = set.union(*[sets[s] for s in x27])
        print(f"X27 ({len(x27)}): intersection={len(i27)}  union={len(u27)}")
    if x15 and x27:
        print(f"X15 ∩ X27 core: {len(i15 & i27)}")

    out_path = ROOT / "results/m9k_mode_d3.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    main()
