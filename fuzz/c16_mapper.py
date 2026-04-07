#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""C16 switch CRAM address mapper.

C16 wires are column wires spanning ~16 rows. Like C4, their switches
should be in the SAME column's CRAM. We use route-pair diffs to find
the SLOT_BASE values.

Usage:
    python3 c16_mapper.py
"""

import sys
import os
import json
import sqlite3
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

from config import COLUMN_BASE, LAB_X
from runner import compile_route_pair

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "results", "ep4ce6_bitdb.sqlite")
BASELINE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "results", "rbf", "baseline.rbf")

# C4 I=0 reference: switches are at LAB_CRAM_END + SLOT_BASE
# C16 might be nearby
_LAB_CRAM_END = {
    3: 0x07ccf, 4: 0x09985, 6: 0x0d2f1, 7: 0x0efa7, 8: 0x10c5d,
    10: 0x145c9, 11: 0x1627f, 12: 0x17f35, 13: 0x19beb,
    16: 0x2c5b1, 17: 0x2e267, 18: 0x30265, 19: 0x31f1b,
    21: 0x35053, 22: 0x36d09, 23: 0x389bf, 24: 0x3a675,
    25: 0x3c32b, 26: 0x3dfe1, 28: 0x4ecf1, 29: 0x509a7, 31: 0x54313,
}


def load_rbf(path):
    with open(path, "rb") as f:
        return f.read()


def expected_bp(y):
    cram_row = y - 2
    group = cram_row // 3
    slot = cram_row % 3
    return (6 - group) if slot == 2 else (7 - group)


def get_c16_routes(db, target_i=0):
    """Find routes using C16 wires, grouped by (x, i) with Y values."""
    rows = db.execute("SELECT src_x, src_y, dst_x, dst_y, path_json FROM routing_paths").fetchall()

    combos = defaultdict(list)  # (wire_x, i) -> [(wire_y, src_x, src_y, dst_x, dst_y)]
    for src_x, src_y, dst_x, dst_y, pj in rows:
        for s in json.loads(pj):
            loc = s.get("location", "")
            if not loc or not loc.startswith("C16_"):
                continue
            parts = loc.split("_")
            try:
                wx = int(parts[1][1:])
                wy = int(parts[2][1:])
                ii = int(parts[4][1:])
            except:
                continue
            if ii != target_i:
                continue
            combos[(wx, ii)].append((wy, src_x, src_y, dst_x, dst_y))

    return combos


def map_c16_i0():
    """Map C16 I=0 switch addresses."""
    print("=" * 70)
    print("  Mapping C16 I=0")
    print("=" * 70)

    db = sqlite3.connect(DB_PATH)
    combos = get_c16_routes(db, target_i=0)
    db.close()

    # Rank by Y diversity
    ranked = []
    for (wx, ii), entries in combos.items():
        unique_y = sorted(set(e[0] for e in entries))
        if len(unique_y) >= 2 and wx in _LAB_CRAM_END:
            ranked.append((len(unique_y), wx, unique_y, entries))
    ranked.sort(reverse=True)

    print(f"  {len(ranked)} usable (x, I=0) combos")
    for _, wx, uy, _ in ranked[:8]:
        print(f"    X={wx:2d}: {len(uy)} Y values {uy}")

    baseline = load_rbf(BASELINE_PATH)

    # For each X, compile routes at different Y, look for switch bits
    # near LAB_CRAM_END[x]
    all_offsets = defaultdict(list)  # (slot, offset_from_end) -> [(x, y)]

    for _, wx, unique_y, entries in ranked[:5]:
        cram_end = _LAB_CRAM_END[wx]
        col_start = COLUMN_BASE.get(wx, cram_end - 5000) - 136

        print(f"\n  --- X={wx} (CRAM_END=0x{cram_end:05x}) ---")

        rbf_cache = {}
        for wy in unique_y[:5]:
            matching = [e for e in entries if e[0] == wy]
            if not matching:
                continue
            _, sx, sy, dx, dy = matching[0]
            tag = f"c16m_X{wx}_Y{wy}"
            print(f"    Compile {tag} ({sx},{sy})→({dx},{dy})...", end=" ", flush=True)
            rbf_path, elapsed, err = compile_route_pair(tag, sx, sy, 0, dx, dy, 0)
            if rbf_path and os.path.exists(rbf_path):
                rbf_cache[wy] = load_rbf(rbf_path)
                print(f"OK ({elapsed:.1f}s)")
            else:
                print("FAIL")

        if len(rbf_cache) < 2:
            continue

        # Diff pairs of Y values
        ys = sorted(rbf_cache.keys())
        for i in range(len(ys)):
            for j in range(i + 1, len(ys)):
                y1, y2 = ys[i], ys[j]
                r1, r2 = rbf_cache[y1], rbf_cache[y2]
                bp1, bp2 = expected_bp(y1), expected_bp(y2)

                # Search region: around LAB_CRAM_END, extended range
                search_start = cram_end - 500
                search_end = min(cram_end + 5000, len(r1))

                for byte_off in range(search_start, search_end):
                    xor = r1[byte_off] ^ r2[byte_off]
                    if not xor:
                        continue

                    rel = byte_off - cram_end

                    # Check if bit at expected_bp for y1 changed
                    if xor & (1 << bp1):
                        cr1 = (y1 - 2) % 3
                        all_offsets[(cr1, rel)].append((wx, y1, y2, f"y1_bp{bp1}"))

                    if xor & (1 << bp2):
                        cr2 = (y2 - 2) % 3
                        all_offsets[(cr2, rel)].append((wx, y1, y2, f"y2_bp{bp2}"))

    if not all_offsets:
        print("\n  No candidates")
        return

    # Score: how many distinct X columns support each (slot, offset)?
    scored = []
    for (slot, off), evidence in all_offsets.items():
        xs = set(e[0] for e in evidence)
        scored.append((len(xs), len(evidence), slot, off))
    scored.sort(reverse=True)

    print(f"\n  === Top (slot, offset_from_CRAM_END) candidates ===")
    print(f"  {'slot':>4} {'offset':>8} {'#cols':>5} {'#hits':>5}")
    for ncols, nhits, slot, off in scored[:30]:
        print(f"  {slot:4d} {off:8d} {ncols:5d} {nhits:5d}")

    # Group by slot to find SLOT_BASE pattern (like C4's {0:2405, 1:2475, 2:2338})
    print(f"\n  === Grouped by slot ===")
    for s in range(3):
        entries = [(off, ncols, nhits) for ncols, nhits, slot, off in scored if slot == s and ncols >= 2]
        if entries:
            entries.sort(key=lambda x: -x[1])
            print(f"  Slot {s}:")
            for off, nc, nh in entries[:5]:
                print(f"    offset={off:6d} ({nc} cols, {nh} hits)")


if __name__ == "__main__":
    map_c16_i0()
