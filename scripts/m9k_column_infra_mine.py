# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-(X,Y) M9K_COLUMN_INFRA bucket miner.

Discovery (2026-04-26):
  * X15 column-infra cells live in lab_low frames (25..1006).
  * X27 column-infra cells live in lab_high frames (1014..1691).
  * In both cases, infra cells sit at bp = Y-formula encoded bit and
    occupy a Y-specific byte_idx range within the column.
  * Pairwise Jaccard between sites = 0.00 — every (X,Y) is fully
    disjoint, so the codec needs a per-site bucket (mirrors M9K_INIT).

Bucket = (v0 ⊕ matched_baseline) ∩ {region(X), bp(Y)}.
  bp(y) = (6 - group) if slot == 2 else (7 - group)
  slot, group = (y - 2) % 3, (y - 2) // 3

Inputs: tmp/m9k_mode_quartus_gold/4x2048/sdp/<site>/{v0,baseline}.rbf
Output: results/m9k_column_infra.json with per-site infra_cells list.
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRE, FRAME, DPF = 32, 210, 208

LAB_LOW = (25, 1006)
LAB_HIGH = (1014, 1691)

# Map of M9K X column → CRAM region housing its column-infra cells.
COL_REGION = {15: LAB_LOW, 27: LAB_HIGH}


def y_to_bp(y: int) -> int:
    slot = (y - 2) % 3
    group = (y - 2) // 3
    return (6 - group) if slot == 2 else (7 - group)


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


def column_infra(diff: set[tuple[int, int]], x: int, y: int) -> set[tuple[int, int]]:
    region = COL_REGION.get(x)
    if region is None:
        return set()
    target_bp = y_to_bp(y)
    lo, hi = region
    return {(off, bp) for (off, bp) in diff
            if bp == target_bp and lo <= (off - PRE) // FRAME <= hi}


def mine_site(site_dir: Path, w: int, d: int, mode: str) -> dict:
    x, y, n = parse_site(site_dir.name)
    tag = f"{w}x{d}_{mode}"
    v0 = (site_dir / f"m9k_mode_gold_{tag}_v0.rbf").read_bytes()
    bl = (site_dir / f"m9k_mode_gold_{tag}_baseline.rbf").read_bytes()
    diff = diff_cells(v0, bl)
    bucket = column_infra(diff, x, y)
    return {
        "site": site_dir.name,
        "x": x, "y": y, "n": n,
        "target_bp": y_to_bp(y),
        "region": "lab_low" if x == 15 else "lab_high" if x == 27 else "?",
        "total_diff": len(diff),
        "infra_count": len(bucket),
        "infra_cells": sorted(bucket),
    }


def main(argv: list[str]) -> int:
    base = ROOT / "tmp/m9k_mode_quartus_gold/4x2048/sdp"
    if not base.exists():
        print(f"missing baselines/v0 at {base}")
        return 2
    sites = sorted(p.name for p in base.iterdir()
                   if p.is_dir() and p.name.startswith("X")
                   and "_Y" in p.name and "_N" in p.name)
    results = {}
    for site in sites:
        info = mine_site(base / site, 4, 2048, "sdp")
        results[site] = info
        print(f"  {site:14} bp={info['target_bp']} region={info['region']:9} "
              f"infra={info['infra_count']:5}")

    # Save
    out_path = ROOT / "results/m9k_column_infra.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")

    # Site-invariance: pairwise Jaccard summary
    sets = {s: set(map(tuple, results[s]["infra_cells"])) for s in sites}
    jacc = Counter()
    keys = list(sites)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = sets[keys[i]], sets[keys[j]]
            if not (a or b):
                continue
            jacc[round(len(a & b) / len(a | b), 2)] += 1
    print(f"Pairwise Jaccard histogram across {len(keys)} sites: {dict(jacc)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
