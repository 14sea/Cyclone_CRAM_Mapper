#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""What are the 8 lab_cram cells per c{w}? Same positions between lo and up?"""
import json

D = json.load(open("tmp/arith_sweep/cells_by_width.json"))

def reg(off):
    if off < 32: return "pre"
    rel = off - 32
    fr = rel // 210
    if fr < 25: return "hdr"
    if 1692 <= fr <= 1738: return "blk"
    return "lab"

for w in [2, 8]:
    print(f"\n=== w={w} ===")
    for half in ["lo", "up"]:
        cells = D[f"c{w}_{half}"]
        all_cells = [tuple(x) for x in cells["set"]] + [tuple(x) for x in cells["clear"]]
        lab_cells = sorted((o, b) for (o, b) in all_cells if reg(o) == "lab")
        print(f"  {half} lab_cram ({len(lab_cells)} cells):")
        for (o, b) in lab_cells:
            rel = o - 32
            frame = rel // 210
            byte_in_frame = rel % 210
            print(f"    off={o:>6} bp={b} frame={frame} byte={byte_in_frame}")
