#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decompose the cross_lab.v X=33Y4 shim into actionable buckets.

The 161-cell `results/x33y4_infra_override.json` shim is currently a single
flat cell list applied as a design-specific XOR delta when cross_lab.v
topology is detected.  Real codec progress requires decomposing it so each
slice can eventually be replaced by a proper per-directive mining entry.

This tool slices the shim against:
  1. Intersection of all 13 Quartus cl_*/rcl_* mined builds (vs
     nv_zero_global) — TT-invariant cross_lab fingerprint.
  2. cl_and gold RBF — concrete reference design.
  3. Per-directive layered emission of the open-toolchain build
     (IOB_BASELINE_NV → +IOB_IN E16 → +IOB_IN M16 → +IOB_OUT G15 →
     +clock → +LAB_CLK_SEL).

Output: 4 disjoint buckets totalling all 161 shim cells, plus an
attribution table that maps each OVER-cancel cell to the directive that
last toggled it ON in the layered emission.  Saved to
`results/x33y4_shim_decomposition.json` for future per-directive mining
to consume.

Usage:
  python3 scripts/cross_lab/x33_shim_decompose.py            # print summary
  python3 scripts/cross_lab/x33_shim_decompose.py --save     # also save sidecar
  python3 scripts/cross_lab/x33_shim_decompose.py --verify   # assert disjoint+full
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))

from config import COLUMN_BASE  # noqa: E402

ZERO = REPO / "results" / "rbf" / "nv_zero_global.rbf"
GOLD = REPO / "tmp" / "x33_lut_mining" / "cl_and" / "cl_and.rbf"
SHIM = REPO / "results" / "x33y4_infra_override.json"
MINING_DIR = REPO / "tmp" / "x33_lut_mining"

# 13 cross_lab variant tags expected on disk under tmp/x33_lut_mining/.
# Each places at SLICE_X33_Y4_N4 + N=6 with E16+M16 inputs and G15 output.
CL_VARIANTS = ("cl_and cl_andn cl_buf2 cl_nor cl_or cl_xnor cl_xor "
               "rcl_and rcl_andn rcl_nor rcl_or rcl_xnor rcl_xor").split()

# Layered FASM directive subsets used to attribute OVER-cancel cells.
DIRECTIVE_LAYERS = [
    ("L0_baseline", ["IOB_BASELINE_NV"]),
    ("L1_iob_e16",  ["IOB_BASELINE_NV", "IOB_IN PIN_E16"]),
    ("L2_iob_m16",  ["IOB_BASELINE_NV", "IOB_IN PIN_E16", "IOB_IN PIN_M16"]),
    ("L3_iob_g15",  ["IOB_BASELINE_NV", "IOB_IN PIN_E16", "IOB_IN PIN_M16",
                     "IOB_OUT PIN_G15"]),
    ("L4_clk",      ["IOB_BASELINE_NV", "IOB_IN PIN_E16", "IOB_IN PIN_M16",
                     "IOB_OUT PIN_G15", "GCLK_PIN PIN_E1",
                     "IOB_CLK_INPUT PIN_E1"]),
    ("L5_lab_clk",  ["IOB_BASELINE_NV", "IOB_IN PIN_E16", "IOB_IN PIN_M16",
                     "IOB_OUT PIN_G15", "GCLK_PIN PIN_E1",
                     "IOB_CLK_INPUT PIN_E1", "LAB_CLK_SEL X33Y4",
                     "LAB_CLK_SEL_LE X33Y4N6", "LAB_CLK_SEL_LE X33Y4N4"]),
]


def cells_of(rbf_bytes: bytes, zero_bytes: bytes) -> set:
    s = set()
    for off, (a, b) in enumerate(zip(rbf_bytes, zero_bytes)):
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


def compute_intersection(zero_bytes: bytes) -> set:
    """Cells common to all 13 cl_*/rcl_* variants (TT-invariant infra)."""
    deltas = []
    missing = []
    for tag in CL_VARIANTS:
        rbf = MINING_DIR / tag / f"{tag}.rbf"
        if not rbf.exists():
            missing.append(tag)
            continue
        deltas.append(cells_of(rbf.read_bytes(), zero_bytes))
    if missing:
        print(f"WARN: missing variants: {missing}", file=sys.stderr)
    if len(deltas) < 6:
        raise SystemExit(f"need >=6 variants on disk, have {len(deltas)}; "
                         f"run scripts/cross_lab/x33_lut_mining/build_variant.sh")
    return set.intersection(*deltas)


def emit_layer(layer_dirs: list, work: Path) -> set:
    """Run fasm2rbf with the given directive subset, return diff cells vs zero."""
    fasm = work / "decomp.fasm"
    rbf = work / "decomp.rbf"
    fasm.write_text("\n".join(layer_dirs) + "\n")
    cmd = ["python3", str(REPO / "fuzz" / "fasm2rbf.py"),
           str(fasm), str(ZERO), str(rbf)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if r.returncode != 0:
        raise SystemExit(f"fasm2rbf failed for layer:\n{r.stderr[-500:]}")
    return cells_of(rbf.read_bytes(), ZERO.read_bytes())


def attribute_over(over: set, layer_cells: dict) -> dict:
    """For each cell in OVER set, return the layer that last toggled it ON
    (i.e. flipped 0→1, persisted to L5)."""
    layer_order = [tag for tag, _ in DIRECTIVE_LAYERS]
    out = {}
    for cell in over:
        if cell not in layer_cells["L5_lab_clk"]:
            out[cell] = "NOT_IN_L5"
            continue
        state = 0
        last_on = None
        for tag in layer_order:
            new = 1 if cell in layer_cells[tag] else 0
            if new == 1 and state == 0:
                last_on = tag
            state = new
        out[cell] = last_on or "never"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", action="store_true",
                    help="write results/x33y4_shim_decomposition.json")
    ap.add_argument("--verify", action="store_true",
                    help="assert buckets are disjoint + cover full shim")
    ap.add_argument("--no-layered", action="store_true",
                    help="skip directive-layered attribution (faster)")
    args = ap.parse_args()

    zero = ZERO.read_bytes()
    gold = cells_of(GOLD.read_bytes(), zero)
    shim = set(tuple(c) for c in
               json.loads(SHIM.read_text())["cells"])
    print(f"shim:           {len(shim)} cells")
    print(f"cl_and gold:    {len(gold)} cells")

    inter = compute_intersection(zero)
    print(f"intersection:   {len(inter)} cells (TT-invariant across "
          f"{len(CL_VARIANTS)} cl_*/rcl_* variants)")

    # Buckets
    tt_invariant = shim & inter & gold      # mineable LE infra
    cl_specific  = (shim & gold) - inter    # cl_and-specific (TT-dependent)
    over_cancel  = shim - gold              # open over-emits
    leftover     = shim - tt_invariant - cl_specific - over_cancel  # should be 0
    print()
    print(f"TT-invariant LE infra (mineable):     {len(tt_invariant)}")
    print(f"cl_and-specific TT-dependent:         {len(cl_specific)}")
    print(f"OVER-cancel (open over-emits):        {len(over_cancel)}")
    if leftover:
        print(f"LEFTOVER (bug): {len(leftover)}")

    if args.verify:
        assert tt_invariant.isdisjoint(cl_specific)
        assert tt_invariant.isdisjoint(over_cancel)
        assert cl_specific.isdisjoint(over_cancel)
        assert tt_invariant | cl_specific | over_cancel == shim
        print("\nverify: OK — buckets are disjoint and cover the full shim")

    # Per-column histograms
    from collections import Counter
    print("\nTT-invariant LE infra by column:")
    for k, v in Counter(col_of(off) for off, _ in tt_invariant).most_common():
        print(f"  {k}: {v}")

    print("\nOVER-cancel by column:")
    for k, v in Counter(col_of(off) for off, _ in over_cancel).most_common():
        print(f"  {k}: {v}")

    # Layered attribution for OVER cells
    attribution = {}
    if not args.no_layered:
        print("\nLayered directive emission (running fasm2rbf 6 times)...")
        work = REPO / "tmp" / "x33_decomp"
        work.mkdir(parents=True, exist_ok=True)
        layer_cells = {tag: emit_layer(dirs, work)
                       for tag, dirs in DIRECTIVE_LAYERS}
        attribution = attribute_over(over_cancel, layer_cells)
        print("\nOVER-cancel attribution (last-toggle-on layer):")
        for tag, n in Counter(attribution.values()).most_common():
            print(f"  {tag}: {n}")

    if args.save:
        out_path = REPO / "results" / "x33y4_shim_decomposition.json"
        payload = {
            "description": (
                "Decomposition of the 161-cell X33Y4_CROSS_LAB_SHIM "
                "(results/x33y4_infra_override.json) into actionable "
                "buckets.  Generated by scripts/cross_lab/x33_shim_decompose.py."
            ),
            "shim_path": str(SHIM.relative_to(REPO)),
            "shim_count": len(shim),
            "intersection_variants": CL_VARIANTS,
            "intersection_count": len(inter),
            "buckets": {
                "tt_invariant_infra": {
                    "description": ("Cells in shim AND gold AND in the "
                                    "intersection of all cl_*/rcl_* "
                                    "variants — real X=33Y4 LE infra "
                                    "(LAB_CLK_SEL_LE, same-LAB ROUTE, "
                                    "IOB pad routing).  Promotion target."),
                    "count": len(tt_invariant),
                    "cells": sorted(tt_invariant),
                },
                "cl_specific": {
                    "description": ("Cells in shim AND gold but NOT in "
                                    "the intersection — TT-dependent or "
                                    "cl_and-specific.  NOT a generic "
                                    "directive target."),
                    "count": len(cl_specific),
                    "cells": sorted(cl_specific),
                },
                "over_cancel": {
                    "description": ("Cells in shim but NOT in gold — "
                                    "current open-toolchain directives "
                                    "over-emit them, shim XOR-cancels.  "
                                    "Each maps to a directive whose "
                                    "input_delta is wrong for X=33Y4 "
                                    "placement context."),
                    "count": len(over_cancel),
                    "cells": sorted(over_cancel),
                    "directive_attribution": (
                        {f"({off},{bp})": layer
                         for (off, bp), layer in
                         sorted(attribution.items())}
                        if attribution else None),
                },
            },
            "next_session_targets": [
                ("Mine OUTROUTE_G15 X33Y4N6 → enable IOB_PAD_NV path → "
                 "may eliminate L0/L1/L2/L4 OVER cells (~37 of 41)"),
                ("Re-mine LAB_CLK_SEL_LE X33Y4 N=4/N=6 with cross_lab "
                 "template → reduces tt_invariant cells in fabric column"),
                ("Mine same-LAB X=33 ROUTE sigcache for "
                 "X33Y4N4 → X33Y4N6.dataa → reduces tt_invariant cells "
                 "in X=33 column"),
            ],
        }
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"\nsaved → {out_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
