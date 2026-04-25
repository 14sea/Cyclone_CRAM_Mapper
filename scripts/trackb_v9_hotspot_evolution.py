# SPDX-License-Identifier: GPL-3.0-or-later
"""Track v9 hotspot (x=21, y=26) over all 46 iterations.

If the hotspot is persistent (same coord stays hot across iters), it's
a structural routing bottleneck — a specific net or LAB that the router
can't unstuck.  If it migrates, it's algorithmic / transient and a
router parameter tweak might help.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "tmp" / "trackb_probe"


def parse_grid(csv_path: Path):
    grid = []
    with csv_path.open() as f:
        for row in csv.reader(f):
            grid.append([int(c) if c else 0 for c in row if c != ""])
    return grid


def main():
    iters = sorted(int(p.stem.split("_")[-1])
                   for p in PROBE.glob("heatmap_v9_congestion_by_coordinate_*.csv"))
    # CSV axis convention (audit 2026-04-25): outer=X (grid_w=56),
    # inner=Y (grid_h≈26).  v9 hotspot is at X=26, Y=21 (NOT 21,26).
    HOT_X, HOT_Y = 26, 21
    print(f"Tracking hotspot (X={HOT_X}, Y={HOT_Y}) across {len(iters)} iters.")
    print(f"  CSV outer=X, inner=Y.  Top-1 reported as (X, Y).\n")
    print(f"{'iter':>4}  {'total':>6}  {'>0_cells':>8}  "
          f"{f'(X={HOT_X},Y={HOT_Y})':>10}  {'top1':>6}  {'top1_XY':>10}")
    persistent_top1 = []
    for it in iters:
        grid = parse_grid(PROBE / f"heatmap_v9_congestion_by_coordinate_{it}.csv")
        tot = sum(sum(r) for r in grid)
        nz = sum(1 for row in grid for v in row if v > 0)
        v_hot = grid[HOT_X][HOT_Y] if len(grid) > HOT_X and len(grid[HOT_X]) > HOT_Y else 0
        # Find top-1 hotspot — outer=X, inner=Y
        top = (0, -1, -1)
        for x, row in enumerate(grid):
            for y, v in enumerate(row):
                if v > top[0]:
                    top = (v, x, y)
        persistent_top1.append((top[1], top[2]))
        print(f"{it:>4}  {tot:>6}  {nz:>8}  {v_hot:>10}  "
              f"{top[0]:>6}  {f'({top[1]},{top[2]})':>10}")

    top1_at_hot = sum(1 for x, y in persistent_top1 if (x, y) == (HOT_X, HOT_Y))
    print(f"\n(X={HOT_X}, Y={HOT_Y}) was top-1 in {top1_at_hot}/{len(iters)} iters.")
    # Migration?
    from collections import Counter
    c = Counter(persistent_top1)
    print(f"\nTop-1 location frequency (across iters):")
    for (x, y), cnt in c.most_common(5):
        print(f"  ({x}, {y}): {cnt} iters")


if __name__ == "__main__":
    sys.exit(main() or 0)
