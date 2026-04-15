# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract clock-input-pin hdr cells.

Dedicated clock bank pins (E1 etc.) were not covered by fuzz/iob_sweep.py
(only 44 regular IO pins).  When a design uses E1 as CLK (driving the
GCLK network), Quartus emits ~26 header-band bytes configuring E1's
IOB + the E1→GCLK path.

Algebra:
  cells_E1_clk = simple_led_E16_to_G15.rbf ^ iob_in_E16.rbf  [hdr band]
  (gold design has E1 CLK + E16 IN + G15 OUT; iob_in_E16 has only E16 IN
  + G15 OUT)

Applying `cells_E1_clk` on top of `nv + IOB_BASELINE_NV + IOB_IN E16 +
IOB_OUT G15` reproduces the simple_led hdr band byte-for-byte.

Writes `results/iob_clk_pin_hdr_cells.json` keyed by pin (just "E1" for
now).  Extensible: when more clock-bank pins are needed, re-run with
the matching gold/anchor pair.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

PRE = 32
FRAME = 210
FIRST = 25
CRAM_START = PRE + FIRST * FRAME  # 5282


def extract_pin_delta(gold_path: Path, anchor_path: Path) -> list[tuple[int, int]]:
    gold = gold_path.read_bytes()
    anchor = anchor_path.read_bytes()
    assert len(gold) == len(anchor)
    cells: list[tuple[int, int]] = []
    for off in range(CRAM_START):
        x = gold[off] ^ anchor[off]
        if x == 0:
            continue
        for bp in range(8):
            if x & (1 << bp):
                cells.append((off, bp))
    return sorted(cells)


def main() -> int:
    gold_simple = (HERE / "work" / "simple_led_E16_to_G15"
                   / "output_files" / "simple_led_E16_to_G15.rbf")
    anchor_E16 = REPO / "results" / "rbf" / "iob_in_E16.rbf"

    e1_cells = extract_pin_delta(gold_simple, anchor_E16)
    print(f"[E1] {len(e1_cells)} bit cells "
          f"({len({o for o, _ in e1_cells})} distinct bytes)")

    data = {
        "meta": {
            "source": "simple_led_{IN_PIN}_to_{OUT_PIN}.rbf ^ "
                      "iob_in_{IN_PIN}.rbf, hdr band only "
                      "(off < 5282).  Extracts the clock-input pin "
                      "activation delta (IOB bank config + GCLK mux).",
            "frame": "nv_zero_global",
            "scope": "header_band",
            "note": "Apply on top of nv + IOB_BASELINE_NV + "
                    "IOB_IN PIN_{IN_PIN} + IOB_OUT PIN_{OUT_PIN} to "
                    "activate the clock-bank pin as a GCLK driver.",
        },
        "cells": {
            "E1": e1_cells,
        },
    }
    out_path = REPO / "results" / "iob_clk_pin_hdr_cells.json"
    out_path.write_text(json.dumps(data, indent=2))
    print(f"[ok] wrote {out_path}")

    # Self-check: iob_in_E16.hdr ^ cells_E1 == gold.hdr
    anchor = anchor_E16.read_bytes()
    gold = gold_simple.read_bytes()
    buf = bytearray(anchor[:CRAM_START])
    for off, bp in e1_cells:
        buf[off] ^= (1 << bp)
    if bytes(buf) == gold[:CRAM_START]:
        print("[verified] anchor_E16 + E1 cells == gold hdr band")
        return 0
    print("[FAIL] self-check mismatch")
    return 1


if __name__ == "__main__":
    sys.exit(main())
