# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-pin spine check — is there a shared GCLK_BUS spine or not?

Recomputes forced-vs-auto sink-indep intersections using cached RBFs
from the clk_force_gclk_probe + clk_iob_subtract_probe RBF sets.  For
each CLK pin we have forced RBFs (fgclk_FORCE_*) and auto RBFs
(fgclk_AUTO_{pin}_*); the intersection of forced-vs-auto diffs across
sinks tells us which cells flip when THAT pin becomes a GCLK source.

If those per-pin sets overlap, the overlap is a universal "any-pin
GCLK activation" spine.  If they don't, the encoding is per-pin
one-hot and there is no universal spine.

Uses only cached RBFs; no new Quartus runs.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clk_iob_subtract_probe import cram_diff

REPO = Path(__file__).resolve().parent.parent
RBF = REPO / "results" / "rbf"
OUT = REPO / "results" / "clk_cross_pin_spine_check.json"

SRC = (10, 10, 0)
SINKS = [(10, 4, 0), (10, 16, 0), (22, 10, 0)]

# (pin, forced_tag_prefix, auto_tag_prefix)
PIN_SETS = [
    ("PIN_E1", "fgclk_FORCE",    "fgclk_AUTO"),
    ("PIN_R8", "fgclk_R8",       "fgclk_AUTO_R8"),
]


def forced_vs_auto_inter(forced_prefix: str, auto_prefix: str) -> set:
    per_sink = []
    for (dx, dy, dn) in SINKS:
        sx, sy, sn = SRC
        tag = f"X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        f = (RBF / f"{forced_prefix}_{tag}.rbf").read_bytes()
        a = (RBF / f"{auto_prefix}_{tag}.rbf").read_bytes()
        per_sink.append(cram_diff(a, f))
    return set.intersection(*per_sink) if per_sink else set()


def main():
    print("=== Cross-pin GCLK 'spine' check ===")
    sets = {}
    for pin, fp, ap in PIN_SETS:
        inter = forced_vs_auto_inter(fp, ap)
        sets[pin] = inter
        print(f"\n{pin} forced-vs-auto sink-indep intersection: {len(inter)} cells")
        for off, bp in sorted(inter):
            frame = (off - 32) // 210
            print(f"  off={off:6d} bp={bp}  frame={frame}")

    if len(sets) < 2:
        return
    keys = list(sets)
    overlap = set.intersection(*sets.values())
    union = set.union(*sets.values())
    print(f"\n=== Overlap ===")
    print(f"  union       : {len(union)} cells")
    print(f"  all-pin overlap (universal spine) : {len(overlap)} cells")
    for off, bp in sorted(overlap):
        frame = (off - 32) // 210
        print(f"    off={off:6d} bp={bp}  frame={frame}")
    if not overlap:
        print("  => NO universal GCLK spine — encoding is per-pin one-hot")

    OUT.write_text(json.dumps({
        "src": list(SRC),
        "sinks": [list(s) for s in SINKS],
        "per_pin_forced_vs_auto_intersection": {
            pin: sorted([list(c) for c in cells])
            for pin, cells in sets.items()
        },
        "universal_spine_overlap": sorted([list(c) for c in overlap]),
        "per_pin_union": sorted([list(c) for c in union]),
    }, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
