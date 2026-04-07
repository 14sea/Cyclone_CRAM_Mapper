# SPDX-License-Identifier: GPL-3.0-or-later
"""C4 I≠0 fog-of-war scanner.

Step 1: Query routing_paths SQLite for every (X,I) combo of C4 wires that
        is NOT yet in _C4_FIXED_OFFSETS, ranked by Y-diversity.
Step 2: Run the existing baseline-diff mapper (c4_mapper.map_c4_baseline)
        aggressively (high --max-per-i) over the unmapped combos.
Step 3: Print a delta table the user can paste into bitstream.py.
"""
import sys, os, json, sqlite3
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitstream import _C4_FIXED_OFFSETS
from c4_mapper import map_c4_baseline

DB_PATH = "/home/test/EP4CE6/results/ep4ce6_bitdb.sqlite"

def survey():
    db = sqlite3.connect(DB_PATH)
    rows = db.execute("SELECT src_x, src_y, dst_x, dst_y, path_json FROM routing_paths").fetchall()
    db.close()
    combos = defaultdict(set)  # (wx,ii) -> set of wy
    for sx, sy, dx, dy, pj in rows:
        for s in json.loads(pj):
            loc = s.get("location", "")
            if not loc.startswith("C4_"):
                continue
            parts = loc.split("_")
            try:
                wx = int(parts[1][1:]); wy = int(parts[2][1:]); ii = int(parts[4][1:])
            except (IndexError, ValueError):
                continue
            if ii == 0:
                continue
            combos[(wx, ii)].add(wy)
    return combos

def main():
    combos = survey()
    mapped = set(_C4_FIXED_OFFSETS.keys())
    all_keys = set(combos.keys())
    unmapped = all_keys - mapped

    print(f"=== C4 I≠0 fog-of-war survey ===")
    print(f"  total (X,I) combos in routing_paths: {len(all_keys)}")
    print(f"  already mapped:                      {len(mapped)}")
    print(f"  unmapped:                            {len(unmapped)}")
    print()
    by_diversity = sorted(unmapped, key=lambda k: -len(combos[k]))
    print(f"  unmapped combos by Y-diversity:")
    high, low = [], []
    for k in by_diversity:
        ys = sorted(combos[k])
        line = f"    X={k[0]:3d} I={k[1]:3d}  ny={len(ys):2d}  Y={ys}"
        if len(ys) >= 2:
            high.append(k); print(line)
        else:
            low.append(k)
    if low:
        print(f"\n  {len(low)} combos with only 1 Y value (need fresh compiles):")
        for k in low[:20]:
            print(f"    X={k[0]:3d} I={k[1]:3d}  Y={sorted(combos[k])}")
        if len(low) > 20:
            print(f"    ... +{len(low)-20} more")

    if not high:
        print("\nNo unmapped combos with sufficient Y-diversity to map from existing corpus.")
        print("Next step: generate more compiles via CE10 jailbreak target.")
        return

    print(f"\n=== Running baseline-diff mapper on {len(high)} mappable combos ===\n")
    # Per I-index, run mapper restricted to that I and high max_per_i
    by_i = defaultdict(list)
    for k in high:
        by_i[k[1]].append(k[0])
    new_mappings = {}
    for ii in sorted(by_i):
        print(f"\n{'#'*60}\n# C4 I={ii}: {len(by_i[ii])} unmapped X values\n{'#'*60}")
        results = map_c4_baseline(target_i=ii, max_per_i=12)
        for key, r in results.items():
            if key in mapped:
                continue
            new_mappings[key] = r

    print(f"\n\n=== NEW MAPPINGS: {len(new_mappings)} ===")
    print("# Paste into _C4_FIXED_OFFSETS in bitstream.py:")
    for (wx, ii) in sorted(new_mappings):
        r = new_mappings[(wx, ii)]
        rate = r.get("rate", "?")
        print(f"    ({wx}, {ii}): 0x{r['byte_offset']:05x},   # {rate} Y hit")

if __name__ == "__main__":
    main()
