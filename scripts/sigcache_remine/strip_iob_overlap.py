#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Post-process cross-LAB sigcache entries: strip IOB+CLK overlap.

Background — memory `gamma_silicon_validation_codec_bug_2026_05_10`:
Plan D' factory mining (`gen_two_luts_single_input_clocked` + FUZZ_PINS)
bakes IOB pad and clock-LE infrastructure cells into every cross-LAB R4
sigcache entry.  In open-toolchain builds those same cells are emitted
SEPARATELY by `IOB_PAD_NV`, `LAB_CLK_SEL`, and `LAB_CLK_SEL_LE` →
double XOR-flip cancels each overlapping cell → final RBF missing the
sigcache cells that overlapped the per-directive sets.

For entry `4,4,0->4,21,0,dataa`: 141 sigcache cells, 63 overlapped
(56 IOB_PAD_NV + 7 LAB_CLK_SEL_LE X4Y21N0) and got cancelled in the
end-to-end test build → silicon would fail.

Fix: strip per-entry overlap with IOB_PAD_NV ∪ LAB_CLK_SEL_LE(src,sn) ∪
LAB_CLK_SEL_LE(dst,dn) ∪ LAB_CLK_SEL(src) ∪ LAB_CLK_SEL(dst) from each
affected cross-LAB entry.  The runtime IOB_PAD_NV + LAB_CLK_SEL_LE +
LAB_CLK_SEL directives then own those cells; ROUTE owns only what's left.

Scope: by default only entries where overlap ≥ 30 (the natural bimodal
threshold separating Plan D' factory "big" entries from C4-direct
"small" entries) and cross-LAB (sx,sy) != (dx,dy) are touched.  Use
`--column X` to limit further.  Both `nv_route_cells.json` (canonical
Plan D' source) and `route_cells_full.json` (live sigcache) are
patched in lockstep.

Usage:
  # Dry-run audit (default):
  python3 scripts/sigcache_remine/strip_iob_overlap.py
  # Apply to X=4 cross-LAB entries (sane default scope for the bug):
  python3 scripts/sigcache_remine/strip_iob_overlap.py --apply --column 4
  # Apply to ALL cross-LAB columns with the overlap threshold:
  python3 scripts/sigcache_remine/strip_iob_overlap.py --apply --all-columns
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from fuzz.fasm2rbf import (  # noqa: E402
    _load_lab_clk_sel_cells,
    _load_lab_clk_sel_le_cells,
)

NV_ROUTE_CELLS = REPO / "results" / "nv_route_cells.json"
ROUTE_CELLS_FULL = REPO / "results" / "route_cells_full.json"
IOB_PAD_NV_PATH = REPO / "results" / "output_route_nv_mining.json"

KEY_RE = re.compile(r"^(\d+),(\d+),(\d+)->(\d+),(\d+),(\d+),(\w+)$")

OVERLAP_THRESHOLD = 30  # bimodal threshold; "small" entries cap around 19


def load_iob_pad_nv() -> set[tuple[int, int]]:
    data = json.loads(IOB_PAD_NV_PATH.read_text())
    return {tuple(c) for c in data["iob_pad_cells"]}


_clk_le_cache: dict[tuple[int, int, int], set[tuple[int, int]]] = {}
_clk_lab_cache: dict[tuple[int, int], set[tuple[int, int]]] = {}


def clk_le_cells(x: int, y: int, n: int) -> set[tuple[int, int]]:
    k = (x, y, n)
    if k not in _clk_le_cache:
        # X=33 entries are mining garbage; fasm2rbf prints a WARN that
        # we don't want to spam during the audit walk.
        if x == 33:
            _clk_le_cache[k] = set()
            return _clk_le_cache[k]
        try:
            cells = _load_lab_clk_sel_le_cells(x, y, n, lenient=True)
        except Exception:
            cells = []
        _clk_le_cache[k] = {tuple(c) for c in cells}
    return _clk_le_cache[k]


def clk_lab_cells(x: int, y: int) -> set[tuple[int, int]]:
    k = (x, y)
    if k not in _clk_lab_cache:
        try:
            cells = _load_lab_clk_sel_cells(x, y, lenient=True)
        except Exception:
            cells = []
        _clk_lab_cache[k] = {tuple(c) for c in cells}
    return _clk_lab_cache[k]


def strip_set_for(sx: int, sy: int, sn: int, dx: int, dy: int, dn: int,
                  iob_pad_nv: set[tuple[int, int]]) -> set[tuple[int, int]]:
    return (
        iob_pad_nv
        | clk_le_cells(sx, sy, sn)
        | clk_le_cells(dx, dy, dn)
        | clk_lab_cells(sx, sy)
        | clk_lab_cells(dx, dy)
    )


def write_atomic(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write modified sigcache (default: dry-run audit)")
    ap.add_argument("--column", type=int, default=None,
                    help="restrict to entries where both sx and dx equal X")
    ap.add_argument("--all-columns", action="store_true",
                    help="process every cross-LAB entry that meets the threshold "
                         "(default: require --column)")
    ap.add_argument("--threshold", type=int, default=OVERLAP_THRESHOLD,
                    help=f"min overlap cells to strip an entry (default {OVERLAP_THRESHOLD})")
    args = ap.parse_args()

    if not args.column and not args.all_columns and args.apply:
        ap.error("with --apply, pass either --column X or --all-columns")

    iob_pad_nv = load_iob_pad_nv()
    print(f"IOB_PAD_NV cells: {len(iob_pad_nv)}")

    nv_sigs = json.loads(NV_ROUTE_CELLS.read_text()) if NV_ROUTE_CELLS.exists() else {}
    sigcache = json.loads(ROUTE_CELLS_FULL.read_text())
    print(f"nv_route_cells.json: {len(nv_sigs)} entries")
    print(f"route_cells_full.json: {len(sigcache)} entries")

    candidates: list[tuple[str, int, int, int, int, int, int, int, int]] = []
    # (key, sx, sy, sn, dx, dy, dn, cell_count, overlap_count)
    for key, cells in sigcache.items():
        m = KEY_RE.match(key)
        if not m:
            continue
        sx, sy, sn, dx, dy, dn, _port = (int(v) if v.isdigit() else v
                                         for v in m.groups())
        if (sx, sy) == (dx, dy):
            continue  # not cross-LAB
        if args.column is not None:
            if sx != args.column or dx != args.column:
                continue
        elif not args.all_columns:
            # Audit-only default: include all cross-LAB for the summary
            pass
        entry = {tuple(c) for c in cells}
        strip = strip_set_for(sx, sy, sn, dx, dy, dn, iob_pad_nv)
        overlap = entry & strip
        candidates.append((key, sx, sy, sn, dx, dy, dn, len(entry), len(overlap)))

    big = [c for c in candidates if c[8] >= args.threshold]
    small = [c for c in candidates if c[8] < args.threshold]
    print()
    print(f"Cross-LAB entries surveyed: {len(candidates)}")
    print(f"  to strip (overlap >= {args.threshold}): {len(big)}")
    print(f"  skipped (overlap < {args.threshold}): {len(small)}")

    # Per-column breakdown
    from collections import Counter
    big_by_col = Counter((c[1], c[4]) for c in big)
    print()
    print("To-strip count by (src_col, dst_col):")
    for (sxk, dxk), n in sorted(big_by_col.items()):
        print(f"  X{sxk} -> X{dxk}: {n}")

    if not big:
        print("No entries match strip criteria.  Done.")
        return

    if not args.apply:
        print()
        print("Dry-run.  Top 5 entries by overlap:")
        for c in sorted(big, key=lambda r: -r[8])[:5]:
            key, sx, sy, sn, dx, dy, dn, n, ov = c
            print(f"  {key}: {n} cells, overlap {ov}, post-strip {n - ov}")
        print()
        print("Re-run with --apply --column X (or --all-columns) to write.")
        return

    # Backup
    ts = time.strftime("%Y%m%d_%H%M%S")
    for path in (NV_ROUTE_CELLS, ROUTE_CELLS_FULL):
        if path.exists():
            bak = path.with_suffix(path.suffix + f".bak.{ts}")
            shutil.copy2(path, bak)
            print(f"  backup: {path.name} -> {bak.name}")

    # Apply strip
    n_modified = 0
    n_cells_removed = 0
    for key, sx, sy, sn, dx, dy, dn, n_cells, n_overlap in big:
        strip = strip_set_for(sx, sy, sn, dx, dy, dn, iob_pad_nv)
        new_cells = sorted(
            (o, b) for (o, b) in (tuple(c) for c in sigcache[key])
            if (o, b) not in strip
        )
        removed = n_cells - len(new_cells)
        n_cells_removed += removed
        sigcache[key] = [list(c) for c in new_cells]
        if key in nv_sigs:
            nv_sigs[key] = [list(c) for c in new_cells]
        n_modified += 1

    print()
    print(f"Modified {n_modified} entries; removed {n_cells_removed} cells total.")

    write_atomic(ROUTE_CELLS_FULL, sigcache)
    print(f"  wrote {ROUTE_CELLS_FULL.relative_to(REPO)}")
    if nv_sigs:
        write_atomic(NV_ROUTE_CELLS, nv_sigs)
        print(f"  wrote {NV_ROUTE_CELLS.relative_to(REPO)}")


if __name__ == "__main__":
    main()
