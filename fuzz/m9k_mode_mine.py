# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine per-(site, width, depth) M9K block-band mode bits.

Background: `M9K_INIT_ANCHORS` only encodes WHERE init bits live. To
make a Quartus-equivalent open-toolchain RBF, the per-site
*enable/mode* cells in frames 1692-1738 also need to flip — without
them the RBF carries valid INIT data but the M9K silicon block is not
configured (HW would not read back the user pattern).

This script is a zero-compile analyzer: it reads existing baseline
RBFs (m9k_baseline_empty.rbf, m9k_as_*_base.rbf for width=9, and
m9k_calib18[b]_*_base.rbf for width=18) and writes
`results/m9k_mode_bits.json` keyed by (site, width, depth).

Width matters: at the same site, w=9 and w=18 share ~52 of ~72 mode
bits and toggle the remaining ~20 each — width is encoded in the mode
band, not in INIT alone.

Usage:
    python3 fuzz/m9k_mode_mine.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from rbf_diff import diff_rbf_files

# BASELINE choice: must match what `fasm2rbf` actually uses as
# `base_rbf`.  The open toolchain passes `results/rbf/nv_zero_global.rbf`
# (or, with `--base pure`, a PURE_ZERO buffer XOR'd with NV_BASELINE_PACK
# — same frames in the block band).  Mining against `m9k_baseline_empty`
# instead leaks ~58 block-band cells that already differ between the
# two zero-class RBFs, double-flipping those cells when emitted on
# `nv_zero_global` and worsening the final byte diff vs Quartus gold.
BASELINE = ROOT / "results" / "rbf" / "nv_zero_global.rbf"

# Block-band frames identified in Phase 5.0 (memory:
# phase5_nonlab_block_band).  Per-site M9K mode/enable bits live here.
BLOCK_FRAME_LO = 1692
BLOCK_FRAME_HI = 1738


def _cram_block_cells(rbf_path: Path) -> set[tuple[int, int]]:
    """Diff vs BASELINE, restricted to the block band (mode/enable)."""
    out = set()
    for d in diff_rbf_files(str(BASELINE), str(rbf_path)):
        off = d.byte_offset
        if off < 32 + 5282:
            continue
        fr = (off - 32) // 210
        if not (BLOCK_FRAME_LO <= fr <= BLOCK_FRAME_HI):
            continue
        if (off - 32) % 210 in (208, 209):
            continue
        out.add((off, d.bit_position))
    return out


def _w9_rbf(site: str) -> Path:
    return ROOT / "results" / "rbf" / f"m9k_as_{site}_9x512_base.rbf"


def _w18_rbf(site: str) -> Path:
    p = ROOT / "results" / "rbf" / f"m9k_calib18b_{site}_base.rbf"
    if p.exists():
        return p
    return ROOT / "results" / "rbf" / f"m9k_calib18_{site}_base.rbf"


# Width=9 sites — 31 from m9k_anchor_sweep
W9_SITES = (
    [f"X15_Y{y}_N0" for y in (5, 6, 8, 9, 10, 11, 12, 13, 14,
                              15, 16, 17, 18, 19, 20, 21, 22, 23)]
    + [f"X27_Y{y}_N0" for y in (11, 12, 13, 14, 15, 16, 17, 18, 19,
                                20, 21, 22, 23)]
)

# Width=18 sites — only the 5 calibrated for the smoke design
W18_SITES = [f"X15_Y{y}_N0" for y in (10, 11, 12, 13, 14)]


def main():
    if not BASELINE.exists():
        print(f"ERROR: baseline missing: {BASELINE}", file=sys.stderr)
        return 1

    out: dict[str, dict] = {}
    for site in W9_SITES:
        rbf = _w9_rbf(site)
        if not rbf.exists():
            print(f"  skip {site}/9x512: {rbf.name} missing")
            continue
        cells = _cram_block_cells(rbf)
        key = f"{site}_9x512"
        out[key] = {
            "site": site, "width": 9, "depth": 512,
            "cells": sorted([list(c) for c in cells]),
            "source": rbf.name,
        }
        print(f"  {key}: {len(cells)} cells")

    for site in W18_SITES:
        rbf = _w18_rbf(site)
        if not rbf.exists():
            print(f"  skip {site}/18x512: no calib18 RBF on disk")
            continue
        cells = _cram_block_cells(rbf)
        key = f"{site}_18x512"
        out[key] = {
            "site": site, "width": 18, "depth": 512,
            "cells": sorted([list(c) for c in cells]),
            "source": rbf.name,
        }
        print(f"  {key}: {len(cells)} cells")

    out_path = ROOT / "results" / "m9k_mode_bits.json"
    out_path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {out_path} ({len(out)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
