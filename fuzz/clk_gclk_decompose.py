# SPDX-License-Identifier: GPL-3.0-or-later
"""Decompose results/clk_gclk_probe.json into:

  * spine — cells flipped for ALL sinks (the existing 16-intersection set)
  * per-sink LAB-CLK_SEL — cells flipped only for some sinks; group by sink

Cross-check the 16 intersection cells against the 17 cells in
``gclk_17_cells_mined.md`` to find the off-by-one (which cell is in the
old mining but NOT in the new probe, or vice versa).

Also reads each clkprobe_C_*.fit.rpt to confirm whether Quartus actually
promoted the clock to a global signal or kept it local — this is the
critical context for what these cells actually represent.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "results" / "clk_gclk_probe.json"
WORK = ROOT / "work"

# 17 cells from gclk_17_cells_mined.md
KNOWN_17 = {
    (11746, 4), (12167, 4), (13191, 4), (13401, 4), (13613, 4),
    (15292, 4), (15923, 4), (18001, 4), (18218, 2), (18869, 2),
    (19678, 4), (20099, 4), (247550, 2), (248189, 2),
    (363039, 2), (363459, 2), (363883, 2),
}


def main():
    data = json.loads(PROBE.read_text())
    per = {k: {tuple(c) for c in v}
           for k, v in data["per_site_cells"].items()}
    union = {tuple(c) for c in data["union"]}
    inter = {tuple(c) for c in data["intersection"]}

    print("== Cell counts ==")
    print(f"  union        : {len(union)}")
    print(f"  intersection : {len(inter)}")
    print()

    # Cross-check intersection vs the known 17-cell GCLK set
    only_in_known = KNOWN_17 - inter
    only_in_inter = inter - KNOWN_17
    common = KNOWN_17 & inter
    print("== Intersection vs gclk_17_cells_mined.md ==")
    print(f"  common              : {len(common)}/17")
    print(f"  only in known 17    : {sorted(only_in_known)}")
    print(f"  only in new probe   : {sorted(only_in_inter)}")
    print()

    # Per-sink decomposition — for each sink, what cells are unique to it
    print("== Per-sink unique cells (LAB CLK_SEL candidates) ==")
    for k in sorted(per):
        unique = per[k] - inter
        # Cells that appear in this sink but NOT in any OTHER sink
        others = set().union(*(per[k2] for k2 in per if k2 != k))
        sink_only = unique - others
        n_total = len(per[k])
        print(f"  sink {k:>10s}  total={n_total:3d}  "
              f"non-spine={len(unique):3d}  sink-unique={len(sink_only):3d}")

    # Co-occurrence: how many sinks does each non-spine cell appear in?
    print()
    print("== Co-occurrence of non-spine cells ==")
    cell_count = Counter()
    for cells in per.values():
        for c in cells:
            cell_count[c] += 1
    n_sinks = len(per)
    histo = Counter()
    for c, n in cell_count.items():
        if c not in inter:
            histo[n] += 1
    for n in sorted(histo):
        print(f"  in {n:2d}/{n_sinks} sinks: {histo[n]:4d} cells")

    # Read fit reports to confirm whether GCLK was used
    print()
    print("== Fit-report check: did Quartus use a global clock? ==")
    for k in sorted(per):
        sx, sy, sn = k.split(",")
        tag = f"clkprobe_C_X10Y10N0_to_X{sx}Y{sy}N{sn}_datab"
        rpt = WORK / tag / "output_files" / f"{tag}.fit.rpt"
        if not rpt.exists():
            print(f"  {k:>10s}: (no fit.rpt)")
            continue
        gclk_line = ""
        clkpin_line = ""
        text = rpt.read_text(errors="replace")
        for line in text.splitlines():
            if "Global clocks" in line and "/" in line and "%" in line:
                gclk_line = line.strip()
                break
        for line in text.splitlines():
            if "; CLK  ; PIN_" in line:
                clkpin_line = line.strip()
                break
        # Compress to fit terminal
        gclk_short = gclk_line.split(";")
        if len(gclk_short) > 2:
            gclk_short = gclk_short[2].strip()
        else:
            gclk_short = "?"
        clk_short = clkpin_line.split(";")
        clk_short = clk_short[2].strip() if len(clk_short) > 2 else "?"
        print(f"  {k:>10s}: GCLK={gclk_short}  pin={clk_short}")


if __name__ == "__main__":
    main()
