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


def find_blink_rbf(x: int, y: int, n: int,
                   width: int = 9, depth: int = 512,
                   mode: str | None = None) -> Path | None:
    """Locate the Quartus reference RBF for a (mode, w, d, site) tuple.

    Search order:
      1. Per-mode parameterized build dir
         (tmp/m9k_blink_<mode>_<w>x<d>_X{x}_Y{y}_N{n}/...)
      2. Legacy SP 9×512 fixed-name build dir (mode=sp w=9 d=512 only)
      3. X15_Y10_N0 9×512 well-known references
    """
    candidates: list[Path] = []
    if mode is not None:
        candidates.append(
            ROOT
            / f"tmp/m9k_blink_{mode}_{width}x{depth}_X{x}_Y{y}_N{n}"
            / f"m9k_blink_{mode}_{width}x{depth}_X{x}_Y{y}_N{n}.rbf"
        )
    else:
        # Try every known mode in a deterministic order so the answer is
        # repeatable when more than one mode happens to be present.
        for m in ("sp", "sdp", "tdp", "rom"):
            candidates.append(
                ROOT
                / f"tmp/m9k_blink_{m}_{width}x{depth}_X{x}_Y{y}_N{n}"
                / f"m9k_blink_{m}_{width}x{depth}_X{x}_Y{y}_N{n}.rbf"
            )
    if (width, depth) == (9, 512):
        # Legacy fixed-name path for the SP 9x512 case.
        candidates.append(
            ROOT
            / f"tmp/m9k_blink_full_X{x}_Y{y}_N{n}"
            / f"m9k_blink_full_X{x}_Y{y}_N{n}.rbf"
        )
        if (x, y, n) == (15, 10, 0):
            candidates.append(ROOT / "tmp/m9k_blink_diag/m9k_blink_diag.rbf")
            candidates.append(ROOT / "tmp/m9k_blink_9x512_full/m9k_blink_9x512_full.rbf")
    for p in candidates:
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
    ap.add_argument("--mode", default=None,
                    help="restrict to a single Quartus build mode "
                         "(sp/sdp/tdp/rom); default = first match")
    ap.add_argument("--sites", default=None,
                    help="optional comma/semicolon-separated X,Y filter, "
                         "e.g. '15,10' or '15,4;15,10'")
    ap.add_argument("--add-missing", action="store_true",
                    help="create JSON entries for (x,y,n,w,d) tuples that "
                         "have an RBF on disk but no key in m9k_mode_bits.json")
    args = ap.parse_args()

    nv = NV.read_bytes()
    assert len(nv) == 368011, f"nv_zero_global wrong size: {len(nv)}"

    db = json.loads(MODE_BITS.read_text())

    site_filter: set[tuple[int, int]] | None = None
    if args.sites:
        site_filter = set()
        for chunk in args.sites.split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            x_s, y_s = chunk.split(",")
            site_filter.add((int(x_s), int(y_s)))

    mined: dict[str, int] = {}  # site_key -> cell count
    skipped: list[str] = []

    keys_to_check = list(db.keys())
    if args.add_missing:
        # Augment with any (x, y, n, w, d) inferred from RBFs on disk.
        import re
        pat = re.compile(r"^m9k_blink_(?P<mode>sp|sdp|tdp|rom)_"
                         r"(?P<w>\d+)x(?P<d>\d+)_"
                         r"X(?P<x>\d+)_Y(?P<y>\d+)_N(?P<n>\d+)$")
        for d in (ROOT / "tmp").glob("m9k_blink_*"):
            if not d.is_dir():
                continue
            m = pat.match(d.name)
            if not m:
                continue
            w_d, d_d = int(m["w"]), int(m["d"])
            if w_d != args.width or d_d != args.depth:
                continue
            x_d, y_d, n_d = int(m["x"]), int(m["y"]), int(m["n"])
            key = f"X{x_d}_Y{y_d}_N{n_d}_{w_d}x{d_d}"
            if key not in db:
                db[key] = {
                    "cells_by_template": {},
                    "template_probe_source": {},
                    "_origin": "m9k_blink_diff_nv_mine.py --add-missing",
                }
                keys_to_check.append(key)

    for key in sorted(set(keys_to_check)):
        parsed = parse_site_key(key)
        if not parsed:
            continue
        x, y, n, w, d = parsed
        if w != args.width or d != args.depth:
            continue
        if site_filter is not None and (x, y) not in site_filter:
            continue
        rbf_path = find_blink_rbf(x, y, n, width=w, depth=d, mode=args.mode)
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
