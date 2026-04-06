#!/usr/bin/env python3
"""R4 I-index BASE mapper v2 — route-pair diff method.

Instead of diffing against baseline (noisy), we diff two routes that
use the SAME R4 I-index but at DIFFERENT Y values. The diff bits
are the R4 switch moving from one Y to another.

For each diff bit, we check if the reverse formula gives the same BASE
for both the "old Y off" and "new Y on" positions.

Usage:
    python3 r4_mapper2.py 12
    python3 r4_mapper2.py 12 3 13 11 28 16
    python3 r4_mapper2.py --all
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

MAPPED = {0, 1, 2, 4, 7, 10, 14, 15, 17, 18, 20, 22, 25}


def load_rbf(path):
    with open(path, "rb") as f:
        return f.read()


def prev_lab_x(wx):
    candidates = [x for x in LAB_X if x < wx]
    return max(candidates) if candidates else None


def reverse_base(byte_offset, col_start, y):
    """Reverse R4 formula: given absolute byte offset, col_start, and Y,
    return candidate BASE for each slot interpretation."""
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


def expected_bp(y):
    cram_row = y - 2
    group = cram_row // 3
    slot = cram_row % 3
    if slot == 0:
        return 7 - group
    else:
        return 6 - group


def get_routes_for_index(db, target_idx):
    """Find routes using R4 wires with target I-index.
    Returns: {(wx, prev_x): [(wy, src_x, src_y, dst_x, dst_y), ...]}
    """
    c = db.cursor()
    rows = c.execute("SELECT src_x, src_y, dst_x, dst_y, path_json FROM routing_paths").fetchall()

    combos = defaultdict(list)
    for src_x, src_y, dst_x, dst_y, pj in rows:
        path = json.loads(pj)
        for step in path:
            loc = step.get("location", "")
            if not loc or not loc.startswith("R4_"):
                continue
            parts = loc.split("_")
            try:
                wx = int(parts[1][1:])
                wy = int(parts[2][1:])
                ii = int(parts[4][1:])
            except (IndexError, ValueError):
                continue
            if ii != target_idx:
                continue
            px = prev_lab_x(wx)
            if px is None or px not in COLUMN_BASE:
                continue
            combos[(wx, px)].append((wy, src_x, src_y, dst_x, dst_y))

    return combos


def map_index(target_idx, max_columns=4):
    """Map R4 BASE for a single I-index using route-pair diffs."""
    print(f"\n{'='*70}")
    print(f"  Mapping R4 I={target_idx}")
    print(f"{'='*70}")

    db = sqlite3.connect(DB_PATH)
    combos = get_routes_for_index(db, target_idx)
    db.close()

    if not combos:
        print(f"  No routes found for I={target_idx}")
        return None

    # Rank by number of unique Y values
    ranked = []
    for (wx, px), entries in combos.items():
        unique_y = sorted(set(e[0] for e in entries))
        if len(unique_y) >= 2:  # Need at least 2 Y values for pair-diff
            ranked.append((len(unique_y), wx, px, unique_y, entries))
    ranked.sort(reverse=True)

    if not ranked:
        print(f"  No (wx, prev_x) combos with ≥2 Y values")
        return None

    print(f"  {len(ranked)} usable combos (≥2 Y values)")
    for _, wx, px, uy, _ in ranked[:5]:
        print(f"    wx={wx:2d} prev={px:2d}: {len(uy)} Y values {uy}")

    all_bases = defaultdict(list)  # base -> [(prev_x, y1, y2), ...]

    columns_done = 0
    for _, wx, px, unique_y, entries in ranked:
        if columns_done >= max_columns:
            break
        # Skip huge columns (M9K/DSP boundary)
        px_idx = LAB_X.index(px)
        if px_idx + 1 < len(LAB_X):
            next_x = LAB_X[px_idx + 1]
            if next_x in COLUMN_BASE:
                col_width = COLUMN_BASE[next_x] - COLUMN_BASE[px]
                if col_width > 10000:
                    print(f"\n  Skipping wx={wx} prev={px} (col_width={col_width}, non-standard)")
                    continue

        prev_col_start = COLUMN_BASE[px] - 136
        col_end = prev_col_start + 7350

        print(f"\n  --- wx={wx}, prev_x={px} ---")

        # Compile routes for each Y value
        rbf_cache = {}
        for wy in unique_y[:5]:
            matching = [e for e in entries if e[0] == wy]
            if not matching:
                continue
            _, src_x, src_y, dst_x, dst_y = matching[0]
            tag = f"r4m2_I{target_idx}_wx{wx}_wy{wy}"
            print(f"    Compile {tag} ({src_x},{src_y})→({dst_x},{dst_y})...", end=" ", flush=True)
            rbf_path, elapsed, err = compile_route_pair(tag, src_x, src_y, 0, dst_x, dst_y, 0)
            if rbf_path and os.path.exists(rbf_path):
                rbf_cache[wy] = load_rbf(rbf_path)
                print(f"OK ({elapsed:.1f}s)")
            else:
                print(f"FAIL")

        if len(rbf_cache) < 2:
            print(f"    Need ≥2 compiled routes, only got {len(rbf_cache)}")
            continue

        # Diff every pair of Y values
        ys = sorted(rbf_cache.keys())
        for i in range(len(ys)):
            for j in range(i + 1, len(ys)):
                y1, y2 = ys[i], ys[j]
                rbf1, rbf2 = rbf_cache[y1], rbf_cache[y2]
                bp1 = expected_bp(y1)
                bp2 = expected_bp(y2)

                # Find diff bits in prev column that match expected bp for EITHER y
                for byte_off in range(prev_col_start, min(col_end, len(rbf1))):
                    xor = rbf1[byte_off] ^ rbf2[byte_off]
                    if not xor:
                        continue

                    # Check if this bit matches expected bp for y1
                    if xor & (1 << bp1):
                        b = reverse_base(byte_off, prev_col_start, y1)
                        if 0 < b < 7500:
                            # Verify: does the same BASE predict a bit at y2?
                            b2 = reverse_base(byte_off, prev_col_start, y2)
                            # They should give different BASEs (different formulas per slot)
                            # but we just collect candidates
                            all_bases[b].append((px, y1, y2, "y1_match"))

                    if xor & (1 << bp2):
                        b = reverse_base(byte_off, prev_col_start, y2)
                        if 0 < b < 7500:
                            all_bases[b].append((px, y1, y2, "y2_match"))

        columns_done += 1

    if not all_bases:
        print("\n  No candidates found")
        return None

    # Count: how many distinct (prev_x, y_pair) combos support each BASE?
    base_score = {}
    for base, evidence in all_bases.items():
        cols = set()
        pairs = set()
        for px, y1, y2, _ in evidence:
            cols.add(px)
            pairs.add((px, y1, y2))
        base_score[base] = (len(cols), len(pairs), len(evidence))

    top = sorted(base_score.items(), key=lambda x: (-x[1][0], -x[1][1], -x[1][2]))

    print(f"\n  === Results ===")
    print(f"  Top BASE candidates (cols, pairs, total_hits):")
    for base, (ncols, npairs, nhits) in top[:20]:
        pair = base // 210
        pos = base % 210
        print(f"    BASE={base:5d} (pair={pair:2d}, pos={pos:3d}): {ncols} cols, {npairs} pairs, {nhits} hits")

    # Best result
    best_base = top[0][0]
    best_cols = top[0][1][0]

    # Look for pair2 (delta ~210 or ~420 from best)
    pair2 = None
    for base, (ncols, npairs, nhits) in top[1:]:
        delta = abs(base - best_base)
        if 200 <= delta <= 430 and ncols >= 1:
            pair2 = base
            break

    print(f"\n  >>> I={target_idx}: pair1={best_base}", end="")
    if pair2:
        print(f", pair2={pair2}, delta={abs(pair2 - best_base)}")
    else:
        print(f", pair2=TBD")

    if best_cols < 2:
        print(f"  ⚠ Only {best_cols} column(s) — needs more validation")

    return (best_base, pair2)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    if sys.argv[1] == "--all":
        targets = [12, 3, 13, 11, 28, 16, 8, 9, 26, 23, 21, 6]
    else:
        targets = [int(x) for x in sys.argv[1:]]

    results = {}
    for idx in targets:
        if idx in MAPPED:
            print(f"\nI={idx} already mapped, skipping")
            continue
        result = map_index(idx)
        if result:
            results[idx] = result

    if results:
        print(f"\n{'='*70}")
        print(f"  SUMMARY")
        print(f"{'='*70}")
        for idx, (p1, p2) in sorted(results.items()):
            delta = abs(p2 - p1) if p2 else "?"
            p2s = str(p2) if p2 else "TBD"
            print(f"  I={idx:2d}: ({p1}, {p2s}), delta={delta}")
        print(f"\n  _R4_BASE_PREV additions:")
        for idx, (p1, p2) in sorted(results.items()):
            p2s = str(p2) if p2 else p1
            print(f"    {idx:2d}: ({p1}, {p2s}),")


if __name__ == "__main__":
    main()
