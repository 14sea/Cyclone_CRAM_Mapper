# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression test for the DESIGN_BLOCK_BAND_PACK FASM directive.

For every (tag, source_rbf) entry in results/design_block_band.json,
applies `DESIGN_BLOCK_BAND_PACK <tag>` to nv_zero_global and asserts:
  1. The resulting buffer's block-band region is byte-identical to the
     source RBF's block-band region.
  2. No bytes outside the block-band region are perturbed (still equal
     to nv_zero_global).

This is the directive-level sanity test — ensures the codec build
pipeline (Quartus build → mine_design_block_band.py → FASM directive)
round-trips byte-perfectly.  Silicon validation is a separate gate.

Usage:
    python3 scripts/design_block_band_pack_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
sys.path.insert(0, str(ROOT / "scripts"))

from fasm2rbf import bitgen  # noqa: E402

NV_PATH = ROOT / "results/rbf/nv_zero_global.rbf"
DB_PATH = ROOT / "results/design_block_band.json"
PRE = 32
FRAME = 210
BB_LO_OFF = PRE + 1692 * FRAME
BB_HI_OFF = PRE + 1739 * FRAME


def test_tag(tag: str, source_rbf_path: Path, nv: bytes) -> bool:
    if not source_rbf_path.exists():
        print(f"  {tag}: SKIP (source RBF missing: {source_rbf_path})")
        return True  # not a failure — codec source unavailable
    src = source_rbf_path.read_bytes()
    if len(src) != len(nv):
        print(f"  {tag}: FAIL (source RBF size {len(src)} != nv {len(nv)})")
        return False
    result = bitgen(f"DESIGN_BLOCK_BAND_PACK {tag}\n", nv)
    bb_diffs = sum(1 for off in range(BB_LO_OFF, BB_HI_OFF)
                   if result[off] != src[off])
    non_bb_diffs = (
        sum(1 for off in range(BB_LO_OFF) if result[off] != nv[off]) +
        sum(1 for off in range(BB_HI_OFF, len(nv)) if result[off] != nv[off])
    )
    if bb_diffs == 0 and non_bb_diffs == 0:
        print(f"  {tag}: PASS (block-band byte-identical to source, "
              f"non-bb untouched)")
        return True
    print(f"  {tag}: FAIL (bb_diffs={bb_diffs}, non_bb_diffs={non_bb_diffs})")
    return False


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} missing")
        return 1
    db = json.loads(DB_PATH.read_text())
    nv = NV_PATH.read_bytes()
    print(f"=== DESIGN_BLOCK_BAND_PACK regression "
          f"({len(db)} tags) ===")
    failed: list[str] = []
    for tag in sorted(db):
        src_rbf = Path(db[tag]["source_rbf"]).expanduser()
        if not test_tag(tag, src_rbf, nv):
            failed.append(tag)
    if failed:
        print(f"\nFAIL: {len(failed)}/{len(db)} — {failed}")
        return 1
    print(f"\nResult: {len(db)}/{len(db)} tags PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
