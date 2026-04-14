# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-LAB structural audit of LAB_CLK_SEL cell sets.

Asks: is there a per-LAB formula (shared cells + LAB-X-offset + LAB-Y-offset)
that would let us extrapolate LAB_CLK_SEL without mining every LAB?

Given 3 mined LABs:
  (10,  4): 26 cells
  (10, 16): 53 cells
  (22, 10): 45 cells

Audit outputs: triple ∩, pairwise ∩, LAB-unique sets, byte-position
distribution per bucket.
"""
from __future__ import annotations

import json
from pathlib import Path

HDR = 32
FRAME = 210

REPO = Path(__file__).resolve().parent.parent
LABS = [(10, 4), (10, 16), (22, 10)]


def frame(off: int) -> int:
    return (off - HDR) // FRAME


def rel(off: int) -> int:
    return (off - HDR) % FRAME


def main():
    sets: dict[tuple, set] = {}
    for x, y in LABS:
        p = REPO / "results" / f"clk_lab_sel_probe_X{x}Y{y}.json"
        data = json.loads(p.read_text())
        sets[(x, y)] = set(tuple(c) for c in data["lab_clk_sel"])
        print(f"LAB({x:2d}, {y:2d}): {len(sets[(x,y)]):3d} cells")

    vals = list(sets.values())
    triple = vals[0] & vals[1] & vals[2]
    print(f"\ntriple ∩ (universal LAB enable?): {len(triple)} cells")

    keys = list(sets)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            inter = sets[a] & sets[b]
            ya, yb = a[1], b[1]
            xa, xb = a[0], b[0]
            note = []
            if xa == xb: note.append("same-X")
            if ya == yb: note.append("same-Y")
            if not note: note.append("diff-both")
            print(f"  LAB{a} ∩ LAB{b}: {len(inter):3d}  ({' '.join(note)})")

    # LAB-unique cells — are they clustered in predictable frame ranges?
    print("\nLAB-unique cells:")
    for k, cells in sets.items():
        others: set = set()
        for k2, v2 in sets.items():
            if k != k2:
                others |= v2
        uniq = cells - others
        frames = sorted(set(frame(o) for o, _ in uniq))
        # simple clustering: contiguous runs
        runs = []
        if frames:
            run = [frames[0]]
            for f in frames[1:]:
                if f - run[-1] <= 3:
                    run.append(f)
                else:
                    runs.append((run[0], run[-1], len(run)))
                    run = [f]
            runs.append((run[0], run[-1], len(run)))
        print(f"  LAB{k}: {len(uniq)} cells across {len(runs)} frame clusters")
        for lo, hi, n in runs:
            print(f"    frames {lo}..{hi}  ({n} distinct)")

    # Final conclusion
    print("\n=== Conclusion ===")
    if len(triple) == 0:
        print("  No universal LAB CLK_SEL activate cells.")
    same_x_overlap = sets[(10, 4)] & sets[(10, 16)]
    diff_both_overlap = sets[(10, 4)] & sets[(22, 10)]
    if len(same_x_overlap) < len(diff_both_overlap):
        print(f"  Same-X overlap ({len(same_x_overlap)}) < diff-both overlap "
              f"({len(diff_both_overlap)}) — LAB column is NOT the "
              f"dominant shared-cell axis.")
    print("  Per-LAB mining is required for every LAB — no extrapolation.")


if __name__ == "__main__":
    main()
