#!/usr/bin/env python3
"""C4 I≠0 CRAM address mapper — route-pair diff method.

C4 I=0 has a universal formula: LAB_CRAM_END + SLOT_BASE[slot] + 3*group.
C4 I≠0 has NO universal formula — pair index and position vary per column.

This mapper finds per-(X, I) switch addresses by diffing routes at different
Y values. For each (wx, ii) with >=2 Y values:
  1. Compile routes at two Y values
  2. Diff the two RBFs
  3. Search the self column CRAM for bits at expected bp positions
  4. Record candidates that pass cross-Y validation

Usage:
    python3 c4_mapper.py                  # map all I≠0 with >=2 Y values
    python3 c4_mapper.py --i 12           # map only I=12
    python3 c4_mapper.py --verify         # verify against baseline
"""

import argparse
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


def load_rbf(path):
    with open(path, "rb") as f:
        return f.read()


def expected_bp(y):
    """Expected bit position for a C4/R4 wire at Y coordinate."""
    cram_row = y - 2
    group = cram_row // 3
    slot = cram_row % 3
    return (6 - group) if slot == 2 else (7 - group)


def get_c4_routes(db, target_i=None):
    """Find routes using C4 I≠0 wires, grouped by (wire_x, wire_i) with Y values."""
    rows = db.execute("SELECT src_x, src_y, dst_x, dst_y, path_json FROM routing_paths").fetchall()

    combos = defaultdict(list)  # (wx, ii) -> [(wy, src_x, src_y, dst_x, dst_y)]
    for src_x, src_y, dst_x, dst_y, pj in rows:
        for s in json.loads(pj):
            loc = s.get("location", "")
            if not loc.startswith("C4_"):
                continue
            parts = loc.split("_")
            try:
                wx = int(parts[1][1:])
                wy = int(parts[2][1:])
                ii = int(parts[4][1:])
            except (IndexError, ValueError):
                continue
            if ii == 0:
                continue
            if target_i is not None and ii != target_i:
                continue
            combos[(wx, ii)].append((wy, src_x, src_y, dst_x, dst_y))

    return combos


def find_col_range(wx):
    """Find CRAM byte range for the column containing wx.

    C4 I=0 uses SELF column. For I≠0, search in self column first.
    Returns (col_label, col_start, col_end) or None.
    """
    if wx in COLUMN_BASE:
        col_start = COLUMN_BASE[wx] - 136
        # Find next column to determine width
        sorted_x = sorted(COLUMN_BASE.keys())
        idx = sorted_x.index(wx)
        if idx + 1 < len(sorted_x):
            col_end = COLUMN_BASE[sorted_x[idx + 1]] - 136
        else:
            col_end = col_start + 7350
        return ("self", col_start, col_end)

    # Non-LAB X: find enclosing columns
    sorted_x = sorted(COLUMN_BASE.keys())
    for i in range(len(sorted_x) - 1):
        if sorted_x[i] < wx < sorted_x[i + 1]:
            # Wire is between two LAB columns — search both
            return ("between", COLUMN_BASE[sorted_x[i]] - 136,
                    COLUMN_BASE[sorted_x[i + 1]] - 136 + 7350)
    return None


def map_c4(target_i=None, max_per_i=6, verify=False):
    """Map C4 I≠0 switch addresses."""
    print("=" * 70)
    print(f"  Mapping C4 I≠0 switches" + (f" (I={target_i})" if target_i else ""))
    print("=" * 70)

    db = sqlite3.connect(DB_PATH)
    combos = get_c4_routes(db, target_i)
    db.close()

    # Rank by Y diversity
    ranked = defaultdict(list)  # ii -> [(n_y, wx, unique_y, entries)]
    for (wx, ii), entries in combos.items():
        unique_y = sorted(set(e[0] for e in entries))
        if len(unique_y) >= 2:
            ranked[ii].append((len(unique_y), wx, unique_y, entries))

    for ii in sorted(ranked):
        ranked[ii].sort(reverse=True)

    # Results: (wx, ii) -> [(byte_off, bp, evidence)]
    results = {}

    for ii in sorted(ranked):
        candidates = ranked[ii][:max_per_i]
        print(f"\n{'='*60}")
        print(f"  C4 I={ii}: {len(ranked[ii])} X combos with >=2 Y values")
        print(f"{'='*60}")

        for _, wx, unique_y, entries in candidates:
            print(f"\n  --- X={wx}, I={ii}, Y={unique_y} ---")

            # Compile routes at different Y values
            rbf_cache = {}
            for wy in unique_y[:5]:
                matching = [e for e in entries if e[0] == wy]
                if not matching:
                    continue
                _, sx, sy, dx, dy = matching[0]
                tag = f"c4m_X{wx}_I{ii}_Y{wy}"
                print(f"    Compile {tag} ({sx},{sy})->({dx},{dy})...", end=" ", flush=True)
                rbf_path, elapsed, err = compile_route_pair(tag, sx, sy, 0, dx, dy, 0)
                if rbf_path and os.path.exists(rbf_path):
                    rbf_cache[wy] = load_rbf(rbf_path)
                    print(f"OK ({elapsed:.1f}s)")
                else:
                    print("FAIL")

            if len(rbf_cache) < 2:
                print("    Skipped (need >=2 RBFs)")
                continue

            # Find search region
            col_info = find_col_range(wx)
            if not col_info:
                print(f"    No column range for X={wx}")
                continue
            col_label, search_start, search_end = col_info

            # Diff all pairs of Y values
            ys = sorted(rbf_cache.keys())
            hit_offsets = defaultdict(int)  # byte_off -> count of Y-pair matches

            for i in range(len(ys)):
                for j in range(i + 1, len(ys)):
                    y1, y2 = ys[i], ys[j]
                    r1, r2 = rbf_cache[y1], rbf_cache[y2]
                    bp1, bp2 = expected_bp(y1), expected_bp(y2)

                    if bp1 == bp2:
                        continue  # Same bp means same group — can't distinguish

                    for byte_off in range(search_start, min(search_end, len(r1))):
                        xor = r1[byte_off] ^ r2[byte_off]
                        if not xor:
                            continue

                        # Both expected bps must be set in the XOR
                        if (xor & (1 << bp1)) and (xor & (1 << bp2)):
                            # Check that ONLY these two bits differ (clean switch)
                            mask = (1 << bp1) | (1 << bp2)
                            if xor == mask:
                                hit_offsets[byte_off] += 1

            if hit_offsets:
                # Best candidate: most Y-pair matches
                best = sorted(hit_offsets.items(), key=lambda x: -x[1])
                byte_off = best[0][0]
                count = best[0][1]
                rel = byte_off - search_start
                pair = rel // 210
                pos = rel % 210

                print(f"    FOUND: offset=0x{byte_off:05x} (rel={rel}, pair={pair}, pos={pos})")
                print(f"           {count}/{len(ys)*(len(ys)-1)//2} Y-pairs match")
                if len(best) > 1:
                    print(f"           runner-up: 0x{best[1][0]:05x} ({best[1][1]} matches)")

                results[(wx, ii)] = {
                    "byte_offset": byte_off,
                    "rel": rel,
                    "pair": pair,
                    "pos": pos,
                    "matches": count,
                    "total_pairs": len(ys) * (len(ys) - 1) // 2,
                    "y_values": ys,
                }
            else:
                # Relaxed search: look for single-bp matches
                relaxed = defaultdict(list)  # byte_off -> [(y1, y2, which_bp)]
                for i in range(len(ys)):
                    for j in range(i + 1, len(ys)):
                        y1, y2 = ys[i], ys[j]
                        r1, r2 = rbf_cache[y1], rbf_cache[y2]
                        bp1, bp2 = expected_bp(y1), expected_bp(y2)

                        for byte_off in range(search_start, min(search_end, len(r1))):
                            xor = r1[byte_off] ^ r2[byte_off]
                            if not xor:
                                continue
                            if xor & (1 << bp1):
                                relaxed[byte_off].append((y1, y2, bp1))
                            if xor & (1 << bp2):
                                relaxed[byte_off].append((y1, y2, bp2))

                # Filter: at least 2 Y-pair hits
                good = [(off, evs) for off, evs in relaxed.items() if len(evs) >= 2]
                if good:
                    good.sort(key=lambda x: -len(x[1]))
                    byte_off, evs = good[0]
                    rel = byte_off - search_start
                    pair = rel // 210
                    pos = rel % 210
                    print(f"    RELAXED: offset=0x{byte_off:05x} (rel={rel}, pair={pair}, pos={pos})")
                    print(f"             {len(evs)} hits")
                    results[(wx, ii)] = {
                        "byte_offset": byte_off,
                        "rel": rel,
                        "pair": pair,
                        "pos": pos,
                        "matches": len(evs),
                        "total_pairs": len(ys) * (len(ys) - 1) // 2,
                        "y_values": ys,
                        "relaxed": True,
                    }
                else:
                    print("    NO MATCH")

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY: {len(results)} mappings found")
    print(f"{'='*70}")
    print(f"  {'X':>3} {'I':>3} {'offset':>8} {'rel':>6} {'pair':>4} {'pos':>4} {'matches':>7} {'Y values'}")
    for (wx, ii) in sorted(results):
        r = results[(wx, ii)]
        rlx = " (relaxed)" if r.get("relaxed") else ""
        print(f"  {wx:3d} {ii:3d} 0x{r['byte_offset']:05x} {r['rel']:6d} {r['pair']:4d} {r['pos']:4d} "
              f"{r['matches']:3d}/{r['total_pairs']}{rlx}  Y={r['y_values']}")

    # Check for cross-column patterns (same I, same pair/pos across different X)
    print(f"\n  === Cross-column analysis (same I → same pair/pos?) ===")
    by_i = defaultdict(list)
    for (wx, ii), r in results.items():
        by_i[ii].append((wx, r["pair"], r["pos"], r["rel"]))

    for ii in sorted(by_i):
        entries = by_i[ii]
        if len(entries) < 2:
            continue
        pairs = set(e[1] for e in entries)
        positions = set(e[2] for e in entries)
        if len(pairs) == 1 and len(positions) == 1:
            print(f"  I={ii:2d}: CONSISTENT pair={entries[0][1]}, pos={entries[0][2]} across {len(entries)} columns")
        else:
            print(f"  I={ii:2d}: VARIES — {[(f'X={e[0]}', f'pair={e[1]}', f'pos={e[2]}') for e in entries]}")

    return results


def map_c4_baseline(target_i=None, max_per_i=6):
    """Map C4 I≠0 using baseline diff — look for fixed-byte offsets like R24.

    For each route using C4_X{wx}_Y{wy}_I{ii}:
      1. Diff route RBF against baseline.rbf
      2. In the self column, find bytes where bit at expected_bp(wy) is flipped
      3. Across multiple wy values, find consistent byte offsets

    If C4 I≠0 uses fixed byte offsets (like R24), the same byte will appear
    for all Y values, with only bp varying.
    """
    print("=" * 70)
    print(f"  Mapping C4 I≠0 via baseline diff" + (f" (I={target_i})" if target_i else ""))
    print("=" * 70)

    baseline = load_rbf(BASELINE_PATH)

    db = sqlite3.connect(DB_PATH)
    combos = get_c4_routes(db, target_i)
    db.close()

    # Rank by Y diversity
    ranked = defaultdict(list)
    for (wx, ii), entries in combos.items():
        unique_y = sorted(set(e[0] for e in entries))
        if len(unique_y) >= 2:
            ranked[ii].append((len(unique_y), wx, unique_y, entries))
    for ii in sorted(ranked):
        ranked[ii].sort(reverse=True)

    # Results
    results = {}

    for ii in sorted(ranked):
        candidates = ranked[ii][:max_per_i]
        print(f"\n{'='*60}")
        print(f"  C4 I={ii}: {len(ranked[ii])} X combos with >=2 Y")
        print(f"{'='*60}")

        for _, wx, unique_y, entries in candidates:
            print(f"\n  --- X={wx}, I={ii}, Y={unique_y} ---")

            # Find column range
            col_info = find_col_range(wx)
            if not col_info:
                print(f"    No column range for X={wx}")
                continue
            col_label, col_start, col_end = col_info

            # Compile routes and diff against baseline
            # Track: byte_offset -> {wy: bit_value_matches_expected}
            byte_hits = defaultdict(dict)  # byte_off -> {wy: True/False}

            for wy in unique_y[:6]:
                matching = [e for e in entries if e[0] == wy]
                if not matching:
                    continue
                _, sx, sy, dx, dy = matching[0]
                tag = f"c4b_X{wx}_I{ii}_Y{wy}"
                print(f"    Compile {tag} ({sx},{sy})->({dx},{dy})...", end=" ", flush=True)
                rbf_path, elapsed, err = compile_route_pair(tag, sx, sy, 0, dx, dy, 0)
                if not (rbf_path and os.path.exists(rbf_path)):
                    print("FAIL")
                    continue
                print(f"OK ({elapsed:.1f}s)")

                route_rbf = load_rbf(rbf_path)
                bp = expected_bp(wy)

                # Scan self column for bits flipped at expected bp
                for byte_off in range(col_start, min(col_end, len(route_rbf))):
                    route_bit = (route_rbf[byte_off] >> bp) & 1
                    base_bit = (baseline[byte_off] >> bp) & 1
                    if route_bit != base_bit:
                        byte_hits[byte_off][wy] = True

            compiled_ys = [wy for wy in unique_y[:6]
                           if any(wy in d for d in byte_hits.values())]
            n_compiled = len(compiled_ys)

            if n_compiled < 2:
                print("    Skipped (need >=2 compiled Y)")
                continue

            # Score: byte offsets hit by multiple Y values
            scored = []
            for byte_off, wy_dict in byte_hits.items():
                n_y = len(wy_dict)
                if n_y >= 2:
                    rel = byte_off - col_start
                    pair = rel // 210
                    pos = rel % 210
                    scored.append((n_y, byte_off, rel, pair, pos))

            scored.sort(reverse=True)

            if scored:
                best_ny, byte_off, rel, pair, pos = scored[0]
                hit_ys = sorted(byte_hits[byte_off].keys())
                print(f"    BEST: offset=0x{byte_off:05x} rel={rel} pair={pair} pos={pos}")
                print(f"          {best_ny}/{n_compiled} Y values hit: {hit_ys}")
                if len(scored) > 1:
                    _, bo2, r2, p2, ps2 = scored[1]
                    print(f"          runner-up: 0x{bo2:05x} rel={r2} pair={p2} pos={ps2} ({scored[1][0]} Y)")

                results[(wx, ii)] = {
                    "byte_offset": byte_off,
                    "rel": rel,
                    "pair": pair,
                    "pos": pos,
                    "hit_ys": hit_ys,
                    "total_ys": n_compiled,
                    "rate": f"{best_ny}/{n_compiled}",
                }
            else:
                print("    NO MATCH (no byte hit by >=2 Y values)")

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY: {len(results)} mappings found")
    print(f"{'='*70}")
    print(f"  {'X':>3} {'I':>3} {'offset':>8} {'rel':>6} {'pair':>4} {'pos':>4} {'rate':>7}  Y values")
    for (wx, ii) in sorted(results):
        r = results[(wx, ii)]
        print(f"  {wx:3d} {ii:3d} 0x{r['byte_offset']:05x} {r['rel']:6d} {r['pair']:4d} {r['pos']:4d} "
              f"{r['rate']:>7s}  Y={r['hit_ys']}")

    # Cross-column analysis
    print(f"\n  === Cross-column analysis ===")
    by_i = defaultdict(list)
    for (wx, ii), r in results.items():
        by_i[ii].append((wx, r["pair"], r["pos"], r["rel"], r["rate"]))

    for ii in sorted(by_i):
        entries = by_i[ii]
        if len(entries) < 2:
            continue
        pairs_set = set(e[1] for e in entries)
        pos_set = set(e[2] for e in entries)
        if len(pairs_set) == 1 and len(pos_set) == 1:
            print(f"  I={ii:2d}: CONSISTENT pair={entries[0][1]}, pos={entries[0][2]} "
                  f"across {len(entries)} columns")
        else:
            for wx, pair, pos, rel, rate in sorted(entries):
                print(f"  I={ii:2d} X={wx:2d}: pair={pair}, pos={pos} ({rate})")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C4 I≠0 CRAM address mapper")
    parser.add_argument("--i", type=int, default=None, help="Map only this I-index")
    parser.add_argument("--max-per-i", type=int, default=6, help="Max X combos per I-index")
    parser.add_argument("--verify", action="store_true", help="Verify against baseline")
    parser.add_argument("--method", choices=["pair", "baseline"], default="baseline",
                        help="Mapping method: pair (route-pair diff) or baseline (diff vs baseline)")
    args = parser.parse_args()

    if args.method == "pair":
        map_c4(target_i=args.i, max_per_i=args.max_per_i, verify=args.verify)
    else:
        map_c4_baseline(target_i=args.i, max_per_i=args.max_per_i)
