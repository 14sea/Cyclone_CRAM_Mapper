#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural analysis: how do arith cells grow with N-slot additions?

Key questions:
 1. Is c{w}_lo cellset a SUBSET of c{w+1}_lo cellset? (monotone growth)
 2. Does c8_lo ∪ c8_up = c16 cellset? (lower+upper union hypothesis)
 3. Are c{w}_lo and c{w}_up related by a fixed offset mapping? (half-LAB symmetry at cell level)
 4. Spatial distribution: block_band cells clustered or dispersed?
"""
import json, collections

D = json.load(open("/tmp/arith_sweep/cells_by_width.json"))

def cells(key, kind=None):
    """Return set of (off, bp) cells. kind in {None, 'set', 'clear', 'block_band_only'}"""
    r = D[key]
    if kind == "set":
        return set(tuple(x) for x in r["set"])
    if kind == "clear":
        return set(tuple(x) for x in r["clear"])
    all_cells = set(tuple(x) for x in r["set"]) | set(tuple(x) for x in r["clear"])
    if kind == "block_band_only":
        # block band = frames 1692-1738
        PRE = 32; FS = 210
        return {(o,b) for (o,b) in all_cells
                if PRE <= o and 1692 <= (o-PRE)//FS <= 1738}
    return all_cells

def region(off):
    PRE = 32; FS = 210
    if off < PRE: return "preamble"
    rel = off - PRE
    frame = rel // FS
    if frame < 25: return "header"
    if 1692 <= frame <= 1738: return "block_band"
    return "lab_cram"

# ---------- Q1: monotone growth in lower half ----------
print("=" * 70)
print("Q1: Monotone growth (lower half, block_band only)")
print("=" * 70)
print(f"{'w':>3} {'|S|':>5} {'+new':>6} {'-lost':>6} {'stable':>7}  (vs w-1)")
prev = set()
for w in range(2, 9):
    s = cells(f"c{w}_lo", "block_band_only")
    new = s - prev
    lost = prev - s
    stable = s & prev
    print(f"{w:>3} {len(s):>5} {len(new):>6} {len(lost):>6} {len(stable):>7}")
    prev = s

print()
print("=" * 70)
print("Q1b: Monotone growth (upper half)")
print("=" * 70)
prev = set()
for w in range(2, 9):
    s = cells(f"c{w}_up", "block_band_only")
    new = s - prev
    lost = prev - s
    stable = s & prev
    print(f"{w:>3} {len(s):>5} {len(new):>6} {len(lost):>6} {len(stable):>7}")
    prev = s

# ---------- Q2: lower ∪ upper vs full ----------
print()
print("=" * 70)
print("Q2: c8_lo ∪ c8_up vs c16 (block_band only)")
print("=" * 70)
lo8 = cells("c8_lo", "block_band_only")
up8 = cells("c8_up", "block_band_only")
full16 = cells("c16", "block_band_only")
union = lo8 | up8
inter = lo8 & up8
print(f"|c8_lo|       = {len(lo8)}")
print(f"|c8_up|       = {len(up8)}")
print(f"|lo ∩ up|     = {len(inter)}")
print(f"|lo ∪ up|     = {len(union)}")
print(f"|c16|         = {len(full16)}")
print(f"|union ∩ c16| = {len(union & full16)}")
print(f"|union \\ c16| = {len(union - full16)}  (in lo/up but not in 16)")
print(f"|c16 \\ union| = {len(full16 - union)}  (in 16 but not in lo or up — combo-specific)")

# Classify combo-specific cells
print()
print("Combo-specific cells (in c16 but neither c8_lo nor c8_up):")
combo_specific = full16 - union
by_frame = collections.Counter()
for (o, b) in combo_specific:
    frame = (o - 32) // 210 if o >= 32 else -1
    by_frame[frame] += 1
for f, cnt in sorted(by_frame.items())[:20]:
    print(f"  frame {f:>4}: {cnt} cells")
print(f"  total frames used: {len(by_frame)}")

# ---------- Q3: lo/up symmetry at cell level ----------
print()
print("=" * 70)
print("Q3: half-LAB symmetry — are lo/up cells related by fixed offset?")
print("=" * 70)
for w in [2, 4, 6, 8]:
    lo = cells(f"c{w}_lo", "block_band_only")
    up = cells(f"c{w}_up", "block_band_only")
    shared = lo & up
    lo_only = lo - up
    up_only = up - lo
    print(f"w={w}: |lo|={len(lo)} |up|={len(up)} shared={len(shared)} lo_only={len(lo_only)} up_only={len(up_only)}")

# ---------- Q4: spatial distribution ----------
print()
print("=" * 70)
print("Q4: block-band spatial distribution (c16 all cells)")
print("=" * 70)
all16 = cells("c16", "block_band_only")
by_frame = collections.Counter()
for (o, b) in all16:
    frame = (o - 32) // 210 if o >= 32 else -1
    by_frame[frame] += 1
for f in sorted(by_frame.keys()):
    print(f"  frame {f:>4}: {by_frame[f]} cells")

# ---------- Q5: c24 vs c16 + c8_lower_at_y17 ----------
print()
print("=" * 70)
print("Q5: c24 = c16(y=18) + c8_lo(y=17)? (cross-LAB carry hypothesis)")
print("=" * 70)
c24 = cells("c24", "block_band_only")
print(f"|c24|         = {len(c24)}")
print(f"|c24 ∩ c16|   = {len(c24 & full16)} (of 181 c16)")
print(f"|c24 \\ c16|   = {len(c24 - full16)} (new for upper y17 LAB)")
