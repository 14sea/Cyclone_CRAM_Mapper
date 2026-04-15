# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive the ideal IOB_ROUTE cells for (E16 -> 10,4,0, dataa) from
Quartus gold, by subtracting (XOR) the cells contributed by all other
directives in the simple_led FASM stack.

Algebra:
  gold_delta = gold ^ nv_zero
             = IOB_BASELINE_NV ⊕ IOB_IN(E16) ⊕ IOB_OUT(G15)
               ⊕ IOB_CLK_INPUT(E1) ⊕ IOB_ROUTE_primary(E16,10_4_0,dataa)
               ⊕ GCLK_PIN(E1) ⊕ LAB_CLK_SEL(10,4) ⊕ LAB_CLK_SEL_LE(10,4,0)
  =>
  IOB_ROUTE_primary = gold_delta ⊕ (all other directives)

This gives a target-LAB-only cell set for IOB_ROUTE that, combined with
the other directives on nv_zero_global, reproduces simple_led gold
bit-perfect in CRAM data.

Verifies by rebuilding simple_led FASM with the primary-only cells
injected into fasm2rbf's _IOB_ROUTE_CACHE and diffing against gold.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f  # noqa: E402


PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_START = PRE + FIRST * FRAME
CRAM_END = PRE + (LAST + 1) * FRAME


def bit_cells(rbf_xor: bytes) -> set[tuple[int, int]]:
    out = set()
    for i, b in enumerate(rbf_xor):
        if not b:
            continue
        for bp in range(8):
            if b & (1 << bp):
                out.add((i, bp))
    return out


def is_crc(off: int) -> bool:
    if off < PRE or off >= CRAM_END:
        return False
    return (off - PRE) % FRAME >= 208


def main() -> int:
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_CLK_INPUT_CACHE = None

    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    gold = ((HERE / "work" / "simple_led_E16_to_G15"
             / "output_files" / "simple_led_E16_to_G15.rbf")
            .read_bytes())
    gold_xor = bytes(a ^ b for a, b in zip(gold, nv))
    gold_cells = {c for c in bit_cells(gold_xor)
                  if not is_crc(c[0]) and c[0] < CRAM_END}

    iob_map = f._load_iob_map()
    other_parity = Counter()
    directive_sets = {
        "IOB_BASELINE_NV":
            {tuple(c) for c in f._load_iob_baseline_hdr_cells()},
        "IOB_IN E16":
            {tuple(c) for c in f._iob_delta_cells("IN", "E16", iob_map)},
        "IOB_OUT G15":
            {tuple(c) for c in f._iob_delta_cells("OUT", "G15", iob_map)},
        "IOB_CLK_INPUT E1":
            {tuple(c) for c in f._load_iob_clk_input_cells("E1")},
        "GCLK_PIN E1":
            set(f._load_gclk_pin_cells("E1")),
        "LAB_CLK_SEL 10,4":
            set(f._load_lab_clk_sel_cells(10, 4)),
        "LAB_CLK_SEL_LE 10,4,0":
            set(f._load_lab_clk_sel_le_cells(10, 4, 0)),
    }
    for name, cs in directive_sets.items():
        for c in cs:
            other_parity[c] ^= 1
    other_cells = {c for c, v in other_parity.items() if v}
    other_cells = {c for c in other_cells
                   if not is_crc(c[0]) and c[0] < CRAM_END}

    # Ideal primary-only IOB_ROUTE cells
    primary = (gold_cells ^ other_cells)

    # Current IOB_ROUTE cells
    current = set(f._load_iob_route_cells("E16", 10, 4, 0, "dataa"))
    current_in_band = {c for c in current
                       if not is_crc(c[0]) and c[0] < CRAM_END}

    print(f"gold_delta (in-band, non-CRC): {len(gold_cells)}")
    print(f"other directives XOR parity  : {len(other_cells)}")
    print(f"=> IOB_ROUTE primary-only    : {len(primary)}")
    print(f"current IOB_ROUTE in-band    : {len(current_in_band)}")
    print(f"current  / primary intersect : {len(primary & current_in_band)}")
    print(f"in current only (strip)      : "
          f"{len(current_in_band - primary)}")
    print(f"in primary only (add)        : "
          f"{len(primary - current_in_band)}")

    # The difference shows which cells move between the two definitions.
    diff = current_in_band ^ primary
    print(f"\nSymmetric difference (current XOR primary): {len(diff)}")

    # Verify: patch fasm2rbf's cache and rebuild
    f._IOB_ROUTE_CACHE = {
        "IOB_E16->10,4,0,dataa": sorted(list(c) for c in primary),
    }

    fasm_text = ("IOB_BASELINE_NV\n"
                 "IOB_IN  PIN_E16\n"
                 "IOB_OUT PIN_G15\n"
                 "IOB_CLK_INPUT PIN_E1\n"
                 "IOB_ROUTE PIN_E16 -> X10Y4N0.dataa\n"
                 "GCLK_PIN PIN_E1\n"
                 "LAB_CLK_SEL X10Y4\n"
                 "LAB_CLK_SEL_LE X10Y4N0\n")
    out = f.bitgen(fasm_text, nv, patch_crc=True)

    data_diffs = 0
    crc_diffs = 0
    for i in range(len(out)):
        if out[i] != gold[i]:
            if is_crc(i):
                crc_diffs += 1
            else:
                data_diffs += 1
    print(f"\nRebuild with primary-only IOB_ROUTE:")
    print(f"  data diffs vs gold : {data_diffs}")
    print(f"  CRC  diffs vs gold : {crc_diffs}")
    total = data_diffs + crc_diffs
    print(f"  total              : {total}")

    # Save for reuse
    out_json = {
        "meta": {
            "source": "derived from simple_led Quartus gold ^ nv_zero "
                      "XOR (all non-IOB_ROUTE directives).  Single-LE, "
                      "no pair-template secondary-LE decoration.",
            "pin": "E16",
            "target": "X10Y4N0.dataa",
            "gold": "scripts/iob_slice_mining/work/simple_led_E16_to_G15/"
                    "output_files/simple_led_E16_to_G15.rbf",
        },
        "absolute_cells": {
            "IOB_E16->10,4,0,dataa": sorted(list(c) for c in primary),
        },
    }
    out_path = HERE / "work" / "iob_route_primary_derived.json"
    out_path.write_text(json.dumps(out_json, indent=2))
    print(f"\n[wrote] {out_path}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
