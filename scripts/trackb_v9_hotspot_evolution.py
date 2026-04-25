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
    print(f"Tracking hotspot (x=21, y=26) across {len(iters)} iters.")
    print(f"  Also tracking iter total + #cells > 0 + top-1 hotspot.\n")
    print(f"{'iter':>4}  {'total':>6}  {'>0_cells':>8}  "
          f"{'(21,26)':>8}  {'top1':>6}  {'top1_xy':>10}")
    persistent_top1 = []
    for it in iters:
        grid = parse_grid(PROBE / f"heatmap_v9_congestion_by_coordinate_{it}.csv")
        tot = sum(sum(r) for r in grid)
        nz = sum(1 for row in grid for v in row if v > 0)
        # Get value at (21, 26) — note CSV row=Y, col=X
        v_2126 = grid[26][21] if len(grid) > 26 and len(grid[26]) > 21 else 0
        # Find top-1 hotspot
        top = (0, -1, -1)
        for y, row in enumerate(grid):
            for x, v in enumerate(row):
                if v > top[0]:
                    top = (v, x, y)
        persistent_top1.append((top[1], top[2]))
        print(f"{it:>4}  {tot:>6}  {nz:>8}  {v_2126:>8}  "
              f"{top[0]:>6}  {f'({top[1]},{top[2]})':>10}")

    # How many iters did (21, 26) remain top-1?
    top1_at_2126 = sum(1 for x, y in persistent_top1 if (x, y) == (21, 26))
    print(f"\n(21, 26) was top-1 in {top1_at_2126}/{len(iters)} iters.")
    # Migration?
    from collections import Counter
    c = Counter(persistent_top1)
    print(f"\nTop-1 location frequency (across iters):")
    for (x, y), cnt in c.most_common(5):
        print(f"  ({x}, {y}): {cnt} iters")


if __name__ == "__main__":
    sys.exit(main() or 0)
