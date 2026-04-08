# SPDX-License-Identifier: GPL-3.0-or-later
"""Analyze LI input-MUX port-select bits via multi-port route XOR-diff.

Given lits_pair_{src}_to_{dst}_{port}.rbf files at the same (src,dst) for
multiple ports, compute:

    diff(port) = cells(port) XOR cells(datab)

Cells that are present in diff(dataa) but NOT in diff(datac) / diff(datad)
are the bits that specifically select port=dataa. Intersection across many
destinations reveals the universal port-select bit positions per (dx,dy,dn).

Output: results/port_mux_cells.json
  { "(dx,dy,dn)": { "dataa": [[off,bp],...], "datac": [...], "datad": [...] } }
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RBF_DIR = Path(REPO) / "results" / "rbf"

PAT = re.compile(r"lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf$")


def read_bytes(p):
    return p.read_bytes()


def xor_cells(a, b):
    """Return set of (offset, bit) that differ between two RBFs."""
    out = set()
    for i in range(len(a)):
        d = a[i] ^ b[i]
        if d:
            for bp in range(8):
                if d & (1 << bp):
                    out.add((i, bp))
    return out


def main():
    # Index all multi-port groups
    by_group = defaultdict(dict)  # (sx,sy,dx,dy,dn) -> {port: path}
    for f in RBF_DIR.iterdir():
        m = PAT.match(f.name)
        if not m:
            continue
        sx, sy, dx, dy, dn, port = m.groups()
        by_group[(sx, sy, dx, dy, dn)][port] = f

    # Filter out header frames 0..24 (bytes 32..5281): IO/global-config live
    # there and dominate port-diff top hits. LUT TT + LI MUX are all in CRAM
    # frames 25..1751 (byte >= 5282).
    HEADER_END = 32 + 25 * 210  # 5282

    def cram_only(cells):
        return {c for c in cells if c[0] >= HEADER_END}

    # For each (src,dst) group compute diff(port vs datab) for all available
    # ports, then extract port-UNIQUE cells (cells in one port's diff but not
    # in any other port's diff at the same src,dst). This cancels both (a)
    # route infrastructure shared between ports and (b) LUT TT cells that
    # behave similarly across mask changes.
    dst_ports = defaultdict(lambda: defaultdict(list))
    n_groups = 0
    for key, pmap in by_group.items():
        if "datab" not in pmap or len(pmap) < 2:
            continue
        sx, sy, dx, dy, dn = key
        bdata = read_bytes(pmap["datab"])
        per_port_diff = {}
        for port, path in pmap.items():
            if port == "datab":
                continue
            per_port_diff[port] = cram_only(xor_cells(bdata, read_bytes(path)))
        if len(per_port_diff) < 2:
            continue  # need at least 2 non-datab ports for uniqueness subtraction
        for port, diff in per_port_diff.items():
            others = set()
            for op, od in per_port_diff.items():
                if op != port:
                    others |= od
            unique = diff - others
            dst_ports[(dx, dy, dn)][port].append(unique)
        n_groups += 1

    print(f"scanned {n_groups} multi-port route groups")

    # For each (dst, port) find cells consistently present (intersection across sources)
    result = {}
    for dst, pmap in dst_ports.items():
        entry = {}
        for port, diff_list in pmap.items():
            if not diff_list:
                continue
            inter = set(diff_list[0])
            for d in diff_list[1:]:
                inter &= d
            entry[port] = {
                "n_sources": len(diff_list),
                "intersection_size": len(inter),
                "cells": sorted(inter),
            }
        if entry:
            result[f"{dst[0]},{dst[1]},{dst[2]}"] = entry

    out = Path(REPO) / "results" / "port_mux_cells.json"
    out.write_text(json.dumps(result, indent=1))
    print(f"wrote {out}  ({len(result)} destinations)")

    # Summary
    port_sizes = defaultdict(list)
    for dst, pmap in result.items():
        for port, info in pmap.items():
            port_sizes[port].append(info["intersection_size"])
    for port, sizes in sorted(port_sizes.items()):
        if sizes:
            print(f"  {port}: n={len(sizes):3d}  intersection mean={sum(sizes)/len(sizes):.1f}"
                  f"  min={min(sizes)}  max={max(sizes)}")

    # Cross-destination universality check: for each port, intersect the
    # intersection-cells across all destinations — a truly universal port-select
    # bit should show up here.
    print("\n=== cross-destination cell overlap (universality test) ===")
    for port in sorted({p for pm in result.values() for p in pm}):
        all_cells = [set(map(tuple, info["cells"]))
                     for dst, pm in result.items()
                     for p, info in pm.items() if p == port and info["cells"]]
        if not all_cells:
            continue
        inter = set(all_cells[0])
        for c in all_cells[1:]:
            inter &= c
        # Pairwise overlap histogram
        counts = defaultdict(int)
        for cs in all_cells:
            for c in cs:
                counts[c] += 1
        top = sorted(counts.items(), key=lambda x: -x[1])[:5]
        print(f"  {port}: {len(all_cells)} dsts, strict-universal={len(inter)}, "
              f"top-5 shared cells: {[(f'0x{c[0][0]:05x}.{c[0][1]}', c[1]) for c in top]}")


if __name__ == "__main__":
    sys.exit(main() or 0)
