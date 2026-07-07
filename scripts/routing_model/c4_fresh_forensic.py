#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sanity + forensic on the fresh vertical builds (tmp/c4_fresh/).

1. Does the KNOWN C4 I=0 production law hit on fresh builds?  (pipeline
   sanity — 2026-07-07 answer: 12/18 = 67%, so the wires<->cells data is
   aligned but even the best-established C4 law is not complete.)
2. For every C4 I!=0 pip, list the ACTUAL column-relative R values of
   XOR cells at the target wire's Y-address bp (|R|<8000 window).

Key 2026-07-07 findings this produced (see memo
c4_pip_write_loop_closed_2026_07_07):
  - identical pip keys with identical driver geometry (LE_BUFFER dx=0
    I=12, driver dy=+4, N0) give DISJOINT R sets across builds;
  - some pips have ZERO cells at the matched bp anywhere in the window
    (e.g. (12,'C4',0,slot1) in cf_X10Y14) while the same key has cells
    in another build -> probable MUX default-input = no-bits semantics;
  - i.e. the (I, src_type, dx, slot) pip key lacks >=1 context dimension.
"""
import sys, os, json, glob, re, collections
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
sys.path.insert(0, os.path.join(REPO, 'scripts/routing_model'))
import bitstream, config
import pip_prediction_gate as gate

CB = config.COLUMN_BASE
SB = bitstream._C4_SLOT_BASE
ZERO = open(os.path.join(REPO, 'results/rbf/nv_zero_global.rbf'), 'rb').read()
WIRE = gate.WIRE

def yaddr(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    return g, s, (6 - g) if s == 2 else (7 - g)

builds = {}
for fn in sorted(glob.glob(os.path.join(REPO, 'tmp/c4_fresh/*.wires.json'))):
    tag = os.path.basename(fn)[:-11]
    gold = open(fn.replace('.wires.json', '.rbf'), 'rb').read()
    cells = set()
    for off in range(5282, 367952):
        if (off - 32) % 210 >= 208:
            continue
        d = gold[off] ^ ZERO[off]
        for bp in range(8):
            if d >> bp & 1:
                cells.add((off, bp))
    builds[tag] = (json.load(open(fn)), cells)

# --- 1. C4 I=0 sanity (production law) ---
hit = tot = 0
for tag, (seq, cells) in builds.items():
    for w in set(seq):
        m = WIRE.match(w)
        if not m or m.group(1) != 'C4' or m.group(5) is None:
            continue
        x, y, i = int(m.group(2)), int(m.group(3)), int(m.group(5))
        if i != 0 or x not in CB or not 2 <= y <= 21:
            continue
        g, s, bp = yaddr(y)
        tot += 1
        hit += (CB[x] + 1519 + SB[s] + 3 * g, bp) in cells
print(f"C4 I=0 production-law sanity on fresh builds: {hit}/{tot}")

# --- 2. forensic: actual R at matched bp for every C4 I!=0 pip ---
print("\nper-pip actual candidate R values (|R|<8000, matched bp):")
freq = collections.defaultdict(collections.Counter)
for tag, (seq, cells) in builds.items():
    seen = set()
    for a, b in zip(seq, seq[1:]):
        mb = WIRE.match(b)
        if not mb or mb.group(1) != 'C4' or not mb.group(5):
            continue
        x, y, i = int(mb.group(2)), int(mb.group(3)), int(mb.group(5))
        if i == 0 or x not in CB or not 2 <= y <= 21:
            continue
        ma = WIRE.match(a)
        if not ma:
            continue
        g, s, bp = yaddr(y)
        key = (i, ma.group(1), int(ma.group(2)) - x, s)
        if (key, b) in seen:
            continue
        seen.add((key, b))
        rs = sorted(off - CB[x] - 3 * g for off, bpc in cells
                    if bpc == bp and abs(off - CB[x] - 3 * g) < 8000)
        freq[key].update(rs)
        print(f"  {tag} {a}->{b} key={key} g={g} bp={bp} R={rs}")

print("\nR frequency per class:")
for key, cnt in sorted(freq.items()):
    print(f"  {key}: {cnt.most_common(8)}")
