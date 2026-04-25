# SPDX-License-Identifier: GPL-3.0-or-later
"""Track B Phase 5 v9 heatmap audit — spatial congestion analysis.

Reads tmp/trackb_probe/heatmap_v9_congestion_by_coordinate_<iter>.csv
(grid X=col, Y=row, cell value = number of overused wires in that LAB
coordinate) and identifies geographic hotspots at best/final iters.

Goal: see if congestion is uniformly distributed (true capacity-bound)
or concentrated at specific LABs (suggests targeted fix possible).
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "tmp" / "trackb_probe"


def parse_grid(csv_path: Path) -> list[list[int]]:
    grid = []
    with csv_path.open() as f:
        reader = csv.reader(f)
        for row in reader:
            grid.append([int(c) if c else 0 for c in row if c != ""])
    return grid


def total(grid):
    return sum(sum(r) for r in grid)


def hotspots(grid, top_n=20):
    cells = []
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if v > 0:
                cells.append((v, x, y))
    cells.sort(reverse=True)
    return cells[:top_n]


def histogram(grid):
    from collections import Counter
    c = Counter()
    for row in grid:
        for v in row:
            if v > 0:
                c[v] += 1
    return c


def main():
    iters = sorted(int(p.stem.split("_")[-1])
                   for p in PROBE.glob("heatmap_v9_congestion_by_coordinate_*.csv"))
    print(f"v9 has {len(iters)} per-iter coord heatmaps: iter {iters[0]}..{iters[-1]}")

    targets = []
    if 11 in iters: targets.append(("BEST (iter 11)", 11))
    if iters: targets.append((f"FINAL (iter {iters[-1]})", iters[-1]))

    for label, it in targets:
        print(f"\n=== {label} ===")
        grid = parse_grid(PROBE / f"heatmap_v9_congestion_by_coordinate_{it}.csv")
        tot = total(grid)
        rows, cols = len(grid), len(grid[0]) if grid else 0
        print(f"Grid {rows}×{cols}, total overuse units = {tot}")
        non_zero = sum(1 for row in grid for v in row if v > 0)
        if non_zero:
            print(f"Non-zero cells: {non_zero} ({non_zero / (rows*cols) * 100:.1f}%)")
        # Top hotspots
        print("Top hotspots (overuse, x, y):")
        for v, x, y in hotspots(grid, top_n=15):
            print(f"  {v:4}  x={x:2}  y={y:2}")
        # Histogram of cell values
        h = histogram(grid)
        print("Histogram of overuse-per-cell:")
        for k in sorted(h, reverse=True)[:10]:
            print(f"  {k}: {h[k]} cells")
        # Concentration metric: top 10% hotspots vs total
        top = hotspots(grid, top_n=max(1, non_zero // 10))
        top_total = sum(v for v, _, _ in top)
        if tot > 0:
            print(f"Top-10% hotspots account for {top_total}/{tot} = "
                  f"{top_total/tot*100:.1f}% of total overuse")


if __name__ == "__main__":
    sys.exit(main() or 0)
