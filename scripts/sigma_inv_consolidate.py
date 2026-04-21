#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Consolidate all σ⁻¹ probe results into a single (foff, fb8, group) table.

Reads probe RBFs from:
  tmp/sigma_fb8_mine/face_X{x}_Y{y}/     (fb8={2,5,6})
  tmp/sigma_existing_groups/face_X{x}_Y{y}/  (fb8={0,1,3,4,7}, groups 0-4)
  tmp/multi_lut_X{x}_Y{y}/               (fb8={0,1,3,4,7}, groups 5-6)

Output: results/sigma_inv_fb8_groups.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import permutations
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
from config import cram_ctrl_addr, cram_ctrl_bit, cram_n_delta

MASK = 0xFACE
N_VALS = list(range(0, 32, 2))


def extract_from_probes(probe_dirs, nv):
    """Extract σ⁻¹ with (foff, fb8, group) key from probe RBFs."""
    table = {}
    errors = 0
    total = 0

    for probe_dir in probe_dirs:
        parts = probe_dir.name.split("_")
        x_str = [p for p in parts if p.startswith("X")][0]
        y_str = [p for p in parts if p.startswith("Y")][0]
        x = int(x_str[1:])
        y = int(y_str[1:])

        rbf_path = probe_dir / "output_files" / "probe.rbf"
        if not rbf_path.exists():
            continue
        probe = rbf_path.read_bytes()
        if len(probe) != 368011:
            continue

        slot = (y - 2) % 3
        group = (y - 2) // 3

        for n in N_VALS:
            total += 1
            k = n // 2
            nd = cram_n_delta(n)
            wrapped = slot == 1 and (24 + group * 3 + nd < 0)
            if wrapped:
                bp = 7 - group
                addr_adj = 207
            else:
                bp = cram_ctrl_bit(y)
                addr_adj = 0

            base = cram_ctrl_addr(x, y, 0, n) + addr_adj
            foff = (base - 32) % 210
            fb8 = ((base - 32) // 210) % 8

            best_si = None
            best_err = 17
            for si in permutations(range(4)):
                sigma = [0] * 4
                for i, j in enumerate(si):
                    sigma[j] = i
                err = 0
                for b in range(16):
                    f0 = (b >> sigma[0]) & 1
                    f1 = (b >> sigma[1]) & 1
                    f2 = (b >> sigma[2]) & 1
                    f3 = (b >> sigma[3]) & 1
                    pair = ((1 - f0) << 2) | ((1 - f1) << 1) | (1 - f2)
                    da = f3 ^ (1 - f2)
                    delta = da if k % 2 == 0 else 1 - da
                    addr = cram_ctrl_addr(x, y, pair, n) + delta + addr_adj
                    nv_bit = (nv[addr] >> bp) & 1
                    p_bit = (probe[addr] >> bp) & 1
                    d = nv_bit ^ p_bit
                    m = (MASK >> b) & 1
                    if d != m:
                        err += 1
                if err < best_err:
                    best_err = err
                    best_si = si

            key = (foff, fb8, group)
            if best_err > 0:
                errors += 1
            else:
                if key in table and table[key] != best_si:
                    print(f"  CONFLICT at {key}: {table[key]} vs {best_si}")
                table[key] = best_si

    return table, total, errors


def main():
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    assert len(nv) == 368011

    # Collect all probe directories
    probe_dirs = []

    # fb8={2,5,6} probes
    d1 = REPO / "tmp" / "sigma_fb8_mine"
    if d1.exists():
        probe_dirs.extend(sorted(d1.glob("face_X*_Y*")))

    # fb8={0,1,3,4,7} groups 0-4 probes
    d2 = REPO / "tmp" / "sigma_existing_groups"
    if d2.exists():
        probe_dirs.extend(sorted(d2.glob("face_X*_Y*")))

    # Existing probes (groups 5-6)
    d3 = REPO / "tmp"
    probe_dirs.extend(sorted(d3.glob("multi_lut_X*_Y*")))

    print(f"Found {len(probe_dirs)} probe directories")

    table, total, errors = extract_from_probes(probe_dirs, nv)

    # Stats
    by_fb8_group = defaultdict(int)
    by_fb8 = defaultdict(int)
    for (foff, fb8, group) in table:
        by_fb8_group[(fb8, group)] += 1
        by_fb8[fb8] += 1

    print(f"\nTotal positions: {total}, errors: {errors}")
    print(f"Unique (foff, fb8, group) entries: {len(table)}")
    print(f"\nPer fb8:")
    for fb8 in sorted(by_fb8.keys()):
        print(f"  fb8={fb8}: {by_fb8[fb8]} entries")
    print(f"\nPer (fb8, group):")
    for (fb8, group) in sorted(by_fb8_group.keys()):
        print(f"  fb8={fb8}, group={group}: {by_fb8_group[(fb8, group)]}")

    # Save
    output = {
        "description": "σ⁻¹ permutation table keyed by (foff, fb8, group)",
        "key_format": "(foff, fb8, group) where group = (y-2)//3",
        "total_entries": len(table),
        "entries": {}
    }
    for (foff, fb8, group), si in sorted(table.items()):
        k = f"{foff},{fb8},{group}"
        output["entries"][k] = {
            "foff": foff, "fb8": fb8, "group": group,
            "sigma_inv": list(si)
        }

    out_path = REPO / "results" / "sigma_inv_fb8_groups.json"
    out_path.write_text(json.dumps(output, indent=1))
    print(f"\nSaved to {out_path}")

    # Coverage check
    print(f"\nCoverage gaps:")
    for fb8 in range(8):
        for group in range(7):
            count = by_fb8_group.get((fb8, group), 0)
            if count == 0:
                print(f"  fb8={fb8}, group={group}: NO DATA")
            elif count < 10:
                print(f"  fb8={fb8}, group={group}: only {count} entries")


if __name__ == "__main__":
    main()
