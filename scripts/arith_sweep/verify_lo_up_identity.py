#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify c{w}_lo and c{w}_up cells are literally identical (not just same count)."""
import json

D = json.load(open("tmp/arith_sweep/cells_by_width.json"))

for w in [2, 4, 8]:
    lo = D[f"c{w}_lo"]
    up = D[f"c{w}_up"]
    set_lo = set(tuple(x) for x in lo["set"])
    set_up = set(tuple(x) for x in up["set"])
    clear_lo = set(tuple(x) for x in lo["clear"])
    clear_up = set(tuple(x) for x in up["clear"])
    print(f"w={w}:")
    print(f"  set diff: lo-up={len(set_lo - set_up)}, up-lo={len(set_up - set_lo)}")
    print(f"  clear diff: lo-up={len(clear_lo - clear_up)}, up-lo={len(clear_up - clear_lo)}")
    # By region
    def reg(off):
        if off < 32: return "pre"
        rel = off - 32
        fr = rel // 210
        if fr < 25: return "hdr"
        if 1692 <= fr <= 1738: return "blk"
        return "lab"
    lo_only_set = set_lo - set_up
    if lo_only_set:
        print(f"  lo_only_set sample: {sorted(lo_only_set)[:5]}")
        from collections import Counter
        print(f"  lo_only_set by region: {Counter(reg(o) for (o,b) in lo_only_set)}")
