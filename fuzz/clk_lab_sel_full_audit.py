# SPDX-License-Identifier: GPL-3.0-or-later
"""Full cross-LAB structural audit of every mined LAB_CLK_SEL set.

Extends `clk_lab_sel_audit.py` from the 3-LAB snapshot to every
`results/clk_lab_sel_probe_X{x}Y{y}.json` that currently exists.

Answers questions raised by the 3-LAB audit:
  1. Does the (10,4) ∩ (22,10) = 17-cell overlap persist across the X=10
     column (same-X, same-Y slot but different LAB)?
  2. Is there a Y-band clustering (Y=10 at multiple X's sharing cells)?
  3. Does the near-zero overlap between (10,4) and (10,16) generalise
     — i.e. is the LAB_CLK_SEL per-LAB set largely Y-band specific?
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"
HDR = 32
FRAME = 210


def frame(off: int) -> int:
    return (off - HDR) // FRAME


def main():
    files = sorted(RESULTS.glob("clk_lab_sel_probe_X*Y*.json"))
    sets: dict[tuple[int, int], set] = {}
    for p in files:
        m = re.match(r"clk_lab_sel_probe_X(\d+)Y(\d+)\.json", p.name)
        if not m:
            continue
        x, y = int(m.group(1)), int(m.group(2))
        data = json.loads(p.read_text())
        sets[(x, y)] = set(tuple(c) for c in data["lab_clk_sel"])

    print(f"Loaded {len(sets)} LABs:")
    for (x, y), s in sorted(sets.items()):
        print(f"  LAB({x:2d},{y:2d}): {len(s):3d} cells")

    # Triple / quadruple intersection check
    all_isect = set.intersection(*sets.values()) if sets else set()
    print(f"\n∩ of all {len(sets)} LABs: {len(all_isect)} cells")

    # Cell-occurrence histogram — how many LABs does each cell appear in?
    cell_count: Counter = Counter()
    for s in sets.values():
        for c in s:
            cell_count[c] += 1

    hist = Counter(cell_count.values())
    print("\nCell-occurrence histogram (k = #LABs containing the cell):")
    for k in sorted(hist):
        print(f"  cells appearing in {k:2d}/{len(sets):2d} LABs: {hist[k]:3d}")

    # Group overlap by axes: same-X, same-Y, diff-both.
    keys = sorted(sets)
    same_x_avg = []
    same_y_avg = []
    diff_both_avg = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            inter = sets[a] & sets[b]
            if a[0] == b[0] and a[1] != b[1]:
                same_x_avg.append(len(inter))
            elif a[1] == b[1] and a[0] != b[0]:
                same_y_avg.append(len(inter))
            else:
                diff_both_avg.append(len(inter))

    def _stats(vals, label):
        if not vals:
            print(f"  {label:12s}: (no pairs)")
            return
        print(f"  {label:12s}: n={len(vals)}  "
              f"avg={sum(vals)/len(vals):5.1f}  "
              f"min={min(vals):3d}  max={max(vals):3d}")

    print(f"\nPairwise overlap statistics:")
    _stats(same_x_avg, "same-X")
    _stats(same_y_avg, "same-Y")
    _stats(diff_both_avg, "diff-both")

    # Check same-Y pairs specifically — is there a "Y-row" signature?
    print(f"\nSame-Y pair details:")
    by_y: dict[int, list] = {}
    for k in keys:
        by_y.setdefault(k[1], []).append(k)
    for y, labs in sorted(by_y.items()):
        if len(labs) < 2:
            continue
        print(f"  Y={y}: {labs}")
        for i in range(len(labs)):
            for j in range(i + 1, len(labs)):
                a, b = labs[i], labs[j]
                inter = sets[a] & sets[b]
                uni = sets[a] | sets[b]
                print(f"    LAB{a} ∩ LAB{b}: {len(inter):3d}  "
                      f"(union {len(uni):3d}, "
                      f"jaccard {len(inter)/len(uni):.2f})")

    # Conclusion heuristic
    print("\n=== Conclusion ===")
    if not all_isect:
        print("  No universal cell across all LABs — no shared LAB-enable bit.")
    if same_y_avg and diff_both_avg:
        if sum(same_y_avg) / len(same_y_avg) > \
           2 * (sum(diff_both_avg) / len(diff_both_avg)):
            print("  same-Y overlap dominates → Y-band is a structural axis")
        elif sum(same_y_avg) / len(same_y_avg) < \
             0.5 * (sum(diff_both_avg) / len(diff_both_avg)):
            print("  same-Y overlap SUPPRESSED → Y is not shared; "
                  "per-LAB mining mandatory")
        else:
            print("  same-Y vs diff-both overlap similar → no clean axis")


if __name__ == "__main__":
    main()
