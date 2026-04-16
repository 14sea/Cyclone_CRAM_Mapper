# SPDX-License-Identifier: GPL-3.0-or-later
"""DSPMULT per-site block-band analyzer (zero-compile).

Mirror of `fuzz/m9k_persite_analyze.py` for the X=20 DSP multiplier
column.  Reads the 42 archived `mult_loc_DSPMULT_X20_Y{y}_N{n}.rbf`
files and `mult_empty_baseline.rbf`, decomposes the block-band diff
into universal / per-site / per-N components, and reports what fraction
of cells are recoverable as a clean per-site directive.

Pure analysis, zero compiles.  Output:
  results/dspmult_persite_analyze.json

CRITICAL LESSON from M9K_MODE mining (2026-04-16): per-site mining
RBFs that share an unmatched IOB+clock harness leak harness infra
into the per-site diff, contaminating the "per-site" cells.  This
analyzer reports BOTH the raw decomposition AND a contamination
estimate (universal-cell counts vs design-band overlap) so we can
judge data quality before landing any DSPMULT_MODE directive.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from rbf_diff import diff_rbf_files

RBF_DIR = ROOT / "results" / "rbf"
BASELINE = RBF_DIR / "mult_empty_baseline.rbf"
HDR = 32
BLOCK_LO, BLOCK_HI = 1692, 1738
DATA_LO, DATA_HI = 25, 1691

# 42 sites: Y ∈ 1..21, N ∈ {0, 1}
SITES = [(20, y, n) for y in range(1, 22) for n in (0, 1)]


def _diff_buckets(rbf: Path) -> tuple[set, set]:
    """Return (block_band_cells, data_band_cells) vs BASELINE.

    Excludes CRC bytes (offset 208/209 within each 210-byte frame)
    and the header/postamble bands."""
    block, data = set(), set()
    for d in diff_rbf_files(str(BASELINE), str(rbf)):
        off = d.byte_offset
        if off < HDR:
            continue
        in_frame = (off - HDR) % 210
        if in_frame >= 208:
            continue
        fr = (off - HDR) // 210
        cell = (off, d.bit_position)
        if BLOCK_LO <= fr <= BLOCK_HI:
            block.add(cell)
        elif DATA_LO <= fr <= DATA_HI:
            data.add(cell)
    return block, data


def main() -> int:
    if not BASELINE.exists():
        print(f"ERROR: baseline missing: {BASELINE}", file=sys.stderr)
        return 1

    print(f"baseline: {BASELINE.name}")
    print(f"sites:    {len(SITES)} ({len({s[1] for s in SITES})} Y rows × "
          f"{len({s[2] for s in SITES})} N slots)")

    sites_block: dict[tuple[int, int, int], set] = {}
    sites_data: dict[tuple[int, int, int], set] = {}
    missing = []
    for x, y, n in SITES:
        rbf = RBF_DIR / f"mult_loc_DSPMULT_X{x}_Y{y}_N{n}.rbf"
        if not rbf.exists():
            missing.append(rbf.name)
            continue
        b, d = _diff_buckets(rbf)
        sites_block[(x, y, n)] = b
        sites_data[(x, y, n)] = d

    if missing:
        print(f"  skipped {len(missing)} missing RBFs: {missing[:3]}{'...' if len(missing) > 3 else ''}")
    print(f"  loaded  {len(sites_block)} per-site RBFs")
    if not sites_block:
        return 1

    block_sets = list(sites_block.values())
    universal = set.intersection(*block_sets)
    union = set.union(*block_sets)
    print()
    print(f"=== block band (frames {BLOCK_LO}-{BLOCK_HI}) ===")
    print(f"  universal (all sites share):  {len(universal):>4} cells")
    print(f"  union:                        {len(union):>4} cells")
    sizes = sorted(len(s) for s in block_sets)
    print(f"  per-site cell count:           min={sizes[0]} median={sizes[len(sizes)//2]} max={sizes[-1]}")

    per_site_unique = {k: v - universal for k, v in sites_block.items()}
    pus_sizes = sorted(len(v) for v in per_site_unique.values())
    print(f"  per-site unique (block - U):   min={pus_sizes[0]} median={pus_sizes[len(pus_sizes)//2]} max={pus_sizes[-1]}")

    # N-invariance: at the same Y, do N=0 and N=1 share most per-site cells?
    n_pairs = []
    for y in sorted({s[1] for s in sites_block}):
        a = sites_block.get((20, y, 0))
        b = sites_block.get((20, y, 1))
        if a is None or b is None:
            continue
        shared = a & b
        sym_diff = (a - b) | (b - a)
        n_pairs.append((y, len(a), len(b), len(shared), len(sym_diff)))
    if n_pairs:
        print()
        print("=== N=0 vs N=1 at each Y (N-invariance check) ===")
        print(f"{'Y':>3} | {'N=0':>4} {'N=1':>4} {'shared':>6} {'sym_diff':>8}")
        for y, a, b, sh, sd in n_pairs:
            print(f"{y:>3} | {a:>4} {b:>4} {sh:>6} {sd:>8}")
        avg_shared = sum(p[3] for p in n_pairs) / len(n_pairs)
        avg_sd = sum(p[4] for p in n_pairs) / len(n_pairs)
        print(f"  avg shared/pair: {avg_shared:.1f}, avg sym-diff: {avg_sd:.1f}")
        if avg_sd < 5:
            print(f"  >>> N-invariance LIKELY (sym-diff <5 cells/pair)")
        else:
            print(f"  >>> N matters (sym-diff ≥5 cells)")

    # Contamination probe: how big is the data-band leak for each site?
    data_sizes = sorted(len(s) for s in sites_data.values())
    print()
    print(f"=== data-band leak (= harness routing/IOB contamination) ===")
    print(f"  per-site data-band diff: min={data_sizes[0]} median={data_sizes[len(data_sizes)//2]} max={data_sizes[-1]}")
    print(f"  >>> If median data leak >> 0, the per-site mining inputs include")
    print(f"      varying harness — the per-site BLOCK diff is also contaminated")
    print(f"      and any derived directive will misflip cells.  See M9K_MODE")
    print(f"      memory `m9k_mode_directive_scaffolded_data_contaminated.md`.")

    out = {
        "baseline": BASELINE.name,
        "n_sites": len(sites_block),
        "block_band": {
            "universal_count": len(universal),
            "union_count": len(union),
            "per_site_min": sizes[0],
            "per_site_max": sizes[-1],
            "per_site_median": sizes[len(sizes) // 2],
            "per_site_unique_median": pus_sizes[len(pus_sizes) // 2],
        },
        "n_invariance_check": [
            {"y": y, "n0_count": a, "n1_count": b, "shared": sh, "sym_diff": sd}
            for y, a, b, sh, sd in n_pairs
        ],
        "data_band_leak": {
            "min": data_sizes[0],
            "median": data_sizes[len(data_sizes) // 2],
            "max": data_sizes[-1],
        },
        "universal_cells": sorted([list(c) for c in universal]),
        "per_site": {
            f"X{x}Y{y}N{n}": sorted([list(c) for c in v])
            for (x, y, n), v in per_site_unique.items()
        },
    }
    out_path = ROOT / "results" / "dspmult_persite_analyze.json"
    out_path.write_text(json.dumps(out, indent=1) + "\n")
    print()
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
