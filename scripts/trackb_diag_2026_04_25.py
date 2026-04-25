# SPDX-License-Identifier: GPL-3.0-or-later
"""Track B re-diagnostic — NEORV32 nextpnr router2 against canonical chipdb.

Parses tmp/trackb_diag_2026_04_25/run.log for iter-by-iter overused
evolution + reads heatmap-by-wiretype CSV at best/worst/final iters
to identify which wire class dominates congestion.  Compares against
Phase 5 v9 (48-track) baseline: best=432 overused at iter 11.
"""
from __future__ import annotations
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAG = ROOT / "tmp" / "trackb_diag_2026_04_25"


def parse_iters(log_path: Path) -> list[dict]:
    iters = []
    pat = re.compile(r"iter=(\d+)\s+wires=(\d+)\s+overused=(\d+)\s+overuse=(\d+)")
    for line in log_path.read_text(errors="replace").splitlines():
        m = pat.search(line)
        if m:
            iters.append({
                "iter": int(m.group(1)),
                "wires": int(m.group(2)),
                "overused": int(m.group(3)),
                "overuse": int(m.group(4)),
            })
    return iters


def parse_wiretype_heatmap(csv_path: Path, capacity: int = 1) -> list[tuple[str, int]]:
    """Return list of (wiretype, overuse_count).

    Overuse = sum of bound > capacity counts.
    """
    if not csv_path.exists():
        return []
    rows = []
    with csv_path.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        # bound=N column index for N > capacity
        ovuse_cols = []
        for i, h in enumerate(header):
            if h.startswith("bound="):
                n = int(h.split("=")[1])
                if n > capacity:
                    ovuse_cols.append(i)
        for row in reader:
            if not row or not row[0]:
                continue
            ov = sum(int(row[i]) for i in ovuse_cols if i < len(row) and row[i])
            rows.append((row[0], ov))
    return rows


def main():
    log = DIAG / "run.log"
    if not log.exists():
        print(f"No log at {log}")
        return 1

    iters = parse_iters(log)
    if not iters:
        print("No iter records in log.  Last 30 lines:")
        for line in log.read_text(errors="replace").splitlines()[-30:]:
            print(f"  {line}")
        return 1

    print(f"Parsed {len(iters)} router2 iterations.")
    best = min(iters, key=lambda r: r["overused"])
    worst = max(iters, key=lambda r: r["overused"])
    final = iters[-1]
    print(f"  iter 1     : overused={iters[0]['overused']:>5}")
    print(f"  iter best  : iter={best['iter']:>3}  overused={best['overused']:>5}")
    print(f"  iter worst : iter={worst['iter']:>3}  overused={worst['overused']:>5}")
    print(f"  iter final : iter={final['iter']:>3}  overused={final['overused']:>5}")
    print()
    print(f"Phase 5 v9 (48-track) baseline: best=432 at iter 11; oscillates 432→635 by iter 46.")

    # Detect oscillation: standard deviation over last N iters
    if len(iters) > 10:
        last10 = iters[-10:]
        ovs = [r["overused"] for r in last10]
        spread = max(ovs) - min(ovs)
        print(f"\nLast-10-iter overused range: {min(ovs)} → {max(ovs)} (spread={spread})")
        if spread > 50:
            print("  → OSCILLATION confirmed (consistent with Phase 5 capacity-bound regime)")
        else:
            print("  → STABLE plateau")

    # Heatmap analysis: best iter
    print()
    best_csv = DIAG / f"heat_congestion_by_wiretype_{best['iter'] + 1}.csv"
    if best_csv.exists():
        print(f"Wire-type congestion at best iter ({best['iter']}):")
        rows = parse_wiretype_heatmap(best_csv, capacity=1)
        rows.sort(key=lambda r: -r[1])
        for wt, ov in rows[:15]:
            if ov > 0:
                print(f"  {wt:20s}  overused={ov}")
    else:
        # Try all heatmaps
        all_csv = sorted(DIAG.glob("heat_congestion_by_wiretype_*.csv"))
        if all_csv:
            print(f"Best-iter heatmap missing; using last available {all_csv[-1].name}")
            rows = parse_wiretype_heatmap(all_csv[-1], capacity=1)
            rows.sort(key=lambda r: -r[1])
            for wt, ov in rows[:15]:
                if ov > 0:
                    print(f"  {wt:20s}  overused={ov}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
