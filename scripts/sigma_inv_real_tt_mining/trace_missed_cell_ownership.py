#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""α'' analysis: identify which fasm2rbf directive owns each "σ⁻¹-missed"
header-band cell from results/real_tt_classification.json.

Method: enumerate the cell footprint of every directive loader for the
arguments used by build_open23 (W=23 silicon-validated, byte-identical
to md5 905dfc85), then for each missed (off, bp) cell, report which
directive's cell set contains it.

Output: stdout report, no files written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f2

CLASSIFICATION = REPO / "results" / "real_tt_classification.json"


def collect_directive_footprints():
    """Return {directive_name: set((off,bp))} for every directive that
    might touch the header band, called with build_open23-style args."""
    fp = {}

    # NV_BASELINE_PACK: full nv_zero reproduction on top of pure_zero
    nv = f2._load_nv_baseline_pack()
    cells = set()
    for bucket_name, bucket_cells in nv.items():
        if isinstance(bucket_cells, list):
            for c in bucket_cells:
                cells.add(tuple(c))
    fp["NV_BASELINE_PACK"] = cells

    # IOB_BASELINE_NV
    fp["IOB_BASELINE_NV"] = set(tuple(c) for c in f2._load_iob_baseline_hdr_cells())

    # IOB_PAD_NV (139 cells) + carry-chain ext (74 cells)
    fp["IOB_PAD_NV"] = set(tuple(c) for c in f2._load_iob_pad_nv_cells())
    fp["IOB_PAD_ARITH_EXT"] = set(tuple(c) for c in f2._load_iob_pad_arith_ext_cells())

    # IOB_ROUTE for E16->dataa, M16->datab at the LE's position
    # (we'll iterate per-LE — collect generic footprints later)

    # GCLK_PIN E1
    fp["GCLK_PIN_E1"] = set(tuple(c) for c in f2._load_gclk_pin_cells("E1"))

    # IOB_CLK_INPUT E1
    try:
        fp["IOB_CLK_INPUT_E1"] = set(tuple(c) for c in f2._load_iob_clk_input_cells("E1"))
    except Exception as e:
        fp["IOB_CLK_INPUT_E1"] = set()
        print(f"  (IOB_CLK_INPUT_E1 loader failed: {e})", file=sys.stderr)

    # IOB_RESERVE_PIN_M16
    try:
        fp["IOB_RESERVE_PIN_M16"] = set(tuple(c) for c in f2._load_iob_reserve_pin_m16_cells())
    except Exception as e:
        fp["IOB_RESERVE_PIN_M16"] = set()
        print(f"  (IOB_RESERVE_PIN_M16 loader failed: {e})", file=sys.stderr)

    # ARITH blob (per-LAB at any LAB) + ARITH_MULTI_LAB widths 17..32
    try:
        arith = f2._load_arith_blob()
        cells = set()
        for k, v in arith.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    if isinstance(sv, list):
                        for c in sv:
                            cells.add(tuple(c))
        fp["LUT_ARITH_blob"] = cells
    except Exception as e:
        fp["LUT_ARITH_blob"] = set()
        print(f"  (LUT_ARITH blob load failed: {e})", file=sys.stderr)

    return fp


def per_le_dynamic_directives(x, y, n):
    """Directives whose footprint is keyed on (x,y,n)."""
    fp = {}
    # OUTROUTE_G15 for this LE
    try:
        fp[f"OUTROUTE_G15({x},{y},{n})"] = set(
            tuple(c) for c in f2._load_outroute_g15_cells(x, y, n)
        )
    except Exception:
        fp[f"OUTROUTE_G15({x},{y},{n})"] = set()

    # LAB_CLK_SEL + LAB_CLK_SEL_LE
    try:
        fp[f"LAB_CLK_SEL({x},{y})"] = set(
            tuple(c) for c in f2._load_lab_clk_sel_cells(x, y, lenient=True)
        )
    except Exception:
        fp[f"LAB_CLK_SEL({x},{y})"] = set()
    try:
        fp[f"LAB_CLK_SEL_LE({x},{y},{n})"] = set(
            tuple(c) for c in f2._load_lab_clk_sel_le_cells(x, y, n, lenient=True)
        )
    except Exception:
        fp[f"LAB_CLK_SEL_LE({x},{y},{n})"] = set()

    # IOB_ROUTE E16->LE.dataa, M16->LE.datab (mining design's iob_pad_nv layout)
    for pin, port in [("PIN_E16", "dataa"), ("PIN_M16", "datab")]:
        try:
            fp[f"IOB_ROUTE({pin}->X{x}Y{y}N{n}.{port})"] = set(
                tuple(c) for c in f2._load_iob_route_cells(pin, x, y, n, port)
            )
        except Exception:
            fp[f"IOB_ROUTE({pin}->X{x}Y{y}N{n}.{port})"] = set()

    return fp


def main():
    classification = json.loads(CLASSIFICATION.read_text())
    entries = classification["entries"]

    print("=== Static directive footprints ===")
    static_fp = collect_directive_footprints()
    for name, cells in static_fp.items():
        hdr_cells = [(o, b) for (o, b) in cells if o < 5282]
        print(f"  {name}: {len(cells)} total ({len(hdr_cells)} in hdr band)")

    print()
    # Union of all missed cells across the 8 LEs
    all_missed = set()
    per_le_missed = {}
    for le, e in entries.items():
        m = set(tuple(c) for c in e.get("sigma_inv_missed", []))
        per_le_missed[le] = m
        all_missed |= m

    print(f"=== Cross-reference {len(all_missed)} unique missed cells against directives ===")

    # Per-cell ownership lookup
    rows = []
    for off, bp in sorted(all_missed):
        owners = []
        for name, cells in static_fp.items():
            if (off, bp) in cells:
                owners.append(name)
        rows.append((off, bp, owners))

    # Now check per-LE dynamic directives — does any LE-specific loader
    # claim a cell that no static directive claims?
    print()
    print("Per-cell static-directive ownership:")
    print(f"  {'(off,bp)':<14} {'owner(s)':<60}")
    unowned = []
    for off, bp, owners in rows:
        own_str = ",".join(owners) if owners else "(NONE)"
        print(f"  {str((off, bp)):<14} {own_str:<60}")
        if not owners:
            unowned.append((off, bp))

    if unowned:
        print()
        print(f"=== {len(unowned)} cells unowned by static directives — checking per-LE dynamic ===")
        for off, bp in unowned:
            owners = []
            for le in entries:
                # parse "X16Y4N0" → (16, 4, 0)
                key = le[1:]  # strip 'X'
                xs, rest = key.split("Y", 1)
                ys, ns = rest.split("N", 1)
                x, y, n = int(xs), int(ys), int(ns)
                # Only check this LE if (off,bp) is in its missed set
                if (off, bp) not in per_le_missed[le]:
                    continue
                dyn_fp = per_le_dynamic_directives(x, y, n)
                for name, cells in dyn_fp.items():
                    if (off, bp) in cells:
                        owners.append(f"{le}:{name}")
            if owners:
                print(f"  {str((off, bp)):<14} {','.join(owners[:3])}")
            else:
                print(f"  {str((off, bp)):<14} (still unowned across all LE dynamics)")

    # Summary by region
    print()
    print("=== Summary ===")
    print(f"  Total unique missed cells (8 LEs union) : {len(all_missed)}")
    print(f"  All in header band (frame 0, off<5282)  : {all(o<5282 for o,_ in all_missed)}")
    static_owned = set()
    for off, bp in all_missed:
        for name, cells in static_fp.items():
            if (off, bp) in cells:
                static_owned.add((off, bp))
                break
    print(f"  Owned by some static directive          : {len(static_owned)}/{len(all_missed)}")
    print(f"  Unowned                                 : {len(all_missed) - len(static_owned)}")


if __name__ == "__main__":
    main()
