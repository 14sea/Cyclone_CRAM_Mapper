#!/usr/bin/env python3
"""R4 I-index BASE mapper via cross-Y validation.

For each target I-index:
1. Find routes from the DB that use R4_X{wx}_Y{wy}_I{idx} at multiple Y values
2. Compile each route, diff against baseline.rbf
3. Reverse the slot/group formula to get candidate BASE
4. The BASE consistent across >=2 Y values is correct
5. Cross-validate across >=2 prev_lab_x columns

Usage:
    python3 r4_mapper.py 12          # map single I-index
    python3 r4_mapper.py 12 3 13 11  # map multiple
    python3 r4_mapper.py --all       # map all unmapped high-frequency indices
"""

import sys
import os
import json
import sqlite3
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

from config import COLUMN_BASE, LAB_X
from runner import compile_route_pair


def load_rbf(path):
    with open(path, "rb") as f:
        return f.read()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "results", "ep4ce6_bitdb.sqlite")
BASELINE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "results", "rbf", "baseline.rbf")

# Already mapped I-indices (from bitstream.py)
MAPPED = {0, 1, 2, 3, 4, 6, 7, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 25}


def prev_lab_x(wx):
    """Find the largest LAB_X value strictly less than wx."""
    candidates = [x for x in LAB_X if x < wx]
    return max(candidates) if candidates else None


def reverse_r4_formula(byte_offset, prev_col_start, y):
    """Given a diff bit's byte_offset and the wire's Y, reverse the R4 slot/group
    formula to compute the candidate BASE value.

    Returns candidate BASE or None if the bit position doesn't match.
    """
    cram_row = y - 2
    group = cram_row // 3
    slot = cram_row % 3

    rel = byte_offset - prev_col_start

    if slot == 0:
        # byte = base + 66 + 3*group + (1 if group>0 else 0)
        correction = 1 if group > 0 else 0
        base = rel - 66 - 3 * group - correction
    elif slot == 1:
        # byte = base + (-70) + 3*group
        base = rel - (-70) - 3 * group
    else:  # slot == 2
        # byte = base + 3*group
        base = rel - 3 * group

    return base


def get_routes_for_index(db, target_idx):
    """Find all routes that use R4 wires with the target I-index.

    Returns dict: (wx, prev_x) -> [(wy, src_x, src_y, dst_x, dst_y), ...]
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
            if px is None:
                continue
            combos[(wx, px)].append((wy, src_x, src_y, dst_x, dst_y))

    return combos


def map_index(target_idx, max_columns=3, max_y_per_col=4):
    """Map R4 BASE for a single I-index using cross-Y validation."""
    print(f"\n{'='*70}")
    print(f"  Mapping R4 I={target_idx}")
    print(f"{'='*70}")

    db = sqlite3.connect(DB_PATH)
    combos = get_routes_for_index(db, target_idx)
    db.close()

    if not combos:
        print(f"  No routes found for I={target_idx}")
        return None

    # Sort combos by number of unique Y values (descending) — best columns first
    ranked = []
    for (wx, px), entries in combos.items():
        unique_y = sorted(set(e[0] for e in entries))
        ranked.append((len(unique_y), wx, px, unique_y, entries))
    ranked.sort(reverse=True)

    print(f"  {len(ranked)} (wx, prev_x) combos available")
    for _, wx, px, uy, _ in ranked[:5]:
        print(f"    wx={wx:2d} prev={px:2d}: {len(uy)} Y values {uy}")

    # Load baseline
    baseline = load_rbf(BASELINE_PATH)

    # For each column, compile routes at different Y values and find consistent BASE
    all_results = {}  # prev_x -> {base_value: count}

    columns_tested = 0
    for _, wx, px, unique_y, entries in ranked:
        if columns_tested >= max_columns:
            break

        # Skip boundary columns (non-standard width)
        if px not in COLUMN_BASE:
            continue
        prev_col_start = COLUMN_BASE[px] - 136

        print(f"\n  --- Testing wx={wx}, prev_x={px} (col_start={prev_col_start}) ---")

        base_candidates = defaultdict(int)  # base -> count of Y values supporting it
        y_tested = 0

        for wy in unique_y[:max_y_per_col]:
            # Find a route that uses this wire
            matching = [(wy2, sx, sy2, dx, dy) for (wy2, sx, sy2, dx, dy) in entries if wy2 == wy]
            if not matching:
                continue

            _, src_x, src_y, dst_x, dst_y = matching[0]
            tag = f"r4map_I{target_idx}_wx{wx}_wy{wy}"

            print(f"    Compiling {tag} (src=({src_x},{src_y}) dst=({dst_x},{dst_y}))...", end=" ", flush=True)

            rbf_path_result, elapsed, err = compile_route_pair(
                tag, src_x, src_y, 0, dst_x, dst_y, 0
            )

            if not rbf_path_result or not os.path.exists(rbf_path_result):
                print(f"FAILED: {err[:80] if err else 'unknown'}")
                continue

            design = load_rbf(rbf_path_result)
            print(f"OK ({elapsed:.1f}s)")

            # Find diff bits in prev column region
            # Standard column is 7350 bytes wide
            col_width = COLUMN_BASE.get(LAB_X[LAB_X.index(px) + 1], prev_col_start + 7350) - COLUMN_BASE[px] if px in COLUMN_BASE and LAB_X.index(px) + 1 < len(LAB_X) else 7350
            col_end = prev_col_start + abs(col_width)

            # Expected bit position for this Y
            cram_row = wy - 2
            group = cram_row // 3
            slot = cram_row % 3
            if slot == 0:
                expected_bp = 7 - group
            else:
                expected_bp = 6 - group

            for byte_off in range(prev_col_start, min(col_end, len(baseline))):
                xor = baseline[byte_off] ^ design[byte_off]
                if not xor:
                    continue
                # Only check the expected bit position for this Y
                if xor & (1 << expected_bp):
                    base = reverse_r4_formula(byte_off, prev_col_start, wy)
                    if base is not None and 0 < base < 8000:
                        base_candidates[base] += 1

            y_tested += 1

        if not base_candidates:
            print(f"    No candidates found")
            continue

        # Find bases that appear across multiple Y values
        top = sorted(base_candidates.items(), key=lambda x: -x[1])
        print(f"\n    Top BASE candidates (base: hits):")
        for base, count in top[:15]:
            pair = base // 210
            pos = base % 210
            print(f"      BASE={base:5d} (pair={pair:2d}, pos={pos:3d}): {count} hits")

        all_results[px] = top[:10]
        columns_tested += 1

    # Cross-column validation: find BASE values that appear in multiple columns
    if len(all_results) >= 2:
        print(f"\n  === Cross-column validation ({len(all_results)} columns) ===")
        base_across = defaultdict(list)
        for px, tops in all_results.items():
            for base, count in tops:
                base_across[base].append((px, count))

        consistent = [(base, cols) for base, cols in base_across.items() if len(cols) >= 2]
        consistent.sort(key=lambda x: -sum(c for _, c in x[1]))

        if consistent:
            print(f"  Bases appearing in ≥2 columns:")
            for base, cols in consistent[:10]:
                pair = base // 210
                pos = base % 210
                col_str = ", ".join(f"prev={px}({cnt})" for px, cnt in cols)
                print(f"    BASE={base:5d} (pair={pair:2d}, pos={pos:3d}): {col_str}")

            best_base = consistent[0][0]
            # Look for a second base (pair2) with delta ~210 or ~420
            pair2_candidates = []
            for base, cols in consistent[1:]:
                delta = abs(base - best_base)
                if 200 <= delta <= 430:
                    pair2_candidates.append((base, delta, cols))

            print(f"\n  >>> RESULT: I={target_idx}")
            print(f"      pair1 BASE = {best_base}")
            if pair2_candidates:
                p2, delta, _ = pair2_candidates[0]
                print(f"      pair2 BASE = {p2} (delta={delta})")
                return (best_base, p2)
            else:
                print(f"      pair2 BASE = TBD")
                return (best_base, None)
        else:
            print("  No cross-column consistent BASE found")
    elif all_results:
        # Single column result
        px, tops = list(all_results.items())[0]
        if tops:
            best = tops[0][0]
            print(f"\n  >>> TENTATIVE (single column): I={target_idx}, BASE={best}")
            return (best, None)

    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    if sys.argv[1] == "--all":
        # High-frequency unmapped indices
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

    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    for idx, (p1, p2) in sorted(results.items()):
        delta = abs(p2 - p1) if p2 else "?"
        p2_str = str(p2) if p2 else "TBD"
        print(f"  I={idx:2d}: ({p1}, {p2_str}), delta={delta}")

    if results:
        print(f"\n  Add to bitstream.py _R4_BASE_PREV:")
        for idx, (p1, p2) in sorted(results.items()):
            p2_str = str(p2) if p2 else "p1"  # placeholder
            print(f"    {idx:2d}: ({p1}, {p2_str}),")


if __name__ == "__main__":
    main()
