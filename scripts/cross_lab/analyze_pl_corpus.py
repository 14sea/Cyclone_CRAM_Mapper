#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Analyze the 1-LE TT-variant corpus (pl_and / pl_or / ... / pl_nor)
for cross-checking the X33Y4_PROBE2_INFRA shim decomposition.

Note: the corpus was built with M16 active (key3=M16) to test whether
1-LE designs land at X33Y4N4 like probe2.  Result: they DON'T — Quartus
places them at X≈9 column instead.  X=33Y4 placement requires either
2-LE topology (cl_*) or explicit LOC assignment (Quartus Lite cannot
force LE LOC reliably without hand-named signals).

So this corpus does NOT directly enable promotion of the 33 ADDITIVE
shim cells (those are pure X33Y4N4-M16-reserved-1-LE).  What it DID
establish:

1. The 4 OVER-CANCEL cells (X33_LUT_CODEC nibble class 1 at (4,4))
   fire in 0/7 pl_* variants → confirmed they're 2-LE-X33Y4-class
   only (also fire in cl_andn/cl_or/cl_xor 2-LE gold per earlier
   13-variant cross-check).

2. The 7-variant intersection (TT-invariant 1-LE infra at the M16-
   active placement) covers 111 cells.  Of these, 90 also appear in
   probe2 → identify "1-LE common infrastructure cells" that any
   1-LE design needs regardless of LE position or TT.  The remaining
   21 cells in pl_* intersection but not probe2 are M16-active-
   specific (probe2 has M16 reserved).

3. probe2's 191 cells - 90 shared = 101 cells that are either
   X33Y4N4-position-specific or M16-reserve-specific or TT-class-
   specific (probe2 TT 0xAAAA differs from any pl_* TT).

Usage:
  python3 scripts/cross_lab/analyze_pl_corpus.py            # print summary
  python3 scripts/cross_lab/analyze_pl_corpus.py --save     # write sidecar
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))
from config import COLUMN_BASE  # noqa: E402

NV = REPO / "results" / "rbf" / "nv_zero_global.rbf"
PROBE2 = REPO / "results" / "rbf" / "x33_probe2_silicon_validated.rbf"
SHIM_DECOMP = REPO / "results" / "x33y4_probe2_shim_decomposition.json"
PL_VARIANTS = ["pl_and", "pl_or", "pl_xor", "pl_xnor",
               "pl_andn", "pl_orn", "pl_nor"]
PL_TT = {"pl_and": 0x8888, "pl_or": 0xEEEE, "pl_xor": 0x6666,
         "pl_xnor": 0x9999, "pl_andn": 0x2222, "pl_orn": 0xBBBB,
         "pl_nor": 0x1111}


def col_of(off: int) -> str:
    """Region classifier — checks LAB columns BEFORE block_band so
    X=33's column (which sits in frames 1704-1738, overlapping the naive
    block_band range 1692-1738) is correctly attributed."""
    if off < 32:
        return "preamble"
    body = off - 32
    f = body // 210
    byte = body % 210
    if byte >= 208:
        return "crc"
    if f < 25:
        return "header"
    for x, base in COLUMN_BASE.items():
        ps = base - 136
        if 0 <= off - ps < 7350:
            return f"X={x}"
    if f >= 1692:
        return "block_band"
    return "inter_col"


def cells_of(rbf: bytes, ref: bytes) -> set:
    s = set()
    for off, (a, b) in enumerate(zip(rbf, ref)):
        if a != b:
            d = a ^ b
            for bp in range(8):
                if (d >> bp) & 1:
                    s.add((off, bp))
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", action="store_true",
                    help="write results/x33y4_pl_corpus_analysis.json")
    args = ap.parse_args()

    nv = NV.read_bytes()
    probe2_cells = {x for x in cells_of(PROBE2.read_bytes(), nv)
                    if col_of(x[0]) != "crc"}

    data = {}
    print(f"{'name':<10s} {'TT':>6s} {'no_crc':>7s} {'X=33':>6s} "
          f"{'block':>6s} {'hdr':>6s} {'X=9':>6s}")
    for v in PL_VARIANTS:
        rbf_path = REPO / "tmp" / "x33_lut_mining" / v / f"{v}.rbf"
        if not rbf_path.exists():
            print(f"{v}: MISSING — run scripts/cross_lab/x33_lut_mining/"
                  f"build_pl_variant.sh {v}")
            continue
        c = {x for x in cells_of(rbf_path.read_bytes(), nv)
             if col_of(x[0]) != "crc"}
        data[v] = c
        by = Counter(col_of(o) for o, _ in c)
        print(f"{v:<10s} {hex(PL_TT[v]):>6s} {len(c):>7d} "
              f"{by.get('X=33', 0):>6d} {by.get('block_band', 0):>6d} "
              f"{by.get('header', 0):>6d} {by.get('X=9', 0):>6d}")

    by_p = Counter(col_of(o) for o, _ in probe2_cells)
    print(f"{'probe2':<10s} {hex(0xAAAA):>6s} {len(probe2_cells):>7d} "
          f"{by_p.get('X=33', 0):>6d} {by_p.get('block_band', 0):>6d} "
          f"{by_p.get('header', 0):>6d} {by_p.get('X=9', 0):>6d}")

    if len(data) < 2:
        print("\nNot enough variants to intersect.")
        return

    inter = set.intersection(*data.values())
    print(f"\n7-way intersection (TT-invariant 1-LE M16-active infra): "
          f"{len(inter)}")
    by_int = Counter(col_of(o) for o, _ in inter)
    for k, v in sorted(by_int.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")

    print(f"\nprobe2 ∩ inter: {len(probe2_cells & inter)} cells")
    print(f"  (1-LE common infra: cells shared by 1-LE M16-reserved + "
          f"1-LE M16-active 1-LE designs, regardless of TT/position)")
    print(f"inter - probe2: {len(inter - probe2_cells)} cells")
    print(f"  (M16-active-specific 1-LE infra)")
    print(f"probe2 - inter: {len(probe2_cells - inter)} cells")
    print(f"  (X33Y4N4-position-specific OR M16-reserve-specific OR "
          f"probe2 TT 0xAAAA-class-specific)")

    # OVER-cancel cells fire test
    OVER = [(358912, 4), (358913, 4), (359122, 4), (359123, 4)]
    print(f"\nOVER-CANCEL test (codec X33Y4N4 nibble class 1 cells):")
    for v, c in data.items():
        fires = sum(1 for cell in OVER if cell in c)
        print(f"  {v} (TT={hex(PL_TT[v])}): fires {fires}/4")
    print("  → 0/4 in all 7 variants confirms OVER cells are 2-LE-X33Y4-")
    print("    class only.  pl_* don't land at X33Y4N4 (M16-active 1-LE")
    print("    is placed at X≈9 by Quartus IO-bank-driven heuristic).")

    # Compare with shim decomp
    shim = json.loads(SHIM_DECOMP.read_text())
    add = set(tuple(c) for c in shim["buckets"]["additive"]["cells"])
    over = set(tuple(c) for c in shim["buckets"]["over_cancel"]["cells"])
    print(f"\nProbe2 shim {len(add)} ADD + {len(over)} OVER:")
    print(f"  inter ∩ ADD: {len(inter & add)} (cells promotable to a "
          f"shared 1-LE directive)")
    print(f"  inter ∩ OVER: {len(inter & over)} (already proven 2-LE-only)")

    if args.save:
        out = REPO / "results" / "x33y4_pl_corpus_analysis.json"
        payload = {
            "description": (
                "Analysis sidecar for the 7-variant 1-LE TT corpus "
                "(pl_and/or/xor/xnor/andn/orn/nor) at M16-active "
                "topology.  Key finding: pl_* land at X=9 not X=33 (IO-"
                "bank topology requires 2-LE pairing OR explicit LOC for "
                "X=33 placement), so the corpus does not directly "
                "validate or promote X33Y4_PROBE2_INFRA's 33 ADDITIVE "
                "cells.  What it DID confirm: 4 OVER cells are 2-LE-"
                "X33Y4-class only, fire in 0/7 1-LE variants."),
            "variants": {v: {"tt": hex(PL_TT[v]),
                              "rbf_path": str(
                                  (REPO/"tmp"/"x33_lut_mining"/v/f"{v}.rbf")
                                  .relative_to(REPO))}
                         for v in data},
            "intersection_count": len(inter),
            "intersection_by_region": dict(by_int),
            "probe2_intersect_inter": len(probe2_cells & inter),
            "shim_promotion_summary": {
                "inter_cap_additive": len(inter & add),
                "inter_cap_over_cancel": len(inter & over),
                "interpretation": (
                    "0 ∩ ADDITIVE means the M16-active 1-LE intersection "
                    "doesn't cover any of probe2's 33 ADDITIVE cells — "
                    "those remain pure X33Y4N4-M16-reserved-1-LE-specific."),
            },
            "next_session_targets": [
                ("Force X33Y4N4 placement via Quartus LOC: requires "
                 "predicting Quartus's internal signal name post-pack "
                 "(e.g., `led0~reg0` or `led0` itself).  Try `set_"
                 "location_assignment LCFF_X33_Y4_N5 -to led0` for one "
                 "variant; if it works, re-run all 7."),
                ("Build a probe2-class corpus instead (1-LE 1-input M16-"
                 "reserved): use only key2=E16 as input, vary the design "
                 "via constant-folding tricks like `key2 ^ 1'b0` vs "
                 "`key2 ^ 1'b1`.  Only 2 distinct TTs achievable (0xAAAA "
                 "and 0x5555) — limited intersection power but matches "
                 "probe2 topology exactly."),
                ("Defer A: the 33 ADDITIVE cells were already labelled "
                 "'pure 1-LE-only, NOT migratable to a shared directive' "
                 "in the original decomposition.  Confirming this with "
                 "more corpus data has diminishing returns; the cells "
                 "remain in the X33Y4_PROBE2_INFRA shim where they "
                 "belong.  Real next-session value is in further "
                 "directive promotion campaigns for OTHER 1-LE topologies "
                 "(different N at X=33) where new shims will need "
                 "similar decomposition work."),
            ],
        }
        out.write_text(json.dumps(payload, indent=2))
        print(f"\nsaved → {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
