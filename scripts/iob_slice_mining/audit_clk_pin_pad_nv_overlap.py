#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit IOB_CLK_INPUT_PIN_X ∩ IOB_PAD_NV overlap and miscalibration risk.

Reports per-pin:
  * overlap count   = cells in both IOB_CLK_INPUT_PIN_X data and IOB_PAD_NV
  * already-correct = overlap cells where the simple_led_clk{PIN} gold
                      reference matches nv baseline (double-flip-to-nv is
                      the correct semantic)
  * needs-correction = overlap cells where gold differs from nv (a
                      Group-B-style XOR correction is needed; without it
                      these cells silently miscalibrate)

Currently only PIN_E1 has a landed correction (`IOB_RESERVE_PIN_M16`
Group B, gated on M16-not-IOB).  Other pins are unmined for the
IOB_PAD_NV combination and would silently miscalibrate if used in an
open-toolchain build that combines them.

Run with --save to write `results/iob_clk_input_pad_nv_audit.json` —
that sidecar is consumed by fasm2rbf to emit a warning whenever a
non-E1 IOB_CLK_INPUT pin gets emitted alongside IOB_PAD_NV.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RES = REPO / "results"
WORK = REPO / "scripts" / "iob_slice_mining" / "work"


def load_clk_pin_cells():
    return json.loads((RES / "iob_clk_pin_hdr_cells.json").read_text())["cells"]


def load_iob_pad_nv():
    nvm = json.loads((RES / "output_route_nv_mining.json").read_text())
    return set(tuple(c) for c in nvm["iob_pad_cells"])


def per_pin_audit():
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    clk = load_clk_pin_cells()
    pad_nv = load_iob_pad_nv()

    out = {}
    for pin in sorted(clk.keys()):
        overlap = set(tuple(c) for c in clk[pin]) & pad_nv
        rbf_path = (WORK / f"simple_led_E16_to_G15_clk{pin}"
                    / "output_files" / f"simple_led_E16_to_G15_clk{pin}.rbf")
        if not rbf_path.exists():
            out[pin] = {
                "overlap_count": len(overlap),
                "discriminator_present": False,
                "needs_correction_count": None,
                "needs_correction_cells": None,
            }
            continue
        rb = rbf_path.read_bytes()
        already_ok = []
        needs_corr = []
        for off, bp in overlap:
            nv_b = (nv[off] >> bp) & 1
            rb_b = (rb[off] >> bp) & 1
            (already_ok if nv_b == rb_b else needs_corr).append((off, bp))
        out[pin] = {
            "overlap_count": len(overlap),
            "discriminator_present": True,
            "discriminator_path": str(rbf_path.relative_to(REPO)),
            "already_correct_count": len(already_ok),
            "needs_correction_count": len(needs_corr),
            "needs_correction_cells": sorted(needs_corr),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", action="store_true",
                    help="write results/iob_clk_input_pad_nv_audit.json")
    args = ap.parse_args()

    audit = per_pin_audit()

    print(f"{'pin':<6s} {'overlap':>8s} {'discr_diff':>11s} "
          f"{'needs_correction':>17s}  status")
    print("-" * 70)
    for pin, r in audit.items():
        if not r["discriminator_present"]:
            print(f"{pin:<6s} {r['overlap_count']:>8d}        N/A "
                  f"            N/A   no discriminator")
            continue
        nc = r["needs_correction_count"]
        ok = r["already_correct_count"]
        status = "OK" if nc == 0 else (
            "LANDED" if pin == "E1"
            else ("LATENT BUG" if nc > 0 else "")
        )
        print(f"{pin:<6s} {r['overlap_count']:>8d} {ok:>11d} "
              f"{nc:>17d}  {status}")

    if args.save:
        landed_pins = {"E1": (
            "IOB_RESERVE_PIN_M16 Group B (9 cells; gated on "
            "M16 not in IOBs).  See iob_reserve_pin_m16_cells.json "
            "→ xor_cells_unified_with_iob_pad_nv_recalibration → "
            "Group B."
        )}
        payload = {
            "description": (
                "Per-pin IOB_CLK_INPUT × IOB_PAD_NV overlap audit.  "
                "Identifies which IOB_CLK_INPUT pin data files have "
                "calibration mismatch with IOB_PAD_NV (data was mined "
                "against IOB_BASELINE_NV).  Cells in `needs_correction_cells` "
                "would silently miscalibrate (XOR double-flip-to-nv "
                "instead of the gold state) if both directives were "
                "emitted without an explicit correction.  PIN_E1 has a "
                "landed correction; other pins are LATENT — fasm2rbf "
                "warns when at-risk combinations detected."),
            "data_baseline_for_iob_clk_input": (
                "IOB_BASELINE_NV (129 cells) — see "
                "results/iob_baseline_hdr_cells.json"),
            "audited_against": (
                "results/output_route_nv_mining.json → iob_pad_cells "
                "(139 cells).  Discriminator: "
                "scripts/iob_slice_mining/work/simple_led_E16_to_G15_"
                "clk{PIN}/output_files/*.rbf — 1-LE@X10Y10N0 with E16+"
                "G15+clk{PIN}, M16 reserved, IOB_BASELINE_NV-class infra."),
            "per_pin": audit,
            "landed_corrections": landed_pins,
            "next_session_targets": [
                ("Mine IOB_PAD_NV + IOB_CLK_INPUT_pin combination for "
                 "the 5 highest-risk pins (M16=8, R8=5, M15=2, plus "
                 "others with >=1 needed corrections).  ~30min Quartus "
                 "per pin, generates Group-B-style override list."),
                ("Refactor: split IOB_RESERVE_PIN_M16 Group B out into "
                 "a dedicated `IOB_CLK_INPUT_PAD_NV_RECALIB` directive "
                 "table keyed by pin.  Currently Group B fires gated "
                 "on M16-reserve (correlates with E1-clock 1-LE class "
                 "in our test set).  Decoupling would let other pins "
                 "land their corrections without artificial M16 gating."),
            ],
        }
        out_path = RES / "iob_clk_input_pad_nv_audit.json"
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"\nsaved → {out_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
