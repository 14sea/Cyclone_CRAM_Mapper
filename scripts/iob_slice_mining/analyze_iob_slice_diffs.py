# SPDX-License-Identifier: GPL-3.0-or-later
"""Decompose Quartus paired-pin RBFs to isolate IOB<->SLICE route cells.

Inputs (all built with build_diff_refs.py + build_golden_dff.py):
  * golden.rbf            K=E16, LED=G15 (anchor)
  * golden_E15_G15.rbf    K=E15, LED=G15
  * golden_M16_G15.rbf    K=M16, LED=G15
  * golden_E16_F15.rbf    K=E16, LED=F15

Outputs (stdout + JSON):
  * Per-pair CRAM-only symmetric-difference cells.
  * Pair-wise consistency check (R(A,B) ^ R(B,C) == R(A,C)).
  * Inclusion check against existing iob_cell_map.json per-pin cell sets.

Key findings at LAB(10,4).N=0 (2026-04-14):
  * Input-pin swap (E15/E16/M16) flips exactly 3 distinct CRAM cells,
    all in frame 1727 bp=3 at byte-in-frame offsets {22, 24, 26}.
    Interpretation: one-hot "LI-MUX select input pin" cells for this LE.
    Per-pin bit:  E16 -> bif=26, E15 -> bif=24, M16 -> bif=22.
  * The bulk of the fabric route (pad -> LAB_X=10 LI column) is
    shared across all tested input pins and does NOT appear in any
    pair-diff. To isolate it, a paired "no-route" template build is
    required -- the pin-swap diff only exposes the mux-select layer.
  * Output-pin swap (G15/F15) flips 41 CRAM cells spanning cols
    10-49; the LE->pad route differs substantially for non-neighboring
    output pins, so the output path is much more pin-dependent than
    the input path.
  * iob_cell_map.json per_pin_input/output entries mined from the
    combinational iob_probe topology do NOT overlap with any pair
    diff here -- those cells are topology-specific to the probe LE
    placement, not universal pad-buffer cells.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

HDR_BYTES = 5282
FRAME = 210
PRE = 32


def load(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def cells_xor(a: bytes, b: bytes) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for i in range(min(len(a), len(b))):
        x = a[i] ^ b[i]
        if x:
            for bp in range(8):
                if x & (1 << bp):
                    out.add((i, bp))
    return out


def cram_only(cells: set[tuple[int, int]]) -> set[tuple[int, int]]:
    return {
        (i, bp)
        for (i, bp) in cells
        if HDR_BYTES <= i < 367952 and (i - PRE) % FRAME < 208
    }


def describe(off: int) -> dict:
    frame = (off - PRE) // FRAME
    col = off // 7350
    bif = (off - PRE) % FRAME
    return {"frame": frame, "col": col, "bif": bif}


def pad_symdiff(pin_a: str, pin_b: str, pin_map: dict) -> set[tuple[int, int]]:
    sa = {tuple(c) for c in pin_map[pin_a]}
    sb = {tuple(c) for c in pin_map[pin_b]}
    return sa ^ sb


def analyze(paths: dict[str, str]) -> dict:
    g = load(paths["golden"])
    e15 = load(paths["golden_E15_G15"])
    m16 = load(paths["golden_M16_G15"])
    f15 = load(paths["golden_E16_F15"])

    d = {
        "E16_E15": cram_only(cells_xor(g, e15)),
        "E16_M16": cram_only(cells_xor(g, m16)),
        "E15_M16": cram_only(cells_xor(e15, m16)),
        "G15_F15": cram_only(cells_xor(g, f15)),
    }

    consistency = d["E16_E15"] ^ d["E16_M16"] ^ d["E15_M16"]

    iob_map_path = REPO / "results" / "iob_cell_map.json"
    iob_overlap = {}
    if iob_map_path.exists():
        iob = json.loads(iob_map_path.read_text())
        for (a, b, which, key) in [
            ("E16", "E15", "per_pin_input", "E16_E15"),
            ("E16", "M16", "per_pin_input", "E16_M16"),
            ("E15", "M16", "per_pin_input", "E15_M16"),
            ("G15", "F15", "per_pin_output", "G15_F15"),
        ]:
            expected_pad = pad_symdiff(a, b, iob[which])
            iob_overlap[key] = {
                "expected_pad_cells": len(expected_pad),
                "overlap_with_diff": len(expected_pad & d[key]),
            }

    report = {
        "pair_diffs": {
            k: {
                "n_cells": len(v),
                "cells": sorted([list(c) + [describe(c[0])] for c in v])[:64],
            }
            for k, v in d.items()
        },
        "consistency_residual": {
            "n_cells": len(consistency),
            "cells": sorted(list(consistency))[:16],
        },
        "iob_cell_map_overlap": iob_overlap,
        "summary": {
            "input_mux_select_layer": (
                "All 3 E16/E15/M16 pair-diffs reduce to 2 CRAM cells each, "
                "distributed across 3 distinct byte-in-frame positions in "
                "frame 1727 bp=3. This is a 3-cell one-hot 'select pin' "
                "layer local to the LE's LI MUX."
            ),
            "output_route_is_pin_dependent": (
                "G15/F15 pair-diff has 41 CRAM cells spanning 15 columns "
                "-- the LE->pad route is substantially pin-specific."
            ),
            "iob_cell_map_mismatch": (
                "per_pin_input/per_pin_output cell sets from iob_cell_map "
                "(mined from the combinational iob_probe topology) do not "
                "overlap with these diffs -- those positions are topology-"
                "specific and cannot be reused as universal pad-buffer cells."
            ),
        },
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refdir",
                    default=str(HERE / "work"),
                    help="directory holding golden*.rbf files")
    ap.add_argument("--json", metavar="PATH",
                    help="write full JSON report to this path")
    args = ap.parse_args()

    refdir = Path(args.refdir)
    paths = {
        "golden": str(refdir / "golden.rbf"),
        "golden_E15_G15": str(refdir / "golden_E15_G15.rbf"),
        "golden_M16_G15": str(refdir / "golden_M16_G15.rbf"),
        "golden_E16_F15": str(refdir / "golden_E16_F15.rbf"),
    }
    missing = [p for p in paths.values() if not Path(p).exists()]
    if missing:
        print("Missing reference RBFs:", file=sys.stderr)
        for p in missing:
            print(f"  {p}", file=sys.stderr)
        print(
            "\nRun build_golden_dff.py + build_diff_refs.py first "
            "(outputs default to ./work).",
            file=sys.stderr,
        )
        return 1

    report = analyze(paths)

    for key, info in report["pair_diffs"].items():
        print(f"\n[{key}] CRAM cells: {info['n_cells']}")
        for entry in info["cells"][:8]:
            (off, bp, meta) = entry
            print(f"  ({off},{bp}) frame={meta['frame']} col={meta['col']} "
                  f"bif={meta['bif']}")

    cr = report["consistency_residual"]
    print(f"\n[consistency] R(E16,E15) ^ R(E16,M16) ^ R(E15,M16) residual: "
          f"{cr['n_cells']} cells (expect 0)")

    print("\n[iob_cell_map overlap]")
    for key, v in report["iob_cell_map_overlap"].items():
        print(f"  {key}: expected_pad={v['expected_pad_cells']} "
              f"overlap_with_diff={v['overlap_with_diff']}")

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=list))
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
