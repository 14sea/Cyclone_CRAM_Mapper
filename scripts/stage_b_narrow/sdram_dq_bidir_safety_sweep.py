# SPDX-License-Identifier: GPL-3.0-or-later
"""Bidir safety-gate sweep across all 16 NEORV32 sdram_dq pins.

For each sdram_dq pin P, apply `IOB_IN_BIDIR PIN_P + IOB_OUT_BIDIR PIN_P
+ IOB_OE PIN_P` atop simple_led_pure and classify the resulting overlap
with simple_led_pure's active cells by CRAM band:

    hdr_band   : (o-PRE) % FRAME < 208 and frame < 25
    fabric     : 25 <= frame < 1692 (SAFE_LO)
    block_band : 1692..1738 (SAFE_HI) — safe (simple_led uses no block)
    CRC        : (o-PRE) % FRAME >= 208 — follow-on CRC flips, ignored

Any pin whose gate surfaces `hdr` or `fabric` overlap bits needs a
per-pin `_IOB_BIDIR_FALSIFIED` mask entry before a NEORV32 build of
that pin's sdram_dq pad can be flashed safely.

Output:
  - stdout table per-pin (hdr / fabric / block / CRC counts)
  - results/sdram_dq_bidir_safety_sweep.json with per-pin classification
    and the explicit (off, bp) sets for any hdr/fabric leaks

R5 is the reference pin — already has a 2-cell `OUT_BIDIR` mask in
`_IOB_BIDIR_FALSIFIED`.  If this sweep reports `hdr=0 fabric=0 block=0`
for R5 and any other pin, that pin is software-ready for HW flash
under the same regression that proved R5's path.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f
from pure_zero_rbf import make_pure_zero_rbf


PRE = 32
FRAME = 210
SAFE_FRAME_LO, SAFE_FRAME_HI = 1692, 1738

# Full NEORV32 S_DB[0..15] pin map (neorv32_demo.qsf lines 115-130).
SDRAM_DQ_PINS = [
    "R5", "T4", "T3", "R3", "T2", "R1", "P2", "P1",
    "R13", "T13", "R12", "T12", "T10", "R10", "T11", "R11",
]

BASE_PATH = (REPO / "scripts" / "iob_slice_mining" / "work"
             / "simple_led_E16_to_G15" / "fasm_pure.rbf")

FASM_TMPL = """\
NV_BASELINE_PACK
IOB_BASELINE_NV
IOB_IN  PIN_E16
IOB_OUT PIN_G15
IOB_CLK_INPUT PIN_E1
IOB_ROUTE PIN_E16 -> X10Y4N0.dataa
GCLK_PIN PIN_E1
LAB_CLK_SEL X10Y4
LAB_CLK_SEL_LE X10Y4N0
IOB_IN_BIDIR  PIN_{pin}
IOB_OUT_BIDIR PIN_{pin}
IOB_OE        PIN_{pin}
"""


def _bits(a: bytes, b: bytes) -> set[tuple[int, int]]:
    s = set()
    for off in range(len(a)):
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                s.add((off, bp))
    return s


def _reset_caches():
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_OE_CACHE = None


def classify(overlap: set[tuple[int, int]]) -> dict:
    hdr, fabric, block, crc = [], [], [], []
    for off, bp in overlap:
        in_data = (off - PRE) % FRAME < 208
        frame = (off - PRE) // FRAME
        if not in_data:
            crc.append((off, bp))
        elif frame < 25:
            hdr.append((off, bp))
        elif SAFE_FRAME_LO <= frame <= SAFE_FRAME_HI:
            block.append((off, bp))
        else:
            fabric.append((off, bp))
    return {"hdr": hdr, "fabric": fabric, "block": block, "crc": crc}


def run_pin(pin: str, pure: bytes, base_rbf: bytes) -> dict:
    _reset_caches()
    fasm = FASM_TMPL.format(pin=pin)
    out = f.bitgen(fasm, pure, patch_crc=True)
    sl_bits = _bits(pure, base_rbf)
    di_bits = _bits(base_rbf, out)
    overlap = sl_bits & di_bits
    cls = classify(overlap)
    return {
        "pin": pin,
        "total_overlap": len(overlap),
        "hdr": len(cls["hdr"]),
        "fabric": len(cls["fabric"]),
        "block": len(cls["block"]),
        "crc": len(cls["crc"]),
        "di_bits": len(di_bits),
        "sl_bits": len(sl_bits),
        "hdr_cells": sorted(cls["hdr"]),
        "fabric_cells": sorted(cls["fabric"]),
        "block_cells": sorted(cls["block"]),
    }


def main() -> int:
    pure = make_pure_zero_rbf()
    if not BASE_PATH.exists():
        print(f"[err] simple_led_pure baseline missing: {BASE_PATH}")
        return 1
    base_rbf = BASE_PATH.read_bytes()

    results = []
    print(f"{'pin':6s}  {'hdr':>4s}  {'fab':>4s}  {'blk':>4s}  "
          f"{'CRC':>4s}  {'tot':>4s}  {'di':>5s}  verdict")
    print("-" * 70)
    for pin in SDRAM_DQ_PINS:
        r = run_pin(pin, pure, base_rbf)
        results.append(r)
        verdict = "PASS" if r["hdr"] == 0 and r["fabric"] == 0 else "LEAK"
        print(f"{pin:6s}  {r['hdr']:4d}  {r['fabric']:4d}  {r['block']:4d}  "
              f"{r['crc']:4d}  {r['total_overlap']:4d}  {r['di_bits']:5d}  "
              f"{verdict}")

    leaky = [r for r in results if r["hdr"] or r["fabric"]]
    print()
    print(f"{len(results) - len(leaky)}/{len(results)} sdram_dq pins PASS "
          f"the bidir safety gate.")
    if leaky:
        print(f"\n{len(leaky)} pins with hdr/fabric leaks require "
              f"_IOB_BIDIR_FALSIFIED mask extension:")
        for r in leaky:
            print(f"  {r['pin']:4s}  hdr={r['hdr']}  fabric={r['fabric']}  "
                  f"hdr_cells={r['hdr_cells'][:4]}{'...' if len(r['hdr_cells']) > 4 else ''}  "
                  f"fab_cells={r['fabric_cells']}")

    out_json = REPO / "results" / "sdram_dq_bidir_safety_sweep.json"
    out_json.write_text(json.dumps(results, indent=2))
    print(f"\n[wrote] {out_json}")
    return 0 if not leaky else 2


if __name__ == "__main__":
    sys.exit(main())
