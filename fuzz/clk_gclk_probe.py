# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.3 experiment 1 — GCLK_IN → GCLK_BUS → LAB_CLK_SEL connectivity.

Strategy:
  For a sweep of N dst LAB sinks, compile the SAME (lut1→lut2) route twice:
    A. Unclocked (compile_route_pair_single_input) — no CLK port
    B. Clocked   (compile_route_pair_single_input_clocked) — CLK registers Q

Then diff A vs B at the CRAM level. All routing, LUT TT, and LI cells are
identical by construction (same placement, same masks, same connect_port).
The ONLY thing B adds is: register enable on lut2's LE + the global clock
routing path from the dedicated CLK pin → LAB clock MUX.

Per user tip:
  - Filter CRAM-only (off >= 5282) — clock-tree bits often hide in the
    header band at the chip center; the noise floor there makes any
    header-band finding fiction. (Phase 5.0 null test.)
  - Expect bits concentrated near the center column (X=15) = clock spine.
    Frequency-by-column report is the primary diagnostic.

Output: results/clk_gclk_probe.json
  {
    "sites": [...],
    "per_site_cells": {"sx,sy,sn": [[off,bp],...]},
    "union": [[off,bp],...],
    "intersection": [[off,bp],...],   # candidate GCLK global bits
    "column_histogram": {x: count},
  }
"""
import json, os, sys
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import (
    compile_route_pair_single_input,
    compile_route_pair_single_input_clocked,
)
from config import COLUMN_BASE

REPO = Path(__file__).resolve().parent.parent
RBF = REPO / "results" / "rbf"
OUT = REPO / "results" / "clk_gclk_probe.json"

HDR_FRAMES = 25
HDR = 32 + HDR_FRAMES * 210       # 5282 — first byte of true CRAM
CRC_SLOT = 208                    # positions 208/209 of each frame are CRC

# 8 dst sinks distributed across the die so we can see LAB clock MUX
# activation in different LABs. Source fixed at (10,10) — known-good.
SRC = (10, 10, 0)
SINKS = [
    (7, 6, 0),   # upper-left quadrant
    (13, 6, 0),  # upper-right
    (7, 14, 0),  # lower-left
    (13, 14, 0), # lower-right
    (16, 10, 0), # center-east
    (10, 4, 0),  # direct north
    (10, 16, 0), # direct south
    (22, 10, 0), # far east
]


def cram_diff(a: bytes, b: bytes) -> set:
    """CRAM-only XOR diff, CRC bytes excluded."""
    out = set()
    for i in range(HDR, min(len(a), len(b))):
        if (i - 32) % 210 >= CRC_SLOT:
            continue
        x = a[i] ^ b[i]
        if x:
            for bp in range(8):
                if (x >> bp) & 1:
                    out.add((i, bp))
    return out


def classify_col(off: int) -> int | None:
    for x, base in sorted(COLUMN_BASE.items(), key=lambda kv: kv[1]):
        cs = base - 136
        if cs <= off < cs + 7350:
            return x
    return None


def ensure_pair(sx, sy, sn, dx, dy, dn):
    """Compile both variants if not cached. Returns (unclocked_rbf, clocked_rbf)."""
    utag = f"clkprobe_U_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}_datab"
    ctag = f"clkprobe_C_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}_datab"
    up = RBF / f"{utag}.rbf"
    cp = RBF / f"{ctag}.rbf"
    if not up.exists():
        print(f"  compile U {utag}", flush=True)
        r, t, err = compile_route_pair_single_input(
            utag, sx, sy, sn, dx, dy, dn, connect_port="datab")
        if not r:
            return None, None, f"U fail: {(err or '')[:100]}"
    if not cp.exists():
        print(f"  compile C {ctag}", flush=True)
        r, t, err = compile_route_pair_single_input_clocked(
            ctag, sx, sy, sn, dx, dy, dn, connect_port="datab")
        if not r:
            return None, None, f"C fail: {(err or '')[:100]}"
    return up.read_bytes(), cp.read_bytes(), None


def main():
    print(f"=== Phase 5.3 GCLK probe ===")
    print(f"src={SRC}  sinks={len(SINKS)}  (compile ~30s each × 2 variants)")

    per_site = {}
    all_sets = []
    for dx, dy, dn in SINKS:
        key = f"{dx},{dy},{dn}"
        print(f"\n[{key}]", flush=True)
        u, c, err = ensure_pair(*SRC, dx, dy, dn)
        if err:
            print(f"  {err}")
            continue
        diff = cram_diff(u, c)
        # Drop any cells inside the source or dst LAB's own CRAM column —
        # those are LUT TT / LE register-mode bits, not the clock network.
        # Keep everything else as candidate clock-net cells.
        lab_cols_excluded = {SRC[0], dx}
        clock_candidates = {(off, bp) for (off, bp) in diff
                            if classify_col(off) not in lab_cols_excluded}
        per_site[key] = sorted(clock_candidates)
        all_sets.append(clock_candidates)
        print(f"  full diff: {len(diff)} cells  "
              f"clock candidates: {len(clock_candidates)}")

    if not all_sets:
        print("no data")
        return

    union = set().union(*all_sets)
    inter = set.intersection(*all_sets) if all_sets else set()

    # Column histogram over the union (where are the bits living?)
    col_hist = Counter()
    for off, bp in union:
        c = classify_col(off)
        col_hist[c] += 1

    print(f"\n=== Summary ===")
    print(f"  union      : {len(union)} cells")
    print(f"  intersection (GCLK global candidates): {len(inter)}")
    print(f"\n  column histogram (union):")
    for col, n in sorted(col_hist.items(),
                          key=lambda kv: (kv[0] is None, kv[0])):
        tag = "non-LAB" if col is None else f"X={col}"
        marker = "  <-- SPINE?" if col == 15 else ""
        print(f"    {tag:>10}  {n:4d}{marker}")

    # Frame-region breakdown for the intersection (where clock bits cluster)
    if inter:
        frame_hist = Counter()
        for off, bp in inter:
            frame = (off - 32) // 210
            frame_hist[frame // 50 * 50] += 1  # 50-frame buckets
        print(f"\n  intersection frame-band buckets (bucket_start : count):")
        for b, n in sorted(frame_hist.items()):
            print(f"    frames {b:4d}..{b+49:4d}: {n}")

    OUT.write_text(json.dumps({
        "src": list(SRC),
        "sinks": [list(s) for s in SINKS],
        "per_site_cells": {k: [list(c) for c in v] for k, v in per_site.items()},
        "union": sorted([list(c) for c in union]),
        "intersection": sorted([list(c) for c in inter]),
        "column_histogram": {str(k): v for k, v in col_hist.items()},
    }, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
