#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build arith_blockband_by_width.json from sweep data.

Per-width blob = block_band cells + arith-infra cells (the 7-8 non-block-band
cells that always appear — classified as 'lab_cram' by offset but actually
scattered infrastructure at frames 34/35/910/1686-7/1743).

Header cells (frames <25) are stripped as seed-noise.
"""
import json, os
from collections import Counter

D = json.load(open("/tmp/arith_sweep/cells_by_width.json"))

def is_noise(off):
    """Return True for header-band seed-noise cells (frames <25)."""
    if off < 32: return True
    rel = off - 32
    frame = rel // 210
    return frame < 25

def arith_cells(key):
    """Return (set_cells, clear_cells) lists, stripping header seed-noise."""
    r = D[key]
    sets = [[o, b] for (o, b) in r["set"] if not is_noise(o)]
    clears = [[o, b] for (o, b) in r["clear"] if not is_noise(o)]
    return sets, clears

table = {
    "version": 5,
    "source": "/tmp/arith_sweep — per-width sweep at LAB(4,18)",
    "method": "counter_w vs identity_w diff, header (frames<25) stripped as seed noise",
    "invariants": {
        "position_independent": "c{w}_lo and c{w}_up produce byte-identical cell sets at widths 2-8, so blob is N-slot-position-agnostic within the same LAB",
        "lab_independent": "triangle test 2026-04-14 verified w=8 blob byte-identical at LABs (4,18), (10,18), (4,10)"
    },
    "widths": {},
    "multi_lab": {},
}

# Single-LAB widths (half-LAB: use lo representative; cross-half: xh; full: c16)
for w in range(2, 9):
    s, c = arith_cells(f"c{w}_lo")
    table["widths"][str(w)] = {
        "topology": "half_lab",
        "set": s,
        "clear": c,
        "n_set": len(s),
        "n_clear": len(c),
    }

for w in range(9, 16):
    k = f"c{w}_xh"
    if k not in D:
        continue
    s, c = arith_cells(k)
    table["widths"][str(w)] = {
        "topology": "cross_half",
        "set": s,
        "clear": c,
        "n_set": len(s),
        "n_clear": len(c),
    }

if "c16" in D:
    s, c = arith_cells("c16")
    table["widths"]["16"] = {
        "topology": "full_lab",
        "set": s,
        "clear": c,
        "n_set": len(s),
        "n_clear": len(c),
    }

# Multi-LAB
if "c24" in D:
    s, c = arith_cells("c24")
    table["multi_lab"]["16+8"] = {
        "topology": "full_lab_plus_half_lab_down",
        "description": "LAB(4,18) full-LAB carry + LAB(4,17) 8-bit half-LAB carry, N=30→N=0 inter-LAB link",
        "set": s,
        "clear": c,
        "n_set": len(s),
        "n_clear": len(c),
    }

with open("/tmp/arith_sweep/arith_blockband_by_width.json", "w") as f:
    json.dump(table, f)
print(f"Wrote arith_blockband_by_width.json with widths: {sorted(table['widths'].keys(), key=int)}")
print(f"Multi-LAB entries: {list(table['multi_lab'].keys())}")
print()
print("Summary table:")
print(f"{'w':>3} {'topology':>14} {'set':>5} {'clear':>6}")
for w, v in sorted(table["widths"].items(), key=lambda kv: int(kv[0])):
    print(f"{w:>3} {v['topology']:>14} {v['n_set']:>5} {v['n_clear']:>6}")
for k, v in table["multi_lab"].items():
    print(f"{k:>3} {v['topology']:>14} {v['n_set']:>5} {v['n_clear']:>6}")
