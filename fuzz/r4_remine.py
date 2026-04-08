# SPDX-License-Identifier: GPL-3.0-or-later
"""R4 _R4_BASE_PREV[I] analytic re-mine from bit-perfect corpora.

Zero new compiles: correlate I-index presence (r4_iindex_table.json)
with absolute CRAM cells (route_cells.json) across all routes, brute-
force the (pair1, pair2) base that maximizes per-wire hit rate.

Proof-of-concept target: I=6 (unblocked 2026-04-08 by STA cross-check).
346 routes across 21 source LABs and 26 prev_x columns give a much
bigger sample than any prior R4 mine.

Usage: python fuzz/r4_remine.py [I]   (default I=6)
"""
import os, sys, json
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import COLUMN_BASE, LAB_X

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CELLS_PATH = os.path.join(REPO, "results", "route_cells.json")
IINDEX_PATH = os.path.join(REPO, "results", "r4_iindex_table.json")

LAB_X_SORTED = sorted(LAB_X)


def prev_lab_x(wx):
    """Largest LAB_X strictly less than wx."""
    prev = None
    for x in LAB_X_SORTED:
        if x < wx:
            prev = x
        else:
            break
    return prev


def predicted_cells(wy, col_start, pair1, pair2):
    """Returns list of (byte, bp) pairs predicted by the R4 formula.

    Slot-dependent formula from CLAUDE.md / bitstream.py.
    Each wire places 2 cells (one per pair1, one per pair2).
    """
    group = (wy - 2) // 3
    slot = (wy - 2) % 3

    # slot 0: byte = col_start + BASE + 66 + 3*group + (1 if group>0 else 0), bp = 7-group
    # slot 1: byte = col_start + BASE + (-70) + 3*group, bp = 6-group
    # slot 2: byte = col_start + BASE + 3*group, bp = 6-group
    if slot == 0:
        off = 66 + 3 * group + (1 if group > 0 else 0)
        bp = 7 - group
    elif slot == 1:
        off = -70 + 3 * group
        bp = 6 - group
    else:  # slot == 2
        off = 3 * group
        bp = 6 - group

    if not (0 <= bp <= 7):
        return []
    out = []
    for base in (pair1, pair2):
        byte = col_start + base + off
        out.append((byte, bp))
    return out


def wire_col_start(wx, mode):
    """mode='prev_lab': largest LAB_X < wx (default R4 model)
       mode='self':     COLUMN_BASE[wx] itself (for non-LAB CRAM wires
                        whose cells live in the wx column, e.g. M9K X=15
                        or DSP X=20)
       Returns None if wx has no COLUMN_BASE entry for that mode."""
    if mode == "prev_lab":
        px = prev_lab_x(wx)
        if px is None or px not in COLUMN_BASE:
            return None, None
        return px, COLUMN_BASE[px] - 136
    elif mode == "self":
        if wx not in COLUMN_BASE:
            return None, None
        return wx, COLUMN_BASE[wx] - 136
    else:
        return None, None


def gather_wire_instances(target_i, col_mode="prev_lab"):
    """Walk r4_iindex_table.json, collect (route_key, wx, wy, col_start, cells_set)
    for every wire at target_i where prev_lab_x is known and route_cells has the key."""
    with open(IINDEX_PATH) as f:
        ti = json.load(f)
    with open(CELLS_PATH) as f:
        raw = json.load(f)
    cells_per_route = {k: set((o, b) for o, b in v) for k, v in raw.items()}

    # Key format mismatch:
    #   r4_iindex_table.json: "sx,sy,dx,dy,port"  (no dn, assumed 0)
    #   route_cells.json:     "sx,sy->dx,dy,dn,port"
    # Normalize r4_iindex keys to the route_cells form with dn=0.
    def _norm(k):
        parts = k.split(",")
        if len(parts) != 5:
            return None
        sx, sy, dx, dy, port = parts
        return f"{sx},{sy}->{dx},{dy},0,{port}"

    instances = []
    for route_key, wires in ti.items():
        nk = _norm(route_key)
        if nk is None:
            continue
        cells = cells_per_route.get(nk)
        if cells is None:
            continue
        for wx, wy, i in wires:
            if i != target_i:
                continue
            px, col_start = wire_col_start(wx, col_mode)
            if col_start is None:
                continue
            instances.append((route_key, wx, wy, px, col_start, cells))
    return instances


def score_base(instances, pair1, pair2):
    """Return (hits, total) for predicted-cell hits across wire instances."""
    hits = 0
    total = 0
    # Deduplicate per (route_key, wx, wy) so the same wire in the same route
    # only scores once (a route can list the wire twice in edge cases).
    seen = set()
    for rk, wx, wy, px, col_start, cells in instances:
        if (rk, wx, wy) in seen:
            continue
        seen.add((rk, wx, wy))
        preds = predicted_cells(wy, col_start, pair1, pair2)
        if not preds:
            continue
        total += 1
        # "Any hit" scoring: at least one of the 2 predicted cells present
        if any(p in cells for p in preds):
            hits += 1
    return hits, total


def brute_force(instances, pair1_range, deltas=(210, 419, 420, 421)):
    """Sweep (pair1, pair2=pair1+delta) and return top-20 by hit rate."""
    results = []
    for p1 in pair1_range:
        for d in deltas:
            p2 = p1 + d
            h, t = score_base(instances, p1, p2)
            if t == 0:
                continue
            results.append((h / t, h, t, p1, p2, d))
    results.sort(reverse=True)
    return results


def main():
    target_i = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    col_mode = sys.argv[2] if len(sys.argv) > 2 else "prev_lab"
    pair1_lo = int(sys.argv[3]) if len(sys.argv) > 3 else 2500
    pair1_hi = int(sys.argv[4]) if len(sys.argv) > 4 else 4500
    print(f"=== r4_remine I={target_i} col_mode={col_mode} "
          f"pair1∈[{pair1_lo},{pair1_hi}] ===")
    inst = gather_wire_instances(target_i, col_mode=col_mode)
    print(f"wire instances: {len(inst)}")
    if not inst:
        print("no instances — cannot mine")
        return

    # Deduplicated wire count
    unique_wires = len(set((rk, wx, wy) for rk, wx, wy, *_ in inst))
    prev_xs = Counter(px for *_, px, cs, _ in ((r, wx, wy, px, cs, c) for r, wx, wy, px, cs, c in inst))
    print(f"unique (route,wx,wy) wires: {unique_wires}")
    print(f"prev_x distribution: {dict(sorted(prev_xs.items()))}")

    # Brute force over a wide pair1 range. Prior bases fall in 2700..4300.
    print(f"\nbrute-forcing pair1 ∈ [{pair1_lo}, {pair1_hi}], delta ∈ {{210, 419, 420, 421}}...")
    pair1_range = range(pair1_lo, pair1_hi + 1)
    results = brute_force(inst, pair1_range)
    print("\nTop 15 candidates:")
    print(f"  {'rate':>7} {'hits':>5}/{'tot':<5} {'pair1':>6} {'pair2':>6} {'delta':>6}")
    for rate, h, t, p1, p2, d in results[:15]:
        print(f"  {rate:7.2%} {h:5d}/{t:<5d} {p1:6d} {p2:6d} {d:6d}")


if __name__ == "__main__":
    main()
