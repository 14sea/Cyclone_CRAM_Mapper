# SPDX-License-Identifier: GPL-3.0-or-later
"""Decompose results/iob_route_cells.json deltas.

Each raw entry `IOB_<pin>-><dx>,<dy>,<dn>,<port>` is
  cells(pair) XOR cells(zero)
where
  pair : IOB_<pin> routed to (dx,dy,dn).<port>
  zero : IOB_<pin> routed to zero_lab.dataa

So the raw delta fuses TWO fabric routes (target + zero_lab). To get
the absolute target-route cells we can try:

  (1) Pair-of-pairs: if two pins P1 and P2 both go to the same target
      and the same zero_lab, then (delta_P1 XOR delta_P2) cancels the
      shared zero_lab component (same LE, same MUX), leaving
      (R(P1->target) XOR R(P2->target)) + (R(P1->zero_lab) XOR R(P2->zero_lab))
      which is a SYMMETRIC diff of the two fabric paths, comparable to
      what we already know from golden-pair diffs.

  (2) Triangulation via known SLICE->(target) entries: the sig-cache
      has `4,4,0->10,4,0,dataa` (50 cells). If the LI-MUX "select
      dataa" component is invariant across sources, we can subtract
      the 17-cell common intersection (14 baseline + 3 dataa-select)
      from both sides and compare what remains.

This script reports:
  * Raw delta sizes
  * Pair-of-pairs symmetric diffs between same-target, different-src
  * Overlap of each delta with the 17-cell SLICE->(target) intersection
  * Cross-entries that share cells (useful to spot the zero_lab's
    fabric as the common component)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def tup(cells):
    return {tuple(c) for c in cells}


def load_sigcache_intersection(dx, dy, dn, port, sigcache_path):
    cache = json.loads(sigcache_path.read_text())
    matches = []
    for k, v in cache.items():
        if k.endswith(f"->{dx},{dy},{dn},{port}"):
            matches.append((k, tup(v)))
    if len(matches) < 2:
        return matches, None
    shared = set.intersection(*[s for _, s in matches])
    return matches, shared


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result-json",
                    default=str(REPO / "results" / "iob_route_cells.json"))
    ap.add_argument("--sigcache",
                    default=str(REPO / "results" / "route_cells_full.json"))
    args = ap.parse_args()

    raw = json.loads(Path(args.result_json).read_text())
    routes = raw["routes"]
    meta = raw["meta"]
    print(f"[meta] zero_lab={meta['zero_lab']} sec_src={meta['sec_src_pin']} "
          f"sink={meta['primary_sink']}/{meta['sec_sink']}")
    print(f"[raw] {len(routes)} entries\n")

    for key, cells in routes.items():
        print(f"  {key:45s} {len(cells)} cells")

    # Group by target for pair-of-pair comparison
    by_target = defaultdict(list)
    for key, cells in routes.items():
        # IOB_<pin>-><dx>,<dy>,<dn>,<port>
        _, tail = key.split("->")
        dx, dy, dn, port = tail.split(",")
        pin = key.split("->")[0][4:]  # strip "IOB_"
        by_target[(dx, dy, dn, port)].append((pin, tup(cells)))

    print("\n[pair-of-pairs] symmetric diffs between same-target pins:")
    for (dx, dy, dn, port), pairs in sorted(by_target.items()):
        if len(pairs) < 2:
            continue
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                pa, ca = pairs[i]
                pb, cb = pairs[j]
                symdiff = ca ^ cb
                shared = ca & cb
                print(f"  ({dx},{dy},{dn},{port}) {pa}<>{pb}: "
                      f"symdiff={len(symdiff)} shared={len(shared)}")

    # SLICE -> target intersection hint
    sc_path = Path(args.sigcache)
    if sc_path.exists():
        print("\n[vs. SLICE sig-cache] overlap with SLICE->target intersection:")
        for (dx, dy, dn, port), pairs in sorted(by_target.items()):
            matches, shared = load_sigcache_intersection(
                int(dx), int(dy), int(dn), port, sc_path)
            if not matches:
                continue
            print(f"  target ({dx},{dy},{dn},{port}): "
                  f"{len(matches)} SLICE entries, "
                  f"{len(shared) if shared else 'n/a'}-cell intersection")
            if shared is None:
                continue
            for pin, cells in pairs:
                overlap = cells & shared
                print(f"    IOB_{pin}: {len(overlap)}/{len(shared)} shared "
                      f"cells present in delta ({len(cells)} total)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
