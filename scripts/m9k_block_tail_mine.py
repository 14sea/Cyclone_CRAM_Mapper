# SPDX-License-Identifier: GPL-3.0-or-later
"""M9K_BLOCK_TAIL bucket miner.

Per the 2026-04-26 companion-infra audit, every M9K instance leaves
~15-25 cells in block_band_post (frames 1739..1751).  Active frames
across all 26 SDP sites: 1748 + 1750 + 1751 (audit predicted 1748 +
1751; 1750 contributes a few cells per site).

Extraction: (v0 ⊕ nv_zero_global) ∩ {block_band_post}.  Mining vs
matched_baseline gives a 14-26 cell bucket per site, but ~10 of
those are matched_baseline-state cells v0 also has → XOR-flipping
them onto nv_zero_global moves AWAY from v0.  Mining vs nv_zero_global
directly yields the clean codec-applicable bucket.

Output: results/m9k_block_tail.json with per-site cells.
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRE, FRAME, DPF = 32, 210, 208
BLOCK_BAND_POST = (1739, 1751)


def diff_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
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


def parse_site(name: str) -> tuple[int, int, int]:
    p = name.split("_")
    return int(p[0][1:]), int(p[1][1:]), int(p[2][1:])


def block_tail(diff: set[tuple[int, int]]) -> set[tuple[int, int]]:
    lo, hi = BLOCK_BAND_POST
    return {(off, bp) for (off, bp) in diff
            if lo <= (off - PRE) // FRAME <= hi}


def mine_site(site_dir: Path, w: int, d: int, mode: str, nv: bytes) -> dict:
    x, y, n = parse_site(site_dir.name)
    tag = f"{w}x{d}_{mode}"
    v0 = (site_dir / f"m9k_mode_gold_{tag}_v0.rbf").read_bytes()
    diff = diff_cells(v0, nv)
    bucket = block_tail(diff)
    return {
        "site": site_dir.name,
        "x": x, "y": y, "n": n,
        "tail_count": len(bucket),
        "tail_cells": sorted(bucket),
    }


def main(argv: list[str]) -> int:
    base = ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp"
    nv = (ROOT / "results/rbf/nv_zero_global.rbf").read_bytes()
    sites = sorted(p.name for p in base.iterdir()
                   if p.is_dir() and p.name.startswith("X")
                   and "_Y" in p.name and "_N" in p.name)
    results = {}
    for site in sites:
        info = mine_site(base / site, 4, 2048, "sdp", nv)
        results[site] = info
        print(f"  {site:14}  tail={info['tail_count']:3}")

    # Site-invariance check
    sets = {s: set(map(tuple, results[s]["tail_cells"])) for s in sites}
    x15_sites = [s for s in sites if s.startswith("X15_")]
    x27_sites = [s for s in sites if s.startswith("X27_")]
    print()
    if x15_sites:
        x15_intersection = set.intersection(*[sets[s] for s in x15_sites])
        x15_union = set.union(*[sets[s] for s in x15_sites])
        print(f"X15 ({len(x15_sites)} sites): "
              f"intersection={len(x15_intersection)}  union={len(x15_union)}")
    if x27_sites:
        x27_intersection = set.intersection(*[sets[s] for s in x27_sites])
        x27_union = set.union(*[sets[s] for s in x27_sites])
        print(f"X27 ({len(x27_sites)} sites): "
              f"intersection={len(x27_intersection)}  union={len(x27_union)}")
    if x15_sites and x27_sites:
        cross = x15_intersection & x27_intersection
        print(f"X15 ∩ X27 (shared core): {len(cross)} cells")

    # Pairwise jaccard
    keys = list(sites)
    jaccs = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = sets[keys[i]], sets[keys[j]]
            if a or b:
                jaccs.append(len(a & b) / len(a | b))
    if jaccs:
        print(f"Pairwise Jaccard: min={min(jaccs):.2f} max={max(jaccs):.2f} "
              f"mean={sum(jaccs)/len(jaccs):.2f}")

    out_path = ROOT / "results/m9k_block_tail.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
