#!/usr/bin/env python3
"""R24 I=0 BASE mapper — route-pair diff method.

R24 wires are row wires spanning ~24 columns. Like R4, their switches
might be in the SAME or PREV column's CRAM. We use route-pair diffs
to find the BASE values.

Usage:
    python3 r24_mapper.py
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


def load_rbf(path):
    with open(path, "rb") as f:
        return f.read()


def prev_lab_x(wx):
    candidates = [x for x in LAB_X if x < wx]
    return max(candidates) if candidates else None


def next_lab_x(wx):
    candidates = [x for x in LAB_X if x > wx]
    return min(candidates) if candidates else None


def expected_bp(y):
    cram_row = y - 2
    group = cram_row // 3
    slot = cram_row % 3
    return (6 - group) if slot == 2 else (7 - group)


def reverse_base(byte_offset, col_start, y):
    """Reverse R4-style formula to get candidate BASE."""
    cram_row = y - 2
    group = cram_row // 3
    slot = cram_row % 3
    rel = byte_offset - col_start

    if slot == 0:
        correction = 1 if group > 0 else 0
        base = rel - 66 - 3 * group - correction
    elif slot == 1:
        base = rel + 70 - 3 * group
    else:
        base = rel - 3 * group

    return base


def get_r24_routes(db, target_i=0):
    """Find routes using R24 wires, grouped by (wire_x) with Y values."""
    rows = db.execute("SELECT src_x, src_y, dst_x, dst_y, path_json FROM routing_paths").fetchall()

    combos = defaultdict(list)  # wx -> [(wy, src_x, src_y, dst_x, dst_y)]
    for src_x, src_y, dst_x, dst_y, pj in rows:
        for s in json.loads(pj):
            loc = s.get("location", "")
            if not loc.startswith("R24_"):
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
            combos[wx].append((wy, src_x, src_y, dst_x, dst_y))

    return combos


def map_r24_i0():
    """Map R24 I=0 switch addresses."""
    print("=" * 70)
    print("  Mapping R24 I=0")
    print("=" * 70)

    db = sqlite3.connect(DB_PATH)
    combos = get_r24_routes(db, target_i=0)
    db.close()

    # Rank by Y diversity
    ranked = []
    for wx, entries in combos.items():
        unique_y = sorted(set(e[0] for e in entries))
        if len(unique_y) >= 2:
            ranked.append((len(unique_y), wx, unique_y, entries))
    ranked.sort(reverse=True)

    print(f"  {len(ranked)} usable wire-X combos with >=2 Y values")
    for _, wx, uy, _ in ranked[:10]:
        is_lab = "LAB" if wx in LAB_X else "non"
        print(f"    X={wx:2d} ({is_lab}): {len(uy)} Y values {uy}")

    # For each good X, compile routes at different Y values
    # Search in BOTH self column and prev column (we don't know which yet)
    all_bases_self = defaultdict(list)   # base -> [(wx, y1, y2)]
    all_bases_prev = defaultdict(list)

    for _, wx, unique_y, entries in ranked[:6]:
        print(f"\n  --- X={wx} ---")

        rbf_cache = {}
        for wy in unique_y[:5]:
            matching = [e for e in entries if e[0] == wy]
            if not matching:
                continue
            _, sx, sy, dx, dy = matching[0]
            tag = f"r24m_X{wx}_Y{wy}"
            print(f"    Compile {tag} ({sx},{sy})->({dx},{dy})...", end=" ", flush=True)
            rbf_path, elapsed, err = compile_route_pair(tag, sx, sy, 0, dx, dy, 0)
            if rbf_path and os.path.exists(rbf_path):
                rbf_cache[wy] = load_rbf(rbf_path)
                print(f"OK ({elapsed:.1f}s)")
            else:
                print("FAIL")

        if len(rbf_cache) < 2:
            continue

        # Determine search columns
        px = prev_lab_x(wx)
        search_cols = []
        if wx in COLUMN_BASE:
            search_cols.append(("self", wx, COLUMN_BASE[wx] - 136))
        if px and px in COLUMN_BASE:
            search_cols.append(("prev", px, COLUMN_BASE[px] - 136))
        # Also try next LAB X
        nx = next_lab_x(wx)
        if nx and nx in COLUMN_BASE:
            search_cols.append(("next", nx, COLUMN_BASE[nx] - 136))

        # Diff pairs of Y values
        ys = sorted(rbf_cache.keys())
        for col_label, col_x, col_start in search_cols:
            col_end = col_start + 7350

            for i in range(len(ys)):
                for j in range(i + 1, len(ys)):
                    y1, y2 = ys[i], ys[j]
                    r1, r2 = rbf_cache[y1], rbf_cache[y2]
                    bp1, bp2 = expected_bp(y1), expected_bp(y2)

                    for byte_off in range(col_start, min(col_end, len(r1))):
                        xor = r1[byte_off] ^ r2[byte_off]
                        if not xor:
                            continue

                        if xor & (1 << bp1):
                            b = reverse_base(byte_off, col_start, y1)
                            if 0 < b < 7500:
                                target = all_bases_self if col_label == "self" else all_bases_prev
                                target[b].append((wx, col_x, y1, y2, col_label))

                        if xor & (1 << bp2):
                            b = reverse_base(byte_off, col_start, y2)
                            if 0 < b < 7500:
                                target = all_bases_self if col_label == "self" else all_bases_prev
                                target[b].append((wx, col_x, y1, y2, col_label))

    # Score and report
    for label, all_bases in [("SELF column", all_bases_self), ("PREV column", all_bases_prev)]:
        if not all_bases:
            continue
        scored = []
        for base, evidence in all_bases.items():
            wxs = set(e[0] for e in evidence)
            pairs = set((e[0], e[2], e[3]) for e in evidence)
            scored.append((len(wxs), len(pairs), len(evidence), base))
        scored.sort(reverse=True)

        print(f"\n  === {label} — Top BASE candidates ===")
        print(f"  {'base':>6} {'pair':>4} {'pos':>4} {'#wx':>4} {'#pairs':>6} {'#hits':>5}")
        for nwx, npairs, nhits, base in scored[:25]:
            pair = base // 210
            pos = base % 210
            wxs = sorted(set(e[0] for e in all_bases[base]))
            print(f"  {base:6d} {pair:4d} {pos:4d} {nwx:4d} {npairs:6d} {nhits:5d}  wx={wxs}")


if __name__ == "__main__":
    map_r24_i0()
