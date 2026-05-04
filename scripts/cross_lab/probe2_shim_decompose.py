#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decompose the probe2.v X=33Y4 1-LE shim into actionable buckets.

The 37-cell `results/x33y4_probe2_infra.json` shim is currently a flat
list applied as a topology-specific XOR delta when probe2.v 1-LE shape
is detected at SLICE_X33_Y4_N4.  Decomposition surfaces what each cell
is actually doing — additive (Quartus has the bit, open toolchain
doesn't emit) vs cancellation (open toolchain over-emits, Quartus
doesn't have the bit) — so future per-directive mining can replace the
shim slice by slice.

Companion / complement to scripts/cross_lab/x33_shim_decompose.py
(which decomposes the 57-cell cl_and 2-LE shim).  That tool can use 13
TT-variant builds to identify the TT-invariant subset; we don't yet
have an analogous variant corpus for the 1-LE class, so this tool
relies on:
  1. Quartus silicon-validated probe2.rbf (single gold reference).
  2. Per-directive layered emission of the open-toolchain build to
     attribute OVER-cancel cells to the directive that emits them.
  3. Source cross-check against existing codec data files
     (x33_lut_codec, output_route_sigcache, iob_to_slice_sigcache,
     iob_clk_pin_hdr, IOB_PAD_NV, IOB_RESERVE_PIN_M16, etc.).

Output: 4 disjoint buckets covering all 37 shim cells, plus a per-cell
attribution table mapping each OVER-cancel cell to the codec data file
(directive) that emits it.  Saved to
`results/x33y4_probe2_shim_decomposition.json` so future mining
campaigns can lift cells out of the shim into proper sigcache entries.

Usage:
  python3 scripts/cross_lab/probe2_shim_decompose.py            # print summary
  python3 scripts/cross_lab/probe2_shim_decompose.py --save     # write sidecar
  python3 scripts/cross_lab/probe2_shim_decompose.py --verify   # disjoint+full
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

ZERO = REPO / "results" / "rbf" / "nv_zero_global.rbf"
GOLD = REPO / "results" / "rbf" / "x33_probe2_silicon_validated.rbf"
SHIM = REPO / "results" / "x33y4_probe2_infra.json"
RESULTS = REPO / "results"


def cells_of(rbf_bytes: bytes, ref_bytes: bytes) -> set:
    s = set()
    for off, (a, b) in enumerate(zip(rbf_bytes, ref_bytes)):
        d = a ^ b
        if d:
            for bp in range(8):
                if (d >> bp) & 1:
                    s.add((off, bp))
    return s


def col_of(off: int) -> str:
    if off < 32:
        return "preamble"
    body = off - 32
    f = body // 210
    if f >= 1692:
        return "block_band"
    if f < 25:
        return "header_frame"
    for x, base in COLUMN_BASE.items():
        ps = base - 136
        if 0 <= off - ps < 7350:
            return f"X={x}"
    return "inter_col"


def load_directive_cells():
    """For each codec data file probe2 directives consume, return the
    subset of cells the directive would actually emit for the probe2
    topology (mask=0xAAAA at X33Y4N4, etc.).  Returns dict
    {directive_name: set((off, bp), ...)}."""
    out = {}

    # X33_LUT_CODEC X33Y4N4 with mask 0xAAAA → fires nibble classes 1 and 3
    d = json.loads((RESULTS / "x33_lut_codec.json").read_text())
    p44 = d["positions"]["(4, 4)"]
    nc = p44["nibble_classes"]
    mask = 0xAAAA  # probe2 LUT TT
    fired = set()
    for k in range(4):
        if (mask >> k) & 0x1111:
            for cell in nc[str(k)]:
                fired.add(tuple(cell))
    out["X33_LUT_CODEC_X33Y4N4_mask0xAAAA"] = fired

    # OUTROUTE_G15 X33Y4N4
    d = json.loads((RESULTS / "output_route_sigcache.json").read_text())
    or_cells = set()
    if "X33Y4N4" in d.get("routes", {}):
        or_cells |= set(tuple(c) for c in d["routes"]["X33Y4N4"]["position_specific"])
    or_cells |= set(tuple(c) for c in d.get("g15_invariant_cells", []))
    out["OUTROUTE_G15_X33Y4N4"] = or_cells

    # LAB_CLK_SEL X33Y4 — only the lab_clk_sel key is emitted
    d = json.loads((RESULTS / "clk_lab_sel_probe_X33Y4.json").read_text())
    out["LAB_CLK_SEL_X33Y4"] = set(tuple(c) for c in d.get("lab_clk_sel", []))

    # GCLK_PIN PIN_E1
    d = json.loads((RESULTS / "clk_cross_pin_spine_check.json").read_text())
    e1 = d["per_pin_forced_vs_auto_intersection"].get("E1", [])
    out["GCLK_PIN_E1"] = set(tuple(c) for c in e1)

    # IOB_CLK_INPUT PIN_E1
    d = json.loads((RESULTS / "iob_clk_pin_hdr_cells.json").read_text())
    out["IOB_CLK_INPUT_E1"] = set(tuple(c) for c in d["cells"]["E1"])

    # IOB_PAD_NV
    d = json.loads((RESULTS / "output_route_nv_mining.json").read_text())
    out["IOB_PAD_NV"] = set(tuple(c) for c in d["iob_pad_cells"])

    # IOB_RESERVE_PIN_M16 (all 4 groups, 66+ cells)
    d = json.loads((RESULTS / "iob_reserve_pin_m16_cells.json").read_text())
    m16 = set()
    def walk(n):
        if isinstance(n, list):
            if n and isinstance(n[0], int) and len(n) == 2:
                m16.add(tuple(n))
            else:
                for x in n: walk(x)
        elif isinstance(n, dict):
            for v in n.values(): walk(v)
    walk(d)
    out["IOB_RESERVE_PIN_M16"] = m16

    # cl_and 2-LE shim cells (not emitted for probe2 — gating excludes
    # — but useful to know overlap)
    d = json.loads((RESULTS / "x33y4_infra_override.json").read_text())
    out["X33Y4_CROSS_LAB_SHIM_cells"] = set(tuple(c) for c in d["cells"])

    return out


def attribute_directive(cell, directive_cells):
    """Return list of directive names that emit `cell` in probe2 context."""
    return [name for name, cells in directive_cells.items()
            if cell in cells and name != "X33Y4_CROSS_LAB_SHIM_cells"]


CL_VARIANTS = ("cl_and cl_andn cl_buf2 cl_nor cl_or cl_xnor cl_xor "
               "rcl_and rcl_andn rcl_nor rcl_or rcl_xnor rcl_xor").split()


def cross_check_variants(cells: set) -> dict:
    """For each cl_*/rcl_* variant gold available on disk, return the
    subset of `cells` that fire (XOR vs nv_zero_global).  Used to
    identify which shim cells are 1-LE-only (fire in 0 variants) vs
    leaking 2-LE infra (fire in some variants)."""
    zero = ZERO.read_bytes()
    out = {}
    for tag in CL_VARIANTS:
        rbf = REPO / "tmp" / "x33_lut_mining" / tag / f"{tag}.rbf"
        if not rbf.exists():
            continue
        rb = rbf.read_bytes()
        s = set()
        for off, bp in cells:
            if (rb[off] ^ zero[off]) & (1 << bp):
                s.add((off, bp))
        out[tag] = s
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", action="store_true",
                    help="write results/x33y4_probe2_shim_decomposition.json")
    ap.add_argument("--verify", action="store_true",
                    help="assert buckets are disjoint and cover full shim")
    args = ap.parse_args()

    zero = ZERO.read_bytes()
    gold_bytes = GOLD.read_bytes()
    gold = cells_of(gold_bytes, zero)
    shim = set(tuple(c) for c in
               json.loads(SHIM.read_text())["cells"])

    print(f"shim:                     {len(shim)} cells")
    print(f"probe2 gold (vs nv_zero): {len(gold)} cells")

    # Two primary buckets:
    #   additive: shim ∩ gold  → cell is in Quartus probe2; open
    #     toolchain doesn't emit it; shim adds it.  Each maps to a
    #     directive that NEEDS to be extended to cover X33Y4 1-LE class.
    #   over_cancel: shim - gold → cell is NOT in Quartus probe2 but
    #     open toolchain emits it; shim XOR-cancels.  Each maps to a
    #     directive that OVER-emits for the 1-LE class.
    additive    = shim & gold
    over_cancel = shim - gold
    leftover    = shim - additive - over_cancel  # must be empty

    print()
    print(f"ADDITIVE (gold has bit, shim adds):       {len(additive)}")
    print(f"OVER-CANCEL (gold lacks bit, open over-emits): {len(over_cancel)}")
    if leftover:
        print(f"LEFTOVER (bug): {len(leftover)}")

    if args.verify:
        assert additive.isdisjoint(over_cancel)
        assert additive | over_cancel == shim
        assert not leftover
        print("\nverify: OK — buckets are disjoint and cover the full shim")

    # Region histograms
    print("\nADDITIVE by column:")
    for k, v in Counter(col_of(off) for off, _ in additive).most_common():
        print(f"  {k}: {v}")
    print("\nOVER-CANCEL by column:")
    for k, v in Counter(col_of(off) for off, _ in over_cancel).most_common():
        print(f"  {k}: {v}")

    # Per-cell directive attribution
    directive_cells = load_directive_cells()
    print("\nPer-directive overlap with shim (probe2 context):")
    for name, cells in directive_cells.items():
        cap = cells & shim
        cap_add = cap & additive
        cap_over = cap & over_cancel
        if cap:
            print(f"  {name}: {len(cap)} shim-overlap "
                  f"({len(cap_add)} ADD + {len(cap_over)} OVER); "
                  f"directive size = {len(cells)}")

    # Attribute every shim cell to (bucket, list-of-directives)
    attribution = {}
    for cell in sorted(shim):
        bucket = "additive" if cell in additive else "over_cancel"
        dirs = attribute_directive(cell, directive_cells)
        attribution[cell] = (bucket, dirs)

    # Compute "novel" subset (no directive overlap at all)
    novel_add  = {c for c in additive    if not attribution[c][1]}
    novel_over = {c for c in over_cancel if not attribution[c][1]}
    print(f"\nNovel ADDITIVE (no current directive emits these): {len(novel_add)}")
    print(f"Novel OVER-CANCEL (??? not from any tracked directive): "
          f"{len(novel_over)}")

    # Cross-check additive cells against 2-LE variant corpus.  Cells
    # that fire in zero 2-LE variants are pure 1-LE-class infra; cells
    # that fire in some are 2-LE-leakage and could be promoted to a
    # cl_class shared directive.
    print("\n=== 2-LE variant cross-check (13 cl_*/rcl_* mining builds) ===")
    var_add  = cross_check_variants(additive)
    var_over = cross_check_variants(over_cancel)
    if var_add:
        union_add = set.union(*var_add.values())
        inter_add = set.intersection(*var_add.values())
        only_1le_add = additive - union_add
        print(f"  ADDITIVE: union across 13 variants = {len(union_add)} / "
              f"{len(additive)} additive cells fire in some 2-LE variant")
        print(f"  ADDITIVE: intersection across 13 variants = {len(inter_add)} "
              f"(true 1-LE-class invariant)")
        print(f"  ADDITIVE: pure 1-LE-only (fire in 0 variants) = "
              f"{len(only_1le_add)}")
    if var_over:
        union_over = set.union(*var_over.values())
        print(f"  OVER-CANCEL: fires in {len(union_over)} of "
              f"{len(over_cancel)} cells across some 2-LE variant — "
              f"these are codec cells that fire correctly for 2-LE but "
              f"over-emit for 1-LE topology")
        for tag in sorted(var_over):
            n = len(var_over[tag])
            if n: print(f"    {tag}: {n}/{len(over_cancel)}")

    if args.save:
        # Recompute cross-check buckets for the sidecar
        var_add_local  = cross_check_variants(additive)
        var_over_local = cross_check_variants(over_cancel)
        union_add_local = (set.union(*var_add_local.values())
                            if var_add_local else set())
        only_1le_add_local = additive - union_add_local
        union_over_local = (set.union(*var_over_local.values())
                            if var_over_local else set())
        out_path = RESULTS / "x33y4_probe2_shim_decomposition.json"
        payload = {
            "description": (
                "Decomposition of the 37-cell X33Y4_PROBE2_INFRA shim "
                "(results/x33y4_probe2_infra.json) into ADDITIVE + "
                "OVER-CANCEL buckets with per-directive attribution.  "
                "Generated by scripts/cross_lab/probe2_shim_decompose.py."
            ),
            "shim_path": str(SHIM.relative_to(REPO)),
            "shim_count": len(shim),
            "gold_reference": str(GOLD.relative_to(REPO)),
            "gold_md5": "d4073d2e655be480d521bf208d3f9ee1",
            "buckets": {
                "additive": {
                    "description": (
                        "Cells in shim AND in Quartus probe2 — bit is "
                        "needed but no current directive emits it for "
                        "the probe2 1-LE topology.  Each candidate for "
                        "promotion into an existing or new directive."),
                    "count": len(additive),
                    "cells": sorted(additive),
                    "novel_count": len(novel_add),
                    "novel_cells": sorted(novel_add),
                    "fire_in_2le_variants_count": (
                        len(union_add_local)),
                    "pure_1le_only_count": len(only_1le_add_local),
                    "pure_1le_only_cells": sorted(only_1le_add_local),
                    "_note": (
                        "If pure_1le_only_count == count, every "
                        "additive cell is 1-LE-class topology specific "
                        "and must NOT be migrated to a generic shared "
                        "directive (e.g. cl_class shim).  Future per-LE "
                        "mining at X33Y4N4 with 1-LE TT corpus needed."),
                },
                "over_cancel": {
                    "description": (
                        "Cells in shim but NOT in Quartus probe2 — open "
                        "toolchain over-emits them; shim XOR-cancels.  "
                        "Each maps to a directive whose data file is "
                        "wrong for the 1-LE topology."),
                    "count": len(over_cancel),
                    "cells": sorted(over_cancel),
                    "novel_count": len(novel_over),
                    "novel_cells": sorted(novel_over),
                    "fire_in_2le_variants_count": (
                        len(union_over_local)),
                    "_note": (
                        "These 4 cells fire in the 3 cl_*/rcl_* "
                        "variants (cl_andn / cl_or / cl_xor) whose TT "
                        "fires nibble class 1 at (4,4) — confirming the "
                        "cells are real 2-LE codec emission, just over-"
                        "emitted for 1-LE.  Suppression should live in "
                        "the X33Y4_PROBE2_INFRA shim (current behavior) "
                        "OR be moved into a 1-LE-topology guard inside "
                        "x33_lut_codec.py if the shim ever expands to "
                        "many 1-LE TTs."),
                },
            },
            "directive_attribution": {
                f"{off},{bp}": {
                    "bucket": bucket,
                    "directives": dirs,
                    "column": col_of(off),
                }
                for (off, bp), (bucket, dirs) in attribution.items()
            },
            "next_session_targets": [
                ("X33_LUT_CODEC over-emit (4 cells, nibble class 1 at "
                 "(4,4)): confirmed 2-LE-real / 1-LE-spurious via "
                 "13-variant cross-check (fire in cl_andn/cl_or/cl_xor "
                 "= variants where class 1 fires).  Cleanest fix is to "
                 "add a 1-LE topology guard inside `_x33_nibble_cells` "
                 "emission loop in fasm2rbf.py: if exactly one X33Y4 "
                 "LE present, suppress nibble class 1 cells listed in "
                 "x33_lut_codec[(4,4)][1].  Then drop the 4 cells from "
                 "shim.  Tested: must keep cl_andn/cl_or/cl_xor open "
                 "build (when reachable) byte-identical."),
                ("Mine OUTROUTE_G15 X33Y4N4 1-LE-specific cells: "
                 "current sigcache entry (29 cells) was seeded from "
                 "2-LE class.  Needs a 1-LE discriminator corpus to "
                 "split position_specific into 2-LE vs 1-LE bands."),
                ("Mine X33Y4 1-LE LAB_CLK_SEL_LE: clk_lab_sel_per_le "
                 "X33 entries are LOC-rejected garbage; rebuild with "
                 "a probe2-style template (single LE at N=4) to "
                 "capture per-LE clock cells separately from LAB-level."),
                ("Promote header-band shim cell (10487, 4) to "
                 "IOB_RESERVE_PIN_M16 Group E once a second 1-LE-class "
                 "discriminator build (simple_led_1LE_clk{PIN}) "
                 "confirms the cell is M16-reserve-1-LE-generic."),
                ("Build a 1-LE TT corpus for X33Y4N4 (probe2 + AND/XOR/"
                 "OR variants of single-LE-at-N4) — 13-variant "
                 "intersection across that corpus would yield the "
                 "TT-invariant 1-LE-class infra subset analogous to the "
                 "cl_*/rcl_* corpus for 2-LE.  ~7 Quartus builds, ~1hr."),
            ],
        }
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"\nsaved → {out_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
