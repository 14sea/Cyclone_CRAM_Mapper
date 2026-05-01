# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine design-specific block-band cells from a Quartus reference RBF.

Stores results to results/design_block_band.json keyed by design tag.
Each entry holds the (off, bp) cells in the block-band region (frames
1692-1738, byte<208) where the design RBF differs from nv_zero_global.

This is the Option 3-residual codec build: each design is mined ONCE
from its own Quartus reference; np2fasm later emits the cells via the
DESIGN_BLOCK_BAND_PACK FASM directive at runtime (Quartus-free).

For NEORV32: ~417 cells covering the full block-band (M9K mode/enable
+ IOB block-band infra + clock-control blocks + miscellaneous).

Usage:
    python3 scripts/mine_design_block_band.py --tag neorv32 \\
        --rbf ~/see_neorv32_run_linux/output/neorv32_demo.rbf
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from m9k_blink_diff_nv_mine import block_band_diff_cells, NV  # noqa: E402

OUT_JSON = ROOT / "results/design_block_band.json"


def mine(rbf_path: Path) -> tuple[list[tuple[int, int]], str]:
    rbf = rbf_path.read_bytes()
    if len(rbf) != 368011:
        raise SystemExit(f"unexpected RBF size {len(rbf)} for {rbf_path}")
    nv = NV.read_bytes()
    cells = block_band_diff_cells(rbf, nv)
    sha = hashlib.sha256(rbf).hexdigest()
    return cells, sha


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="design name (e.g. neorv32)")
    ap.add_argument("--rbf", required=True, help="path to Quartus reference RBF")
    args = ap.parse_args()

    rbf_path = Path(args.rbf).expanduser().resolve()
    cells, sha = mine(rbf_path)

    db = {}
    if OUT_JSON.exists():
        db = json.loads(OUT_JSON.read_text())

    # Frame distribution for sanity
    PRE = 32
    FRAME = 210
    iob_range = sum(1 for o, _ in cells if (o-PRE)//FRAME < 1720)
    m9k_range = sum(1 for o, _ in cells if (o-PRE)//FRAME >= 1720)

    db[args.tag] = {
        "cells": [list(c) for c in cells],
        "source_rbf": str(rbf_path),
        "source_sha256": sha,
        "scope": "block_band_full_frames_1692_1738_data_bytes_only",
        "cell_count": len(cells),
        "iob_range_count_frames_1692_1719": iob_range,
        "m9k_range_count_frames_1720_1738": m9k_range,
    }

    OUT_JSON.write_text(json.dumps(db, indent=2, sort_keys=True))
    print(f"[wrote] {OUT_JSON.relative_to(ROOT)}")
    print(f"  tag:        {args.tag}")
    print(f"  total:      {len(cells)} cells")
    print(f"  IOB range:  {iob_range} (frames 1692-1719)")
    print(f"  M9K range:  {m9k_range} (frames 1720-1738)")
    print(f"  sha256:     {sha[:16]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
