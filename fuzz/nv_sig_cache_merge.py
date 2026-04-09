# SPDX-License-Identifier: GPL-3.0-or-later
"""Task F — merge Plan D' nv_ corpus into a unified 7-tuple sig-cache.

Inputs:
  - results/route_cells.json           legacy 6-tuple (sx,sy -> dx,dy,dn,port)
  - results/nv_route_cells.json        Plan D' extract output
                                       (sx,sy,sn -> dx,dy,dn,port)
  - results/nv_fingerprints/*.json     (optional, fp_stream output)

Output:
  - results/route_cells_full.json      merged 7-tuple (sx,sy,sn -> dx,dy,dn,port)

Merge rules:
  1. Legacy entries: inject sn=0 (green-zone corpus used src_N=0)
  2. Plan D' entries override legacy when key collides (newer data wins)
  3. Deduplicate cells per route (sort + unique)
  4. Drop entries with 0 cells (factory failures / empty diffs)
"""
import json, os, sys, re
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from route_signatures import (
    load_cells,
    _route_key_full,
    CELLS_FULL_PATH,
)

ROOT = HERE.parent
NV_CELLS = ROOT / "results" / "nv_route_cells.json"
OUT = CELLS_FULL_PATH

NV_KEY_RE = re.compile(r"^(\d+),(\d+),(\d+)->(\d+),(\d+),(\d+),(\w+)$")


def lift_legacy():
    """Load legacy route_cells.json and lift keys to 7-tuple (sn=0)."""
    legacy = load_cells()
    if legacy is None:
        return {}
    out = {}
    for lk, cells in legacy.items():
        head, tail = lk.split("->")
        sx, sy = head.split(",")
        parts = tail.split(",")
        dx, dy, dn, port = parts[0], parts[1], parts[2], parts[3]
        nk = _route_key_full(int(sx), int(sy), 0, int(dx), int(dy), int(dn), port)
        out[nk] = sorted({tuple(c) for c in cells})
    return out


def load_nv():
    """Load nv_route_cells.json (Plan D' extract output)."""
    if not NV_CELLS.exists():
        return {}
    raw = json.loads(NV_CELLS.read_text())
    out = {}
    for k, cells in raw.items():
        m = NV_KEY_RE.match(k)
        if not m:
            continue
        sx, sy, sn, dx, dy, dn, port = m.groups()
        nk = _route_key_full(int(sx), int(sy), int(sn),
                             int(dx), int(dy), int(dn), port)
        dedup = sorted({tuple(c) for c in cells})
        if dedup:
            out[nk] = dedup
    return out


def main():
    print("== Plan D' sig-cache merger ==\n")

    legacy = lift_legacy()
    print(f"  legacy entries (sn=0 lifted): {len(legacy)}")

    nv = load_nv()
    print(f"  plan D' nv entries:           {len(nv)}")

    # Overlap analysis: same 7-tuple key in both tables
    overlap = set(legacy) & set(nv)
    disagree = 0
    for k in overlap:
        if set(legacy[k]) != set(nv[k]):
            disagree += 1
    print(f"  key overlap:                  {len(overlap)} "
          f"({disagree} with cell disagreement)")

    # Merge: nv entries override on collision
    merged = dict(legacy)
    merged.update(nv)
    print(f"  merged total:                 {len(merged)}")

    # Source N distribution in merged table
    sn_counts = Counter()
    for k in merged:
        head = k.split("->")[0]
        sn = int(head.split(",")[2])
        sn_counts[sn] += 1
    print(f"\n  source N histogram (top 10):")
    for sn, c in sn_counts.most_common(10):
        print(f"    sn={sn:2d}: {c}")

    # Stats
    total_cells = sum(len(v) for v in merged.values())
    avg = total_cells / len(merged) if merged else 0
    print(f"\n  total cells in merged: {total_cells}  avg/route {avg:.1f}")

    # Serialize (use list form, not tuples, for JSON)
    serial = {k: [list(c) for c in v] for k, v in merged.items()}
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(serial))
    os.replace(tmp, OUT)
    print(f"\nwrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
