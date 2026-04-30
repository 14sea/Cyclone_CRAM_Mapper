# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine the per-site `m9k_blink_diff_nv` bucket: cells where the
Quartus-built m9k_blink_full RBF differs from nv_zero_global, restricted
to the M9K block-band (frames 1692-1738, byte<208).

This is the post-2026-04-30 v5 finding methodology.  The inferred /
inferred_goldintersect / quartus_gold + --base nv pipelines were proven
mode-incorrect on silicon (see memory
m9k_mode_v5_finding_gi_codec_unnecessary_2026_04_30.md).  v5 silicon
test passed by keeping ONLY the 12 non-inferred Quartus block-band
cells per site — identically what this mining recipe captures.

Output: results/m9k_mode_bits.json — adds
`cells_by_template["m9k_blink_diff_nv"]` to each existing site entry
that has a corresponding m9k_blink_full RBF available.

The bucket is XOR-applied against nv_zero_global:
    site_block_band_state = nv_block_band_state XOR diff_nv_cells
After flash, M9K hardware reads the (w, d) mode encoded by these bits.

Usage:
    python3 scripts/m9k_blink_diff_nv_mine.py            # mine all available
    python3 scripts/m9k_blink_diff_nv_mine.py --dry-run  # preview only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NV = ROOT / "results/rbf/nv_zero_global.rbf"
MODE_BITS = ROOT / "results/m9k_mode_bits.json"

# Block-band geometry (per CLAUDE.md + memory phase5_nonlab_block_band.md)
PRE = 32
FRAME = 210
BLOCK_FRAME_LO = 1692
BLOCK_FRAME_HI = 1738
DATA_BYTES_PER_FRAME = 208  # exclude per-frame CRC bytes 208/209


def block_band_diff_cells(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """XOR diff restricted to block-band data bytes.

    Returns list of (offset, bit_position) tuples sorted by (offset, bp).
    """
    cells: list[tuple[int, int]] = []
    base = PRE + BLOCK_FRAME_LO * FRAME
    end = PRE + (BLOCK_FRAME_HI + 1) * FRAME
    for off in range(base, end):
        if a[off] == b[off]:
            continue
        # Skip per-frame CRC bytes
        if (off - PRE) % FRAME >= DATA_BYTES_PER_FRAME:
            continue
        x = a[off] ^ b[off]
        for bp in range(8):
            if x & (1 << bp):
                cells.append((off, bp))
    return cells


def find_blink_rbf(x: int, y: int, n: int) -> Path | None:
    # Primary: scripts/m9k_blink_full_build.py output
    p = ROOT / f"tmp/m9k_blink_full_X{x}_Y{y}_N{n}/m9k_blink_full_X{x}_Y{y}_N{n}.rbf"
    if p.exists():
        return p
    # X15_Y10_N0 special case: the v5-validated reference is m9k_blink_diag.
    if (x, y, n) == (15, 10, 0):
        p = ROOT / "tmp/m9k_blink_diag/m9k_blink_diag.rbf"
        if p.exists():
            return p
        # Alternative full-9x512 build
        p = ROOT / "tmp/m9k_blink_9x512_full/m9k_blink_9x512_full.rbf"
        if p.exists():
            return p
    return None


def parse_site_key(key: str) -> tuple[int, int, int, int, int] | None:
    """Parse 'X{x}_Y{y}_N{n}_{w}x{d}' into (x, y, n, w, d)."""
    try:
        head, geom = key.rsplit("_", 1)
        w_s, d_s = geom.split("x")
        parts = head.split("_")
        x = int(parts[0][1:])
        y = int(parts[1][1:])
        n = int(parts[2][1:])
        return (x, y, n, int(w_s), int(d_s))
    except (ValueError, IndexError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="don't write JSON")
    ap.add_argument("--width", type=int, default=9, help="filter by width")
    ap.add_argument("--depth", type=int, default=512, help="filter by depth")
    args = ap.parse_args()

    nv = NV.read_bytes()
    assert len(nv) == 368011, f"nv_zero_global wrong size: {len(nv)}"

    db = json.loads(MODE_BITS.read_text())

    mined: dict[str, int] = {}  # site_key -> cell count
    skipped: list[str] = []

    for key in sorted(db.keys()):
        parsed = parse_site_key(key)
        if not parsed:
            continue
        x, y, n, w, d = parsed
        if w != args.width or d != args.depth:
            continue
        rbf_path = find_blink_rbf(x, y, n)
        if rbf_path is None:
            skipped.append(key)
            continue
        rbf = rbf_path.read_bytes()
        if len(rbf) != 368011:
            print(f"  WARN: {rbf_path} wrong size {len(rbf)}, skipping")
            skipped.append(key)
            continue
        cells = block_band_diff_cells(rbf, nv)
        mined[key] = len(cells)
        if not args.dry_run:
            entry = db[key]
            entry.setdefault("cells_by_template", {})
            entry["cells_by_template"]["m9k_blink_diff_nv"] = [list(c) for c in cells]
            entry.setdefault("template_probe_source", {})
            entry["template_probe_source"]["m9k_blink_diff_nv"] = str(
                rbf_path.relative_to(ROOT)
            )

    print(f"Mined {len(mined)} sites:")
    for k, c in sorted(mined.items()):
        print(f"  {k}: {c} cells")
    if skipped:
        print(f"Skipped {len(skipped)} (no RBF available):")
        for k in skipped:
            print(f"  {k}")

    if mined and not args.dry_run:
        MODE_BITS.write_text(json.dumps(db, indent=2, sort_keys=True))
        print(f"\n[wrote] {MODE_BITS.relative_to(ROOT)}")
    elif args.dry_run:
        print("\n(dry-run; no changes written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
